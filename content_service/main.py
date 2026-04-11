import os
import time
import httpx
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import uuid
from typing import List, Optional

import crud, models, schemas
from database import engine, get_db
from auth_deps import verify_token, get_current_publisher, get_current_admin, TokenData
from automation.scheduler import automation_scheduler


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
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemma-3-27b-it')
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

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
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
    # Start the automation scheduler
    automation_scheduler.start()

@app.on_event("shutdown")
async def shutdown_event():
    # Clean shutdown
    automation_scheduler.shutdown()

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
def record_view(article_id: uuid.UUID, db: Session = Depends(get_db)):
    crud.add_view(db, article_id)
    return {"message": "View recorded"}

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
    return crud.get_keywords(db)

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

from fastapi import BackgroundTasks
from automation.engine import ArticleAutomationEngine

@app.post("/admin/ai/trigger-automation")
async def trigger_automation_manually(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    batch_size = int(os.getenv("AUTOMATION_BATCH_SIZE", "1"))
    
    async def run_engine():
        engine = ArticleAutomationEngine(db)
        await engine.run_pipeline(batch_size=batch_size)
        
    background_tasks.add_task(run_engine)
    return {"message": f"Automation triggered in background for {batch_size} articles."}


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

@app.get("/admin/articles", response_model=List[schemas.ArticleResponse])
def get_all_articles(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    return crud.get_articles(db, skip=skip, limit=limit)

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

@app.get("/admin/inquiries/notifications")
def get_inquiry_notifications(db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    unread_count = crud.count_unread_inquiries(db)
    inquiries = crud.get_unread_inquiries(db, limit=5)
    return {
        "unread_count": unread_count,
        "recent_inquiries": [schemas.ContactInquiryResponse.from_attributes(i) for i in inquiries]
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
