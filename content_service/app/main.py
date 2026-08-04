import os
import time
import httpx
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()

import cloudinary
import cloudinary.uploader
import cloudinary.api

CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL")
if CLOUDINARY_URL:
    cloudinary.config(url=CLOUDINARY_URL)
elif os.environ.get("CLOUDINARY_CLOUD_NAME"):
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET")
    )

from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Response, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, text
from pydantic import BaseModel
import uuid
from typing import List, Optional

from app.crud import crud
from app.models import models
from app.schemas import schemas
from app.core.database import engine, get_db
from app.core.auth_deps import verify_token, verify_token_optional, get_current_publisher, get_current_admin, TokenData, require_tier
from app.services.automation.scheduler import automation_scheduler


class UnsplashRateLimiter:
    def __init__(self, limit: int = 50, period: int = 3600):
        self.limit = limit
        self.period = period
        self.requests = []

    def is_allowed(self) -> bool:
        now = time.time()
        self.requests = [t for t in self.requests if t > now - self.period]
        if len(self.requests) >= self.limit:
            return False
        self.requests.append(now)
        return True

unsplash_limiter = UnsplashRateLimiter(limit=50, period=3600)

# --- GEMINI AI SETUP ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL_NAME", "gemma-4-26b-a4b-it")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
else:
    print("Warning: GEMINI_API_KEY missing. AI features will be disabled.")

try:
    models.Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Startup Warning: Database table creation failed (expected if DB is still starting): {e}")

app = FastAPI(title="Advanced CMS Service")

# --- EXCEPTION HANDLERS ---
@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request, exc: IntegrityError):
    msg = str(exc.orig).lower()
    detail = "An item with this value already exists."
    
    if "unique constraint" in msg or "already exists" in msg:
        if "categories_name_key" in msg: detail = "A category with this name already exists."
        elif "categories_slug_key" in msg: detail = "A category with this slug already exists."
        elif "keywords_tag_key" in msg: detail = "This tag already exists."
        elif "articles_slug_key" in msg: detail = "An article with this slug already exists."
        
        return Response(content='{"detail": "' + detail + '"}', status_code=409, media_type="application/json")
    
    return Response(content='{"detail": "Database integrity error."}', status_code=400, media_type="application/json")

raw_origins = os.environ.get("CORS_ORIGINS", "")
if raw_origins:
    cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
else:
    cors_origins = []

if not cors_origins:
    cors_origins = ["https://relaypost.me"]

MEDIA_BASE_URL = os.environ.get("MEDIA_BASE_URL", "http://localhost:8001")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Dispose of engine connection pool to prevent fork-related SSL/EOF errors
    engine.dispose()
    # Start the automation scheduler
    automation_scheduler.start()
    # Register weekly digest cron job (Sunday 06:00 UTC)
    _register_digest_job()

@app.on_event("shutdown")
async def shutdown_event():
    # Clean shutdown
    automation_scheduler.shutdown()

def _register_digest_job():
    """Add the weekly digest job to the existing AutomationScheduler."""
    if os.environ.get("DISABLE_DIGEST_JOB", "").lower() == "true":
        print("[DIGEST] Weekly digest job is DISABLED via DISABLE_DIGEST_JOB env var.")
        return

    from apscheduler.triggers.cron import CronTrigger
    from app.services.digest_scheduler import run_digest_job_sync
    try:
        automation_scheduler.scheduler.add_job(
            run_digest_job_sync,
            CronTrigger(day_of_week="sun", hour=6, minute=0, timezone="UTC"),
            id="weekly_digest_job",
            replace_existing=True,
            misfire_grace_time=3600,
            max_instances=1,
        )
        print("[DIGEST] Weekly digest job registered (Sunday 06:00 UTC).")
    except Exception as e:
        print(f"[DIGEST] Failed to register digest job: {e}")

@app.get("/")
def read_root():
    return {"status": "online", "service": "RelayPost Content Service", "version": "1.0.0"}

# --- PUBLIC ENDPOINTS ---

@app.get("/public/articles/search", response_model=List[schemas.ArticleResponse])
def search_public_articles(q: str, limit: int = 10, db: Session = Depends(get_db)):
    return crud.search_articles(db, query_str=q, limit=limit)

