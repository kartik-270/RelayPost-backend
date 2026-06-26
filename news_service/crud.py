from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, func, String
import models
import schemas
from typing import List, Optional
from datetime import datetime

def get_article_by_url(db: Session, url: str):
    return db.query(models.Article).filter(models.Article.url == url).first()

def create_article(db: Session, article: schemas.ArticleCreate):
    db_article = models.Article(**article.model_dump())
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    return db_article

def get_articles(
    db: Session, 
    skip: int = 0, 
    limit: int = 20, 
    category: Optional[str] = None, 
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    keyword: Optional[str] = None,
    is_verified: Optional[bool] = True
):
    query = db.query(models.Article)

    if category:
        query = query.filter(models.Article.category.ilike(f"%{category}%"))
    
    if start_date:
        query = query.filter(models.Article.published_at >= start_date)
    
    if end_date:
        query = query.filter(models.Article.published_at <= end_date)
        
    if keyword:
        # JSON querying for keywords list or title match
        search = f"%{keyword}%"
        query = query.filter(
            or_(
                models.Article.title.ilike(search),
                models.Article.description.ilike(search),
                func.cast(models.Article.keywords, String).ilike(search)
            )
        )
        
    if is_verified is not None:
        query = query.filter(models.Article.is_verified == is_verified)

    total = query.count()
    items = query.order_by(
        desc(models.Article.title.ilike('%india%')),
        desc(models.Article.description.ilike('%india%')),
        desc(models.Article.published_at)
    ).offset(skip).limit(limit).all()
    
    return items, total

def get_latest_articles(db: Session, limit: int = 50, is_verified: Optional[bool] = True):
    query = db.query(models.Article)
    if is_verified is not None:
        query = query.filter(models.Article.is_verified == is_verified)
    return query.order_by(
        desc(models.Article.title.ilike('%india%')),
        desc(models.Article.description.ilike('%india%')),
        desc(models.Article.published_at)
    ).limit(limit).all()

def get_clustered_articles(db: Session, cluster_id: int, is_verified: Optional[bool] = True):
    query = db.query(models.Article).filter(models.Article.cluster_id == cluster_id)
    if is_verified is not None:
        query = query.filter(models.Article.is_verified == is_verified)
    return query.all()

def get_article_by_id(db: Session, article_id: int, is_verified: Optional[bool] = None):
    query = db.query(models.Article).filter(models.Article.id == article_id)
    if is_verified is not None:
        query = query.filter(models.Article.is_verified == is_verified)
    return query.first()

def get_article_by_slug(db: Session, slug: str, is_verified: Optional[bool] = None):
    query = db.query(models.Article).filter(models.Article.slug == slug)
    if is_verified is not None:
        query = query.filter(models.Article.is_verified == is_verified)
    article = query.first()
    
    if not article and slug.isdigit():
        query2 = db.query(models.Article).filter(models.Article.id == int(slug))
        if is_verified is not None:
            query2 = query2.filter(models.Article.is_verified == is_verified)
        article = query2.first()

    if article and article.cluster_id:
        query_related = db.query(models.Article).filter(
            models.Article.cluster_id == article.cluster_id,
            models.Article.id != article.id
        )
        if is_verified is not None:
            query_related = query_related.filter(models.Article.is_verified == is_verified)
        related = query_related.all()
        # Create a dict that matches ArticleWithSources schema
        article_dict = {c.name: getattr(article, c.name) for c in article.__table__.columns}
        article_dict['related_sources'] = [
            {"id": r.id, "source_name": r.source_name, "url": r.url} for r in related
        ]
        return article_dict
    elif article:
        article_dict = {c.name: getattr(article, c.name) for c in article.__table__.columns}
        article_dict['related_sources'] = []
        return article_dict
    return None


def get_unique_categories(db: Session):
    categories = db.query(models.Article.category).distinct().all()
    # Flatten list of tuples [(cat1,), (cat2,)] to [cat1, cat2]
    return [c[0] for c in categories if c[0]]
