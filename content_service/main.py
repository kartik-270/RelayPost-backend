import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uuid
from typing import List, Optional

import crud, models, schemas
from database import engine, get_db
from auth_deps import verify_token, get_current_publisher, get_current_admin, TokenData

try:
    models.Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Startup Warning: Database table creation failed (expected if DB is still starting): {e}")

app = FastAPI(title="Advanced CMS Service")

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
MEDIA_BASE_URL = os.environ.get("MEDIA_BASE_URL", "http://localhost:8001")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- PUBLIC ENDPOINTS ---

@app.get("/public/articles/trending", response_model=List[schemas.ArticleResponse])
def get_trending_articles(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    # Using 'is_featured' and 'PUBLISHED' status to get top articles
    query = db.query(models.Article).filter(models.Article.status == models.ArticleStatus.PUBLISHED, models.Article.is_featured == True)
    return query.order_by(models.Article.published_at.desc()).offset(skip).limit(limit).all()

@app.get("/public/articles", response_model=List[schemas.ArticleResponse])
def get_public_articles(skip: int = 0, limit: int = 20, template: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Article).filter(models.Article.status == models.ArticleStatus.PUBLISHED)
    if template:
        query = query.filter(models.Article.template_type == template)
    return query.order_by(models.Article.published_at.desc()).offset(skip).limit(limit).all()

@app.get("/public/articles/section/{section}", response_model=List[schemas.ArticleResponse])
def get_articles_by_section(section: str, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_articles_by_section(db, section=section, limit=limit)

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

# --- USER CONTRIBUTION ENDPOINTS ---

@app.post("/public/contributions", response_model=schemas.UserContributionResponse)
def submit_contribution(contribution: schemas.UserContributionCreate, db: Session = Depends(get_db), current_user: TokenData = Depends(verify_token)):
    return crud.create_user_contribution(db, uuid.UUID(current_user.user_id), contribution)

@app.get("/admin/contributions", response_model=List[schemas.UserContributionResponse])
def list_contributions(skip: int = 0, limit: int = 50, status: str = None, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_admin)):
    return crud.get_user_contributions(db, skip=skip, limit=limit, status=status)

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
    return crud.update_article(db=db, db_article=db_article, update_data=update_data)

@app.delete("/admin/articles/{article_id}")
def archive_article(article_id: uuid.UUID, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    db_article = crud.get_article(db, article_id=article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    crud.delete_article(db, db_article)
    return {"message": "Article archived successfully"}

@app.put("/admin/articles/{article_id}/placement")
def update_article_placement(article_id: uuid.UUID, placement: dict, db: Session = Depends(get_db), current_user: TokenData = Depends(get_current_publisher)):
    db_article = crud.get_article(db, article_id=article_id)
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    db_article.homepage_section = placement.get("section")
    db_article.section_order = placement.get("order", 0)
    db.commit()
    return {"message": "Placement updated"}