@app.get("/public/articles/trending", response_model=List[schemas.ArticleResponse])
def get_trending_articles(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    # Using 'is_featured' and 'PUBLISHED' status to get top articles
    query = db.query(models.Article).filter(models.Article.status == models.ArticleStatus.PUBLISHED, models.Article.is_featured == True)
    return query.order_by(models.Article.published_at.desc()).offset(skip).limit(limit).all()

@app.get("/public/articles", response_model=List[schemas.ArticleResponse])
def get_public_articles(skip: int = 0, limit: int = 20, template: Optional[str] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Article).filter(models.Article.status == models.ArticleStatus.PUBLISHED)
    if template:
        query = query.filter(models.Article.template_type == template)
    if category:
        # Check if category is slug or name
        query = query.join(models.Category).filter(
            (func.lower(models.Category.slug) == category.lower()) | (func.lower(models.Category.name) == category.lower())
        )
    return query.order_by(models.Article.published_at.desc()).offset(skip).limit(limit).all()

@app.get("/public/articles/section/{section}", response_model=List[schemas.ArticleResponse])
def get_articles_by_section(section: str, category: Optional[str] = None, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_articles_by_section(db, section=section, category=category, limit=limit)

@app.get("/public/articles/{slug}", response_model=schemas.ArticleDetailResponse)
def get_public_article(slug: str, db: Session = Depends(get_db)):
    article = crud.get_article_by_slug(db, slug=slug)
    if not article or article.status != models.ArticleStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Calculate counts for the response
    return {
        **schemas.ArticleResponse.from_orm(article).model_dump(),
        "views_count": article.views_count,
        "likes_count": len(article.likes),
        "reflections": article.reflections
    }

@app.post("/public/articles/{article_id}/view")
def record_view(
    article_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(verify_token_optional)
):
    crud.add_view(db, article_id)
    if current_user:
        # Check if already viewed recently to prevent duplicates
        user_uuid = uuid.UUID(current_user.user_id)
        exists = db.query(models.ReadingHistory).filter(
            models.ReadingHistory.user_id == user_uuid,
            models.ReadingHistory.article_id == article_id
        ).first()
        if not exists:
            new_history = models.ReadingHistory(user_id=user_uuid, article_id=article_id)
            db.add(new_history)
            db.commit()
    return {"message": "View recorded"}

class DurationUpdate(BaseModel):
    duration_seconds: int

@app.patch("/public/articles/{article_id}/view/duration")
def update_view_duration(
    article_id: uuid.UUID,
    data: DurationUpdate,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(verify_token_optional)
):
    if not current_user:
        return {"message": "unauthenticated"}
        
    if current_user.tier == "free":
        return {"message": "duration not tracked for free users"}
        
    user_uuid = uuid.UUID(current_user.user_id)
    history = db.query(models.ReadingHistory).filter(
        models.ReadingHistory.user_id == user_uuid,
        models.ReadingHistory.article_id == article_id
    ).order_by(models.ReadingHistory.read_at.desc()).first()
    
    if history:
        history.duration_seconds = (history.duration_seconds or 0) + data.duration_seconds
        db.commit()
    return {"message": "duration updated"}

class NewsViewData(BaseModel):
    title: str
    slug: str

@app.post("/public/news/{news_id}/view")
def record_news_view(
    news_id: int,
    data: NewsViewData,
    db: Session = Depends(get_db),
    current_user: Optional[TokenData] = Depends(verify_token_optional)
):
    if current_user:
        user_uuid = uuid.UUID(current_user.user_id)
        exists = db.query(models.ReadingHistory).filter(
            models.ReadingHistory.user_id == user_uuid,
            models.ReadingHistory.news_article_id == news_id,
            models.ReadingHistory.source_type == "news"
        ).first()
        if not exists:
            new_history = models.ReadingHistory(
                user_id=user_uuid, 
                source_type="news",
                news_article_id=news_id,
                news_title=data.title,
                news_slug=data.slug
            )
            db.add(new_history)
            db.commit()
    return {"message": "News view recorded"}

@app.get("/profile/history")
def get_user_history(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(verify_token)
):
    user_uuid = uuid.UUID(current_user.user_id)
    history_items = db.query(models.ReadingHistory).filter(
        models.ReadingHistory.user_id == user_uuid
    ).order_by(models.ReadingHistory.read_at.desc()).offset(offset).limit(limit).all()
    
    result = []
    for h in history_items:
        item = {
            "id": str(h.id),
            "source_type": h.source_type,
            "read_at": h.read_at.isoformat() if h.read_at else None,
            "duration_seconds": h.duration_seconds
        }
        if h.source_type == "article" and h.article:
            item["article"] = {
                "id": str(h.article.id),
                "title": h.article.title,
                "slug": h.article.slug,
                "category_name": h.article.category_name,
                "image_url": h.article.hero_image
            }
        elif h.source_type == "news":
            item["news"] = {
                "id": h.news_article_id,
                "title": h.news_title,
                "slug": h.news_slug
            }
        result.append(item)
    return result

@app.post("/public/articles/{article_id}/reflections", response_model=schemas.ReflectionResponse)
def add_reflection(article_id: uuid.UUID, reflection: schemas.ReflectionCreate, db: Session = Depends(get_db)):
    return crud.add_reflection(db, article_id, reflection)

@app.post("/admin/articles/{article_id}/like")
def toggle_like(article_id: uuid.UUID, db: Session = Depends(get_db), current_user: TokenData = Depends(verify_token)):
    # Note: verify_token is used here to allow any logged in user to like
    user_id = uuid.UUID(current_user.user_id)
    liked = crud.toggle_like(db, article_id, user_id)
    return {"liked": liked}

@app.get("/public/categories", response_model=List[schemas.CategoryResponse])
def get_public_categories(db: Session = Depends(get_db)):
    return crud.get_categories(db)

@app.get("/public/homepage/category-sections")
def get_homepage_category_sections(limit: int = 10, categories: Optional[List[str]] = Query(None), db: Session = Depends(get_db)):
    return crud.get_homepage_category_articles(db, limit=limit, categories=categories)


@app.get("/public/keywords", response_model=List[schemas.KeywordResponse])
def get_public_keywords(limit: Optional[int] = None, db: Session = Depends(get_db)):
    return crud.get_keywords(db, limit=limit)

@app.get("/public/meta/popular-keywords", response_model=List[str])
def get_popular_string_keywords(limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_popular_string_keywords(db, limit=limit)

@app.post("/public/newsletter/subscribe")
def subscribe_newsletter(sub: schemas.NewsletterCreate, db: Session = Depends(get_db)):
    crud.subscribe_newsletter(db, sub.email)
    return {"message": "Subscribed successfully"}

@app.post("/public/follow/toggle", response_model=Optional[schemas.FollowResponse])
def toggle_follow(follow: schemas.FollowToggle, db: Session = Depends(get_db)):
    return crud.toggle_follow(db, follow)

@app.get("/public/follows/{user_id}", response_model=List[schemas.FollowResponse])
def get_user_follows(user_id: str, db: Session = Depends(get_db)):
    return crud.get_user_follows(db, user_id)


# --- PROTECTED ADMIN/PUBLISHER ENDPOINTS ---

@app.get("/admin/categories", response_model=List[schemas.CategoryResponse])
def get_admin_categories(db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    return crud.get_categories(db)

@app.post("/admin/categories", response_model=schemas.CategoryResponse)
def create_category(category: schemas.CategoryBase, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    return crud.create_category(db, category)

@app.post("/admin/keywords", response_model=schemas.KeywordResponse)
def create_keyword(keyword: schemas.KeywordBase, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    return crud.create_keyword(db, keyword)

@app.get("/admin/keywords", response_model=List[schemas.KeywordResponse])
def get_all_keywords(db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    return crud.get_admin_keywords(db)


# --- MEDIA ENDPOINTS ---

@app.post("/admin/media/upload", response_model=schemas.MediaResponse)
async def upload_media(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    contents = await file.read()
    db_media = crud.create_media(
        db=db,
        filename=file.filename,
        content_type=file.content_type,
        data=contents,
        size=len(contents)
    )
    return {
        "id": db_media.id,
        "filename": db_media.filename,
        "content_type": db_media.content_type,
        "size": db_media.size,
        "created_at": db_media.created_at,
        "url": f"{MEDIA_BASE_URL}/public/media/{db_media.id}"
    }

@app.get("/public/media/{media_id}")
def get_media_file(media_id: uuid.UUID, db: Session = Depends(get_db)):
    db_media = crud.get_media(db, media_id)
    if not db_media:
        raise HTTPException(status_code=404, detail="Media not found")
    return Response(content=db_media.data, media_type=db_media.content_type)

@app.get("/admin/media", response_model=List[schemas.MediaResponse])
def get_all_media(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    media_list = crud.get_all_media(db, skip=skip, limit=limit)
    return [
        {
            "id": m.id,
            "filename": m.filename,
            "content_type": m.content_type,
            "size": m.size,
            "created_at": m.created_at,
            "url": f"{MEDIA_BASE_URL}/public/media/{m.id}"
        } for m in media_list
    ]

@app.get("/admin/media/stock/search")
async def search_unsplash_stock(query: str, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    if not unsplash_limiter.is_allowed():
        raise HTTPException(status_code=429, detail="Unsplash search quota exceeded (50/hr). Please try again later.")

    access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not access_key:
        raise HTTPException(status_code=500, detail="Unsplash configuration missing on server.")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": 24},
                headers={"Authorization": f"Client-ID {access_key}"},
                timeout=10.0
            )
            if response.status_code != 200:
                print(f"Unsplash API Error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Remote stock photo provider error")
            
            data = response.json()
            return data.get("results", [])
        except Exception as e:
            print(f"Unsplash Proxy Error: {e}")
            raise HTTPException(status_code=500, detail="Failed to connect to stock photo provider")

# --- AI INTELLIGENCE ---
@app.post("/admin/ai/rewrite")
async def ai_rewrite(payload: dict, current_user: TokenData = Depends(get_current_publisher)):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini AI is not configured on the server.")
    
    text = payload.get("text")
    intent = payload.get("intent", "professional")
    
    if not text:
        raise HTTPException(status_code=400, detail="Text is required for rewriting.")

    prompt = f"""
    You are an expert editorial assistant. 
    Rewrite the following text with a '{intent}' tone.
    Maintain the original meaning but improve clarity, impact, and style.
    Do NOT include any preamble or extra commentary. Return ONLY the rewritten text.
    
    Text: {text}
    """

    try:
        response = await model.generate_content_async(prompt)
        return {"original": text, "rewritten": response.text.strip()}
    except Exception as e:
        print(f"Gemini Rewrite Error: {e}")
        raise HTTPException(status_code=500, detail="AI Rewrite service failed.")

from app.services.automation.engine import ArticleAutomationEngine
from app.core.database import SessionLocal as AutomationSessionLocal

@app.post("/admin/ai/trigger-automation")
async def trigger_automation_manually(background_tasks: BackgroundTasks, current_user: TokenData = Depends(get_current_admin)):
    db = AutomationSessionLocal()
    has_lock = db.execute(text("SELECT pg_try_advisory_lock(1001)")).scalar()
    if not has_lock:
        db.close()
        raise HTTPException(status_code=409, detail="Automation is currently running. Please wait.")
    db.execute(text("SELECT pg_advisory_unlock(1001)"))
    db.commit()
    db.close()

    batch_size = int(os.getenv("AUTOMATION_BATCH_SIZE", "3"))  # Default 3 articles per run
    print(f"[Trigger] Using batch_size={batch_size}")
    
    async def run_engine():
        bg_db = AutomationSessionLocal()
        lock_acquired = bg_db.execute(text("SELECT pg_try_advisory_lock(1001)")).scalar()
        if not lock_acquired:
            bg_db.close()
            return
            
        try:
            engine = ArticleAutomationEngine(bg_db)
            await engine.run_pipeline(batch_size=batch_size)
        finally:
            bg_db.execute(text("SELECT pg_advisory_unlock(1001)"))
            bg_db.commit()
            bg_db.close()
        
    background_tasks.add_task(run_engine)
    return {"message": f"Automation triggered in background for {batch_size} articles."}

@app.post("/admin/ai/trigger-topic")
async def trigger_topic_manually(payload: dict, background_tasks: BackgroundTasks, current_user: TokenData = Depends(get_current_admin)):
    topic = payload.get("topic")
    category = payload.get("category", "Intelligence")
    search_queries_str = payload.get("search_queries", "")
    
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    # Process search queries
    parsed_queries = [q.strip() for q in search_queries_str.split(",")] if search_queries_str.strip() else []
    final_queries = parsed_queries if parsed_queries else [topic]

    db = AutomationSessionLocal()
    has_lock = db.execute(text("SELECT pg_try_advisory_lock(1001)")).scalar()
    if not has_lock:
        db.close()
        raise HTTPException(status_code=409, detail="Automation is currently running. Please wait.")
    db.execute(text("SELECT pg_advisory_unlock(1001)")) 
    db.commit()
    db.close()

    async def run_engine_topic():
        bg_db = AutomationSessionLocal()
        lock_acquired = bg_db.execute(text("SELECT pg_try_advisory_lock(1001)")).scalar()
        if not lock_acquired:
            bg_db.close()
            return
            
        try:
            engine = ArticleAutomationEngine(bg_db)
            topic_info = {
                "title": topic,
                "search_queries": final_queries,
                "category": category,
                "template_type": "standard"
            }
            
            from app.crud.crud import get_latest_prompt_version
            latest_prompt = get_latest_prompt_version(bg_db)
            from app.services.automation.prompts import CONTENT_GENERATION_DYNAMIC_PROMPT
            engine.current_content_prompt = latest_prompt.content_generation_dynamic if latest_prompt else CONTENT_GENERATION_DYNAMIC_PROMPT
            
            await engine.process_single_topic(topic_info)
        finally:
            bg_db.execute(text("SELECT pg_advisory_unlock(1001)"))
            bg_db.commit()
            bg_db.close()
            
    background_tasks.add_task(run_engine_topic)
    return {"message": f"Generation for topic '{topic}' triggered in background."}

@app.post("/admin/automation/pause")
async def pause_automation(current_user: TokenData = Depends(get_current_admin)):
    automation_scheduler.pause_automation()
    return {"message": "Article generation scheduling has been paused."}

@app.post("/admin/automation/resume")
async def resume_automation(current_user: TokenData = Depends(get_current_admin)):
    automation_scheduler.resume_automation()
    return {"message": "Article generation scheduling has been resumed."}

# --- DIGEST SCHEDULER CONTROL ---

@app.get("/admin/digest/status")
async def get_digest_status(current_user: TokenData = Depends(get_current_admin)):
    """Returns whether the weekly digest job is currently scheduled and when it next runs."""
    job = automation_scheduler.scheduler.get_job("weekly_digest_job")
    if job:
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        return {"active": True, "next_run": next_run}
    return {"active": False, "next_run": None}

@app.post("/admin/digest/pause")
async def pause_digest_job(current_user: TokenData = Depends(get_current_admin)):
    """Removes the weekly digest cron job from the scheduler until resumed."""
    job = automation_scheduler.scheduler.get_job("weekly_digest_job")
    if job:
        automation_scheduler.scheduler.remove_job("weekly_digest_job")
        return {"message": "Weekly digest scheduler has been paused. No digest will run until resumed."}
    return {"message": "Digest scheduler was already inactive."}

@app.post("/admin/digest/resume")
async def resume_digest_job(current_user: TokenData = Depends(get_current_admin)):
    """Re-registers the weekly digest cron job (Sunday 06:00 UTC)."""
    from apscheduler.triggers.cron import CronTrigger
    from app.services.digest_scheduler import run_digest_job_sync
    existing = automation_scheduler.scheduler.get_job("weekly_digest_job")
    if existing:
        return {"message": "Digest scheduler is already active."}
    automation_scheduler.scheduler.add_job(
        run_digest_job_sync,
        CronTrigger(day_of_week="sun", hour=6, minute=0, timezone="UTC"),
        id="weekly_digest_job",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )
    return {"message": "Weekly digest scheduler has been resumed. Next run: Sunday 06:00 UTC."}

from app.services.automation.learning import SelfLearningEngine

@app.post("/admin/automation/learning/trigger")
async def trigger_learning_loop(background_tasks: BackgroundTasks, current_user: TokenData = Depends(get_current_admin)):
    async def run_learning():
        db = AutomationSessionLocal()
        try:
            engine = SelfLearningEngine(db)
            await engine.analyze_and_update_prompt()
        finally:
            db.close()
            
    background_tasks.add_task(run_learning)
    return {"message": "Self-learning evaluation triggered in the background."}

from app.services.automation.placement import HomepagePlacementEngine

@app.post("/admin/automation/placement/trigger")
async def trigger_placement_manually(background_tasks: BackgroundTasks, current_user: TokenData = Depends(get_current_admin)):
    async def run_placement():
        db = AutomationSessionLocal()
        try:
            engine = HomepagePlacementEngine(db)
            await engine.reorder_homepage_placements()
        finally:
            db.close()
            
    background_tasks.add_task(run_placement)
    return {"message": "Homepage placement curation triggered in the background."}


# --- USER CONTRIBUTION ENDPOINTS ---

@app.post("/public/contributions", response_model=schemas.UserContributionResponse)
def submit_contribution(contribution: schemas.UserContributionCreate, db: Session = Depends(get_db), current_user: TokenData = Depends(verify_token)):
    return crud.create_user_contribution(db, uuid.UUID(current_user.user_id), contribution)

@app.get("/admin/contributions", response_model=List[schemas.UserContributionResponse])
def list_contributions(skip: int = 0, limit: int = 50, status: str = None, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    return crud.get_user_contributions(db, skip=skip, limit=limit, status=status)

# --- USER PROFILE ENDPOINTS ---
@app.get("/profile/stats")
def get_profile_stats(db: Session = Depends(get_db), current_user: TokenData = Depends(verify_token)):
    user_id = uuid.UUID(current_user.user_id)
    return crud.get_user_profile_stats(db, user_id)

@app.get("/profile/saved", response_model=List[schemas.ArticleResponse])
def get_user_saved_articles(limit: int = 20, db: Session = Depends(get_db), current_user: TokenData = Depends(verify_token)):
    user_id = uuid.UUID(current_user.user_id)
    return crud.get_saved_articles(db, user_id, limit)

@app.get("/profile/favorites", response_model=List[schemas.ArticleResponse])
def get_user_favorites(limit: int = 20, db: Session = Depends(get_db), current_user: TokenData = Depends(verify_token)):
    user_id = uuid.UUID(current_user.user_id)
    return crud.get_favorited_articles(db, user_id, limit)

@app.get("/profile/contributions", response_model=List[schemas.UserContributionResponse])
def get_my_contributions(limit: int = 20, db: Session = Depends(get_db), current_user: TokenData = Depends(verify_token)):
    user_id = uuid.UUID(current_user.user_id)
    # Reusing the existing function but filtering by user if we extended it, 
    # but crud.get_user_contributions doesn't filter by user yet. Let's do it inline:
    return db.query(models.UserContribution).filter(models.UserContribution.user_id == user_id).order_by(models.UserContribution.created_at.desc()).limit(limit).all()

@app.post("/profile/articles/{article_id}/save")
def toggle_save(article_id: uuid.UUID, db: Session = Depends(get_db), current_user: TokenData = Depends(verify_token)):
    user_id = uuid.UUID(current_user.user_id)
    saved = crud.toggle_save_article(db, article_id, user_id)
    return {"saved": saved}

@app.put("/admin/contributions/{contribution_id}", response_model=schemas.UserContributionResponse)
def update_contribution(contribution_id: uuid.UUID, data: dict, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    updated = crud.update_contribution_status(
        db, 
        contribution_id, 
        status=data.get("status"), 
        admin_notes=data.get("admin_notes")
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Contribution not found")
    return updated

# --- SUGGESTION ENDPOINTS ---

@app.post("/admin/articles/suggest-keywords", response_model=List[schemas.KeywordSuggestion])
def suggest_keywords(payload: dict, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    text = f"{payload.get('title', '')} {payload.get('excerpt', '')} {payload.get('content_snippet', '')}"
    return crud.suggest_keywords(db, text)

@app.get("/admin/articles/{article_id}/suggest-links", response_model=List[schemas.LinkSuggestion])
def suggest_links(article_id: uuid.UUID, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    return crud.suggest_links(db, article_id)

# --- ARTICLE CRUD ---

@app.post("/admin/articles", response_model=schemas.ArticleResponse)
def create_article(article: schemas.ArticleCreate, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    article.author_id = current_user.user_id
    return crud.create_article(db=db, article=article)

@app.get("/admin/articles", response_model=schemas.PaginatedArticleResponse)
def get_all_articles(
    page: int = 1, 
    size: int = 25, 
    category_ids: Optional[List[uuid.UUID]] = Query(None),
    keywords: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db), 
    current_user: TokenData = Depends(get_current_publisher)
):
    skip = (page - 1) * size
    items, total = crud.get_articles(
        db, 
        skip=skip, 
        limit=size, 
        include_deleted=True, 
        category_ids=category_ids, 
        keywords=keywords
    )
    pages = (total + size - 1) // size
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }

@app.get("/public/articles/keyword/{tag}", response_model=schemas.PaginatedArticleResponse)
def get_articles_by_keyword(tag: str, page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    skip = (page - 1) * size
    items, total = crud.get_articles_by_keyword(db, tag=tag, skip=skip, limit=size)
    pages = (total + size - 1) // size
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }


@app.get("/admin/articles/{article_id}", response_model=schemas.ArticleResponse)
def get_admin_article(article_id: uuid.UUID, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    article = crud.get_article(db, article_id=article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article

@app.put("/admin/articles/{article_id}", response_model=schemas.ArticleResponse)
def update_article(article_id: uuid.UUID, update_data: schemas.ArticleUpdate, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    db_article = crud.get_article(db, article_id=article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    return crud.update_article(db=db, db_article=db_article, update_data=update_data, current_user_id=uuid.UUID(current_user.user_id))

@app.put("/admin/articles/{article_id}/placement", response_model=schemas.ArticleResponse)
def update_article_placement(article_id: uuid.UUID, update_data: schemas.ArticlePlacementUpdate, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    db_article = crud.update_article_placement(db, article_id=article_id, update_data=update_data)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    return db_article

@app.delete("/admin/articles/{article_id}")
def archive_article(article_id: uuid.UUID, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    db_article = crud.get_article(db, article_id=article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    crud.delete_article(db, db_article)
    return {"message": "Article archived successfully"}

@app.post("/admin/articles/{article_id}/restore")
def restore_article(article_id: uuid.UUID, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    db_article = crud.restore_article(db, article_id=article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"message": "Article restored successfully"}


# --- CATEGORY ADMIN ---

@app.put("/admin/categories/{category_id}", response_model=schemas.CategoryResponse)
def update_category(category_id: uuid.UUID, category: schemas.CategoryBase, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    updated = crud.update_category(db, category_id, category)
    if not updated:
        raise HTTPException(status_code=404, detail="Category not found")
    return updated

@app.delete("/admin/categories/{category_id}")
def delete_category(category_id: uuid.UUID, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    success = crud.delete_category(db, category_id)
    if not success:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"message": "Category deleted"}


# --- DASHBOARD ADMIN ---

@app.get("/admin/stats/content")
def get_content_statistics(db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    return crud.get_content_stats(db)

@app.get("/admin/activity")
def list_activity(limit: int = 15, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    return crud.get_recent_activity(db, limit=limit)

# --- SYSTEM SETTINGS ---
@app.get("/admin/settings", response_model=schemas.SystemSettingsResponse)
def get_system_settings(db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    return crud.get_system_settings(db)

@app.put("/admin/settings", response_model=schemas.SystemSettingsResponse)
def update_system_settings(data: schemas.SystemSettingsBase, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    return crud.update_system_settings(db, data)

@app.get("/public/settings", response_model=schemas.SystemSettingsResponse)
def get_public_settings(db: Session = Depends(get_db)):
    return crud.get_system_settings(db)


# --- CONTACT INQUIRIES ---

@app.post("/public/contact", response_model=schemas.ContactInquiryResponse)
def submit_contact_inquiry(inquiry: schemas.ContactInquiryCreate, db: Session = Depends(get_db)):
    try:
        return crud.create_contact_inquiry(db=db, inquiry=inquiry)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not submit inquiry")

@app.get("/admin/inquiries", response_model=List[schemas.ContactInquiryResponse])
def list_admin_inquiries(status: Optional[str] = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    return crud.get_all_inquiries(db, status=status, skip=skip, limit=limit)

@app.patch("/admin/inquiries/{inquiry_id}/status", response_model=schemas.ContactInquiryResponse)
def update_inquiry_status(inquiry_id: str, payload: schemas.ContactInquiryStatusUpdate, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    updated_inquiry = crud.update_inquiry_status(db, inquiry_id, payload.status)
    if not updated_inquiry:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    return updated_inquiry

@app.get("/admin/inquiries/notifications")
def get_inquiry_notifications(db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    unread_count = crud.count_unread_inquiries(db)
    inquiries = crud.get_unread_inquiries(db, limit=5)
    return {
        "unread_count": unread_count,
        "recent_inquiries": [schemas.ContactInquiryResponse.model_validate(i) for i in inquiries]
    }

@app.get("/admin/notifications", response_model=List[schemas.AdminNotificationResponse])
def list_admin_notifications(skip: int = 0, limit: int = 20, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    return db.query(models.AdminNotification).order_by(models.AdminNotification.created_at.desc()).offset(skip).limit(limit).all()

@app.post("/admin/notifications/{notification_id}/read")
def mark_notification_read(notification_id: uuid.UUID, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    notif = db.query(models.AdminNotification).filter(models.AdminNotification.id == notification_id).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"message": "Notification marked as read"}


# =============================================================================
# PREMIUM AI ROUTES — Tier gated + Usage tracked
# =============================================================================
from app.core.auth_deps import check_and_track_usage, track_usage, require_tier
from app.services.premium.ai_service import (
    generate_article_summary,
    ask_ai_about_article,
    cross_article_summary,
    generate_research_report,
    generate_weekly_report,
)


class AskAIRequest(BaseModel):
    question: str


class CrossSummaryRequest(BaseModel):
    article_ids: List[uuid.UUID]
    synthesis_query: Optional[str] = None


class ResearchModeRequest(BaseModel):
    topic: str
    article_ids: Optional[List[uuid.UUID]] = None
    include_news: bool = True


class WeeklyReportRequest(BaseModel):
    topic_cluster: str


@app.post("/premium/ai/summary/{article_id}")
async def ai_article_summary(
    article_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(check_and_track_usage("ai_summary")),
):
    """
    Generate AI summary for a single article.
    Free: 10/month | Plus: 40/24h | Pro: unlimited
    """
    article = crud.get_article(db, article_id)
    if not article or article.status != models.ArticleStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Article not found")

    try:
        summary = article.ai_summary
        if not summary:
            # Fallback if an article was published before automation was added
            summary = "No AI summary is currently available for this article."
            
        track_usage(current_user.user_id, "ai_summary", current_user.tier)
        return {"article_id": str(article_id), "summary": summary, "tier": current_user.tier}
    except Exception as e:
        print(f"AI Service Summary Exception: {e}")
        return {
            "article_id": str(article_id),
            "summary": "The AI service is temporarily unavailable. Please try again shortly.",
            "tier": current_user.tier
        }


@app.post("/premium/ai/ask/{article_id}")
async def ai_ask_article(
    article_id: uuid.UUID,
    payload: AskAIRequest,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(check_and_track_usage("ask_ai")),
):
    """
    Ask AI a question about a specific article.
    Free: 5/month | Plus: 25/24h | Pro: unlimited
    """
    article = crud.get_article(db, article_id)
    if not article or article.status != models.ArticleStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Article not found")

    content_text = " ".join(
        block.get("content", "") if isinstance(block, dict) else ""
        for block in (article.content_blocks or [])
    )

    try:
        answer = ask_ai_about_article(article.title, content_text, payload.question, tier=current_user.tier)
        track_usage(current_user.user_id, "ask_ai", current_user.tier)
        return {"article_id": str(article_id), "question": payload.question, "answer": answer}
    except Exception as e:
        print(f"AI Service Exception: {e}")
        return {
            "article_id": str(article_id),
            "question": payload.question,
            "answer": "The AI service is temporarily unavailable. Please try again shortly."
        }


@app.post("/premium/ai/cross-summary")
async def ai_cross_article_summary(
    payload: CrossSummaryRequest,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(check_and_track_usage("cross_article")),
):
    """Cross-article synthesis — Pro only."""
    articles_data = []
    for aid in payload.article_ids[:20]:
        a = crud.get_article(db, aid)
        if a and a.status == models.ArticleStatus.PUBLISHED:
            articles_data.append({"title": a.title, "excerpt": a.excerpt or "", "content_snippet": a.excerpt or ""})

    if not articles_data:
        raise HTTPException(status_code=400, detail="No valid articles found")

    try:
        result = cross_article_summary(articles_data, payload.synthesis_query)
        track_usage(current_user.user_id, "cross_article", current_user.tier)
        return {"synthesis": result, "article_count": len(articles_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")


@app.post("/premium/ai/research")
async def ai_research_mode(
    payload: ResearchModeRequest,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(check_and_track_usage("research_mode")),
):
    """Research Mode — Pro only, 30/month soft cap."""
    background_articles = []
    if payload.article_ids:
        for aid in payload.article_ids[:15]:
            a = crud.get_article(db, aid)
            if a and a.status == models.ArticleStatus.PUBLISHED:
                background_articles.append({
                    "title": a.title,
                    "content_snippet": a.excerpt or "",
                    "published_at": str(a.published_at)[:10] if a.published_at else "",
                    "source": "RelayPost",
                })

    news_articles = []
    if payload.include_news:
        import httpx as _httpx
        NEWS_SERVICE = os.environ.get("NEWS_SERVICE_URL", "http://news_service:8002")
        try:
            resp = _httpx.get(f"{NEWS_SERVICE}/api/news/live?limit=10&search={payload.topic}", timeout=5.0)
            if resp.status_code == 200:
                for na in resp.json()[:10]:
                    news_articles.append({
                        "title": na.get("title", ""),
                        "content_snippet": na.get("description", ""),
                        "published_at": na.get("published_at", "")[:10] if na.get("published_at") else "",
                        "source": na.get("source_name", "News"),
                    })
        except Exception as e:
            print(f"News fetch warning in research mode: {e}")

    try:
        result = generate_research_report(payload.topic, background_articles, news_articles)
        track_usage(current_user.user_id, "research_mode", current_user.tier)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")


@app.get("/premium/weekly-report/{topic_cluster}")
async def ai_weekly_report(
    topic_cluster: str,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    """Weekly Intelligence Report — Plus and Pro. Cached per topic per week."""
    # Fetch recent articles for this topic cluster
    articles = crud.search_articles(db, query_str=topic_cluster, limit=15)
    articles_data = [{"title": a.title, "excerpt": a.excerpt or ""} for a in articles]

    from datetime import datetime
    week_label = datetime.utcnow().strftime("Week of %b %d, %Y")

    try:
        result = generate_weekly_report(topic_cluster, articles_data, week_label)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")


# =============================================================================
# BOOKMARK ROUTES — Extended with source_type, folder/tag support
# =============================================================================

class BookmarkCreate(BaseModel):
    source_type: str = "article"    # 'article' | 'news'
    article_id: Optional[uuid.UUID] = None
    # News bookmark fields
    news_article_id: Optional[int] = None
    news_title: Optional[str] = None
    news_slug: Optional[str] = None
    news_image_url: Optional[str] = None
    news_source: Optional[str] = None


class BookmarkUpdate(BaseModel):
    folder_id: Optional[uuid.UUID] = None
    tag_ids: Optional[List[str]] = None
    notes: Optional[str] = None


class BookmarkFolderCreate(BaseModel):
    name: str
    description: Optional[str] = None


class BookmarkTagCreate(BaseModel):
    name: str
    color: str = "#6366f1"


@app.get("/bookmarks")
def get_bookmarks(
    source_type: Optional[str] = None,  # 'article' | 'news' | None (all)
    folder_id: Optional[uuid.UUID] = None,
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(verify_token),
):
    """Get all bookmarks for the current user. Supports filtering by source_type."""
    from app.core.auth_deps import _get_verified_tier
    verified_tier = _get_verified_tier(current_user.user_id)

    query = db.query(models.SavedArticle).filter(
        models.SavedArticle.user_id == uuid.UUID(current_user.user_id)
    )
    if source_type:
        query = query.filter(models.SavedArticle.source_type == source_type)
    if folder_id:
        query = query.filter(models.SavedArticle.folder_id == folder_id)

    bookmarks = query.order_by(models.SavedArticle.saved_at.desc()).offset(skip).limit(limit).all()
    total = query.count()

    # Get bookmark limit for free users
    bookmark_limit = 20 if verified_tier == "free" else -1

    result = []
    for bm in bookmarks:
        item = {
            "id": str(bm.id),
            "source_type": bm.source_type,
            "saved_at": bm.saved_at.isoformat() if bm.saved_at else None,
            "folder_id": str(bm.folder_id) if bm.folder_id else None,
            "tag_ids": bm.tag_ids or [],
            "notes": bm.notes,
        }
        if bm.source_type == "article" and bm.article_id:
            article = crud.get_article(db, bm.article_id)
            if article:
                item.update({"article_id": str(bm.article_id), "title": article.title, "slug": article.slug, "hero_image": article.hero_image, "excerpt": article.excerpt})
        elif bm.source_type == "news":
            item.update({"news_article_id": bm.news_article_id, "title": bm.news_title, "slug": bm.news_slug, "hero_image": bm.news_image_url, "source": bm.news_source})
        result.append(item)

    return {"bookmarks": result, "total": total, "bookmark_limit": bookmark_limit, "tier": verified_tier}


@app.post("/bookmarks")
def create_bookmark(
    payload: BookmarkCreate,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(verify_token),
):
    """Create a bookmark. Free users capped at 20 total."""
    from app.core.auth_deps import _get_verified_tier
    verified_tier = _get_verified_tier(current_user.user_id)
    user_uuid = uuid.UUID(current_user.user_id)

    # Enforce free tier bookmark limit
    if verified_tier == "free":
        total = db.query(models.SavedArticle).filter(
            models.SavedArticle.user_id == user_uuid
        ).count()
        if total >= 20:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "bookmark_limit_exceeded",
                    "limit": 20,
                    "current": total,
                    "message": "You've reached the 20-bookmark limit on the Free plan. Upgrade to Plus for unlimited bookmarks.",
                    "upgrade_url": "/pricing",
                }
            )

    # Check for duplicate
    existing = db.query(models.SavedArticle).filter(
        models.SavedArticle.user_id == user_uuid,
        models.SavedArticle.source_type == payload.source_type,
    )
    if payload.source_type == "article" and payload.article_id:
        existing = existing.filter(models.SavedArticle.article_id == payload.article_id)
    elif payload.source_type == "news" and payload.news_article_id:
        existing = existing.filter(models.SavedArticle.news_article_id == payload.news_article_id)

    if existing.first():
        raise HTTPException(status_code=409, detail="Already bookmarked")

    bookmark = models.SavedArticle(
        user_id=user_uuid,
        source_type=payload.source_type,
        article_id=payload.article_id,
        news_article_id=payload.news_article_id,
        news_title=payload.news_title,
        news_slug=payload.news_slug,
        news_image_url=payload.news_image_url,
        news_source=payload.news_source,
    )
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    return {"id": str(bookmark.id), "message": "Bookmarked successfully"}


@app.put("/bookmarks/{bookmark_id}")
def update_bookmark(
    bookmark_id: uuid.UUID,
    payload: BookmarkUpdate,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    """Update bookmark folder/tags/notes — Plus and Pro only."""
    bm = db.query(models.SavedArticle).filter(
        models.SavedArticle.id == bookmark_id,
        models.SavedArticle.user_id == uuid.UUID(current_user.user_id),
    ).first()
    if not bm:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    if payload.folder_id is not None:
        bm.folder_id = payload.folder_id
    if payload.tag_ids is not None:
        bm.tag_ids = payload.tag_ids
    if payload.notes is not None:
        bm.notes = payload.notes

    db.commit()
    return {"message": "Bookmark updated"}


@app.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(
    bookmark_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(verify_token),
):
    """Delete a bookmark."""
    bm = db.query(models.SavedArticle).filter(
        models.SavedArticle.id == bookmark_id,
        models.SavedArticle.user_id == uuid.UUID(current_user.user_id),
    ).first()
    if not bm:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    db.delete(bm)
    db.commit()
    return {"message": "Bookmark removed"}


# ── Folders (Plus+) ───────────────────────────────────────────────────────────

@app.get("/bookmarks/folders")
def get_bookmark_folders(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    folders = db.query(models.BookmarkFolder).filter(
        models.BookmarkFolder.user_id == uuid.UUID(current_user.user_id)
    ).all()
    return [{"id": str(f.id), "name": f.name, "description": f.description, "is_smart": f.is_smart} for f in folders]


@app.post("/bookmarks/folders")
def create_bookmark_folder(
    payload: BookmarkFolderCreate,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    folder = models.BookmarkFolder(
        user_id=uuid.UUID(current_user.user_id),
        name=payload.name,
        description=payload.description,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return {"id": str(folder.id), "name": folder.name}


# ── Tags (Plus+) ──────────────────────────────────────────────────────────────

@app.get("/bookmarks/tags")
def get_bookmark_tags(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    tags = db.query(models.BookmarkTag).filter(
        models.BookmarkTag.user_id == uuid.UUID(current_user.user_id)
    ).all()
    return [{"id": str(t.id), "name": t.name, "color": t.color} for t in tags]


@app.post("/bookmarks/tags")
def create_bookmark_tag(
    payload: BookmarkTagCreate,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    tag = models.BookmarkTag(
        user_id=uuid.UUID(current_user.user_id),
        name=payload.name,
        color=payload.color,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return {"id": str(tag.id), "name": tag.name, "color": tag.color}


# =============================================================================
# FOLLOW LIMIT ENFORCEMENT (Free: 5 topics)
# =============================================================================

@app.post("/public/follow/toggle", response_model=Optional[schemas.FollowResponse])
def toggle_follow_gated(follow: schemas.FollowToggle, db: Session = Depends(get_db)):
    """Follow toggle with free-tier limit enforcement (5 topics max)."""
    from app.core.auth_deps import _get_verified_tier
    import httpx as _httpx

    # Try to get tier if user is authenticated (optional auth here)
    # For now, look up current follow count — we store user_id as string in the model
    existing_follows = crud.get_user_follows(db, follow.user_id)

    # Check if this is an unfollow
    existing = next((f for f in existing_follows if str(f.target_id) == str(follow.target_id)), None)
    if existing:
        # Unfollow — always allowed
        return crud.toggle_follow(db, follow)

    # Following — check free tier limit
    # We pass user_id as string; try to get tier from auth service
    tier = "free"
    try:
        resp = _httpx.get(
            f"{os.environ.get('AUTH_SERVICE_URL', 'http://auth_service:8000')}/internal/tier/{follow.user_id}",
            timeout=2.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("is_active"):
                tier = data.get("tier", "free")
    except Exception:
        pass

    if tier == "free" and len(existing_follows) >= 5:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "follow_limit_exceeded",
                "limit": 5,
                "current": len(existing_follows),
                "message": "Free plan allows following up to 5 topics. Upgrade to Plus for unlimited follows.",
                "upgrade_url": "/pricing",
            }
        )

    return crud.toggle_follow(db, follow)


# =============================================================================
# USAGE STATUS ENDPOINT (for frontend meters)
# =============================================================================

@app.get("/usage/status")
def get_user_usage_status(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(verify_token),
):
    """Proxy to tracking_service usage status for the current user."""
    from app.core.auth_deps import _get_verified_tier
    import httpx as _httpx
    verified_tier = _get_verified_tier(current_user.user_id)
    TRACKING_URL = os.environ.get("TRACKING_SERVICE_URL", "http://tracking_service:8003")
    try:
        resp = _httpx.get(
            f"{TRACKING_URL}/usage/status/{current_user.user_id}",
            params={"tier": verified_tier},
            timeout=3.0,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Usage status proxy error: {e}")
    return {"user_id": current_user.user_id, "tier": verified_tier, "features": {}}


# =============================================================================
# WEEKLY DIGEST API
# =============================================================================

from app.services.premium.digest_service import (
    publish_weekly_digest as _publish_digest,
    personalize_digest,
    _digest_to_dict,
    _current_week_label,
)


@app.get("/digest/latest")
def get_latest_digest(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    """
    Returns the latest published weekly digest.
    Requires Plus or Pro tier.
    Also returns personalized article ordering based on user reading history.
    """
    digest = (
        db.query(models.WeeklyDigest)
        .filter(models.WeeklyDigest.generation_status == "done")
        .order_by(models.WeeklyDigest.published_at.desc())
        .first()
    )
    if not digest:
        raise HTTPException(status_code=404, detail="No digest published yet.")

    # Personalization: read user's recent reading history
    try:
        history = (
            db.query(models.ReadingHistory)
            .filter(models.ReadingHistory.user_id == current_user.user_id)
            .order_by(models.ReadingHistory.read_at.desc())
            .limit(30)
            .all()
        )
        article_ids = [str(h.article_id) for h in history]
        # Get categories from those articles
        articles = db.query(models.Article).filter(
            models.Article.id.in_(article_ids)
        ).all() if article_ids else []
        from collections import Counter
        cat_counts = Counter(a.category_name for a in articles if a.category_name)
        user_top_cats = [cat for cat, _ in cat_counts.most_common(3)]
        return personalize_digest(digest, user_top_cats)
    except Exception:
        return _digest_to_dict(digest)


@app.get("/digest/{week_label}")
def get_digest_by_week(
    week_label: str,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    """Returns a specific week's digest by ISO label (e.g. '2026-W28'). Plus/Pro only."""
    digest = db.query(models.WeeklyDigest).filter(
        models.WeeklyDigest.week_label == week_label
    ).first()
    if not digest:
        raise HTTPException(status_code=404, detail=f"No digest found for {week_label}.")
    return _digest_to_dict(digest)


@app.get("/digest")
def list_digests(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    """List available weekly digests (most recent first). Plus/Pro only."""
    digests = (
        db.query(models.WeeklyDigest)
        .filter(models.WeeklyDigest.generation_status == "done")
        .order_by(models.WeeklyDigest.published_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "week_label":   d.week_label,
            "published_at": d.published_at.isoformat() if d.published_at else None,
            "article_count": d.article_count,
            "news_count":    d.news_count,
        }
        for d in digests
    ]


@app.post("/digest/publish")
async def trigger_digest_publish(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_admin),
):
    """
    Admin-only: manually trigger weekly digest generation.
    Useful for testing in production without waiting for Sunday.
    """
    try:
        digest = await _publish_digest(db)
        return {"status": "ok", "week_label": digest.week_label, "generation_status": digest.generation_status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/digest/opt-out")
def digest_opt_out(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(verify_token),
):
    """Opt the current user out of weekly digest emails."""
    existing = db.query(models.DigestOptOut).filter(
        models.DigestOptOut.user_id == current_user.user_id
    ).first()
    if not existing:
        opt_out = models.DigestOptOut(
            user_id=current_user.user_id,
            email=current_user.email,
        )
        db.add(opt_out)
        db.commit()
    return {"status": "opted_out", "message": "You will no longer receive weekly digest emails."}


@app.delete("/digest/opt-out")
def digest_opt_in(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(verify_token),
):
    """Re-subscribe the current user to weekly digest emails."""
    db.query(models.DigestOptOut).filter(
        models.DigestOptOut.user_id == current_user.user_id
    ).delete()
    db.commit()
    return {"status": "opted_in", "message": "You are now subscribed to weekly digest emails."}


@app.get("/digest/opt-out/status")
def digest_opt_out_status(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(verify_token),
):
    """Check whether the current user has opted out of digest emails."""
    opted_out = db.query(models.DigestOptOut).filter(
        models.DigestOptOut.user_id == current_user.user_id
    ).first() is not None
    return {"opted_out": opted_out}


class OptOutByIdPayload(BaseModel):
    user_id: str


@app.post("/digest/opt-out-by-id")
def digest_opt_out_by_id(payload: OptOutByIdPayload, db: Session = Depends(get_db)):
    """
    Public opt-out endpoint called from the email unsubscribe link.
    Does NOT require authentication — the user_id in the link acts as the identifier.
    In production, sign the URL with a HMAC token for security.
    """
    try:
        uid = uuid.UUID(payload.user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id")

    existing = db.query(models.DigestOptOut).filter(
        models.DigestOptOut.user_id == uid
    ).first()
    if not existing:
        opt_out = models.DigestOptOut(user_id=uid)
        db.add(opt_out)
        db.commit()
    return {"status": "opted_out"}


# =============================================================================
# PROFILE ANALYTICS & TRENDS API (Plus/Pro)
# =============================================================================

@app.get("/profile/analytics")
def get_user_analytics_dashboard(
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(require_tier("plus")),
):
    """
    Returns user reading statistics, top categories (pie charts data), 
    weekly reading history volume, and global trending topics.
    Plus/Pro only.
    """
    user_uuid = uuid.UUID(current_user.user_id)

    # 1. Fetch user's recent reading history (up to 100 entries)
    history = (
        db.query(models.ReadingHistory)
        .filter(models.ReadingHistory.user_id == user_uuid)
        .order_by(models.ReadingHistory.read_at.desc())
        .limit(100)
        .all()
    )

    # 2. Category distribution (Pie Chart data)
    article_ids = [str(h.article_id) for h in history]
    articles = db.query(models.Article).filter(
        models.Article.id.in_(article_ids)
    ).all() if article_ids else []

    from collections import Counter
    cat_counts = Counter(a.category_name for a in articles if a.category_name)
    total_cats = sum(cat_counts.values()) or 1
    category_distribution = [
        {"category": cat, "count": count, "percentage": round((count / total_cats) * 100, 1)}
        for cat, count in cat_counts.most_common(5)
    ]

    # Fill default if empty
    if not category_distribution:
        category_distribution = [
            {"category": "Technology", "count": 12, "percentage": 45.0},
            {"category": "Finance", "count": 8, "percentage": 30.0},
            {"category": "Markets", "count": 5, "percentage": 25.0},
        ]

    # Check actual counts per day and merge with baseline mock
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    activity_volume = []
    base_mocks = {"Mon": 2, "Tue": 4, "Wed": 1, "Thu": 3, "Fri": 2, "Sat": 5, "Sun": 2}
    has_history = len(history) > 0
    for i in range(6, -1, -1):
        day_date = (now_utc - timedelta(days=i)).date()
        day_label = day_date.strftime("%a")  # e.g., Mon, Tue
        # Filter DB history entries for this specific day
        real_count = sum(
            1 for h in history 
            if h.read_at.astimezone(timezone.utc).date() == day_date
        )
        # Use real count, but fallback to mock ONLY if user has absolutely no history
        if has_history:
            count = real_count
        else:
            count = base_mocks.get(day_label, 1)
        activity_volume.append({"day": day_label, "reads": count})

    # 4. Global trending categories/keywords repository-wide
    # Fetch cached global trends to save computation
    global_trends_cache = db.query(models.SystemCache).filter(models.SystemCache.key == "global_trends").first()
    
    if global_trends_cache and global_trends_cache.value:
        global_trends = global_trends_cache.value
    else:
        # Fallback if cache is not populated yet
        from app.services.analytics import calculate_and_cache_global_trends
        calculate_and_cache_global_trends(db)
        global_trends_cache = db.query(models.SystemCache).filter(models.SystemCache.key == "global_trends").first()
        global_trends = global_trends_cache.value if global_trends_cache else []
    
    if not global_trends:
        global_trends = [
            {"topic": "Artificial Intelligence", "rank": 1, "score": 95},
            {"topic": "Global Markets", "rank": 2, "score": 85},
            {"topic": "Climate Tech", "rank": 3, "score": 70},
        ]

    return {
        "category_distribution": category_distribution,
        "activity_volume": activity_volume,
        "global_trends": global_trends,
        "total_reads": len(history),
        "total_reading_minutes": round(sum((h.duration_seconds or 0) for h in history) / 60)
    }




