from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.crud import crud
from app.schemas import schemas
from app.core.database import get_db
import requests

router = APIRouter()

@router.post("/admin/engine/pause")
def pause_engine():
    """Pause the automated news ingestion job"""
    try:
        response = requests.post("http://news_generation_service:8004/api/news/admin/engine/pause")
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/admin/engine/resume")
def resume_engine():
    """Resume the automated news ingestion job"""
    try:
        response = requests.post("http://news_generation_service:8004/api/news/admin/engine/resume")
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/admin/engine/trigger")
def trigger_engine():
    """Manually trigger the news ingestion job once"""
    try:
        response = requests.post("http://news_generation_service:8004/api/news/admin/engine/trigger")
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/live")
def get_live_feed(
    skip: int = 0, limit: int = 20, search: Optional[str] = None, is_admin: bool = False, db: Session = Depends(get_db)
):
    """Get the most recent unstructured live feed of news"""
    from fastapi.responses import JSONResponse
    is_verified = None if is_admin else True
    articles = crud.get_latest_articles(db, limit=limit, skip=skip, is_verified=is_verified, search=search)
    total = crud.count_articles(db, is_verified=is_verified, search=search)
    return JSONResponse(
        content=[{c.name: getattr(a, c.name).__str__() if not isinstance(getattr(a, c.name), (str, int, float, bool, type(None), list)) else getattr(a, c.name) for c in a.__table__.columns} for a in articles],
        headers={"X-Total-Count": str(total), "Access-Control-Expose-Headers": "X-Total-Count"}
    )

@router.get("/categories/{category}", response_model=schemas.ArticlePaginated)
def get_category_news(
    category: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get news by category"""
    items, total = crud.get_articles(db, skip=skip, limit=limit, category=category)
    return schemas.ArticlePaginated(
        items=items,
        total=total,
        page=skip // limit + 1,
        size=limit,
        pages=(total + limit - 1) // limit
    )

@router.get("/time", response_model=schemas.ArticlePaginated)
def get_time_based_news(
    start_date: datetime,
    end_date: datetime,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get news within a specific timeframe"""
    items, total = crud.get_articles(db, skip=skip, limit=limit, start_date=start_date, end_date=end_date)
    return schemas.ArticlePaginated(
        items=items,
        total=total,
        page=skip // limit + 1,
        size=limit,
        pages=(total + limit - 1) // limit
    )

@router.get("/keywords/{keyword}", response_model=schemas.ArticlePaginated)
def get_keyword_news(
    keyword: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get news matching a specific keyword"""
    items, total = crud.get_articles(db, skip=skip, limit=limit, keyword=keyword)
    return schemas.ArticlePaginated(
        items=items,
        total=total,
        page=skip // limit + 1,
        size=limit,
        pages=(total + limit - 1) // limit
    )

@router.get("/clusters/{cluster_id}", response_model=List[schemas.Article])
def get_grouped_news(
    cluster_id: int,
    db: Session = Depends(get_db)
):
    """Get all news within a specific group/cluster"""
    return crud.get_clustered_articles(db, cluster_id=cluster_id)

@router.get("/slug/{slug}", response_model=schemas.ArticleWithSources)
def get_news_by_slug(slug: str, db: Session = Depends(get_db)):
    """Get a single news article by its slug"""
    article = crud.get_article_by_slug(db, slug=slug, is_verified=True)
    if not article:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="News article not found")
    return article

@router.get("/id/{article_id}", response_model=schemas.Article)
def get_news_by_id(article_id: int, is_admin: bool = False, db: Session = Depends(get_db)):
    """Get a single news article by its ID"""
    article = crud.get_article_by_id(db, article_id=article_id, is_verified=None if is_admin else True)
    if not article:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="News article not found")
    return article

@router.put("/admin/{article_id}", response_model=schemas.Article)
def update_news_article(article_id: int, article_update: schemas.ArticleCreate, db: Session = Depends(get_db)):
    """Update a news article (CMS)"""
    db_article = crud.get_article_by_id(db, article_id=article_id)
    if not db_article:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="News article not found")
        
    for key, value in article_update.model_dump().items():
        setattr(db_article, key, value)
        
    db.commit()
    db.refresh(db_article)
    return db_article

@router.delete("/admin/{article_id}")
def delete_news_article(article_id: int, db: Session = Depends(get_db)):
    """Delete a news article (CMS)"""
    db_article = crud.get_article_by_id(db, article_id=article_id)
    if not db_article:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="News article not found")
        
    db.delete(db_article)
    db.commit()
    return {"message": "News article deleted successfully"}

@router.get("/meta/categories", response_model=List[str])
def get_news_categories(db: Session = Depends(get_db)):
    """Get all unique news categories"""
    return crud.get_unique_categories(db)



@router.get("/rss")
def get_rss_feed(db: Session = Depends(get_db)):
    from fastapi import Response
    from feedgen.feed import FeedGenerator
    
    fg = FeedGenerator()
    fg.title('RelayPost Intelligence Feed')
    fg.link(href='https://relaypost.app', rel='alternate')
    fg.description('Live, synthesized, and verified news from RelayPost AI.')
    
    # Get recent verified news
    items, _ = crud.get_articles(db, limit=30, is_verified=True)
    
    for item in items:
        fe = fg.add_entry()
        fe.title(item.title)
        fe.link(href=f"https://relaypost.app/news/{item.slug}" if item.slug else item.url)
        fe.description(item.ai_summary or item.description or "")
        if item.published_at:
            import pytz
            dt = item.published_at.replace(tzinfo=pytz.UTC)
            fe.pubDate(dt)
            
    rss_xml = fg.rss_str(pretty=True)
    return Response(content=rss_xml, media_type="application/xml")

@router.post("/id/{article_id}/view")
def increment_news_view(article_id: int, db: Session = Depends(get_db)):
    """Increment the view count of a news article"""
    article = crud.get_article_by_id(db, article_id=article_id)
    if not article:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="News article not found")
    article.views = (article.views or 0) + 1
    db.commit()
    db.refresh(article)
    return {"status": "ok", "views": article.views}

@router.get("/top", response_model=List[schemas.Article])
def get_top_news():
    """Get the cached top 5 news articles based on views"""
    from app.services.cache import get_top_news_from_cache
    return get_top_news_from_cache()
