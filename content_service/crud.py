from sqlalchemy.orm import Session
from sqlalchemy import or_, func
import schemas
from schemas import ArticleCreate, ArticleUpdate, CategoryBase, KeywordBase
import models
import uuid
from datetime import datetime, timezone
import re
import collections

# --- Categories & Keywords ---

def get_categories(db: Session):
    return db.query(models.Category).all()

def get_or_create_category(db: Session, name: str):
    if not name: return None
    db_category = db.query(models.Category).filter(func.lower(models.Category.name) == name.lower()).first()
    if not db_category:
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        db_category = models.Category(name=name, slug=slug)
        db.add(db_category)
        db.commit()
        db.refresh(db_category)
    return db_category

def create_category(db: Session, category: CategoryBase):
    db_category = models.Category(**category.model_dump())
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

def get_keywords(db: Session):
    return db.query(models.Keyword).all()

def get_or_create_keyword(db: Session, tag: str):
    if not tag: return None
    db_keyword = db.query(models.Keyword).filter(func.lower(models.Keyword.tag) == tag.lower()).first()
    if not db_keyword:
        db_keyword = models.Keyword(tag=tag)
        db.add(db_keyword)
        db.commit()
        db.refresh(db_keyword)
    return db_keyword

def create_keyword(db: Session, keyword: KeywordBase):
    db_keyword = models.Keyword(**keyword.model_dump())
    db.add(db_keyword)
    db.commit()
    db.refresh(db_keyword)
    return db_keyword

# --- Articles ---

def get_article(db: Session, article_id: uuid.UUID):
    # Using visibility or status instead of is_deleted if we dropped is_deleted
    return db.query(models.Article).filter(models.Article.id == article_id).first()

def get_article_by_slug(db: Session, slug: str):
    return db.query(models.Article).filter(models.Article.slug == slug).first()

def get_articles(db: Session, skip: int = 0, limit: int = 100, status: models.ArticleStatus = None):
    query = db.query(models.Article)
    if status:
        query = query.filter(models.Article.status == status)
    return query.order_by(models.Article.created_at.desc()).offset(skip).limit(limit).all()

def create_article(db: Session, article: ArticleCreate):
    # Separate the complex relational fields
    article_data = article.model_dump(exclude={'category_id', 'category_name', 'keyword_ids'})
    
    db_article = models.Article(**article_data)
    
    # Handle Category
    if article.category_name:
        cat = get_or_create_category(db, article.category_name)
        db_article.category_id = cat.id
    elif article.category_id:
        db_article.category_id = article.category_id

    # Handle Keywords (Association Table + Strings)
    if article.secondary_keywords:
        for kw_tag in article.secondary_keywords:
            get_or_create_keyword(db, kw_tag)
    
    # Handle Status/Publish defaults
    if not db_article.status:
        db_article.status = models.ArticleStatus.DRAFT
    if db_article.status == models.ArticleStatus.PUBLISHED and not db_article.published_at:
        db_article.published_at = datetime.now(timezone.utc)
        
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    
    return db_article

def update_article(db: Session, db_article: models.Article, update_data: ArticleUpdate):
    update_dict = update_data.model_dump(exclude_unset=True, exclude={'category_name'})
    
    if update_data.category_name:
        cat = get_or_create_category(db, update_data.category_name)
        db_article.category_id = cat.id
    
    for key, value in update_dict.items():
        setattr(db_article, key, value)
    
    if update_data.status == models.ArticleStatus.PUBLISHED and db_article.published_at is None:
        db_article.published_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(db_article)
    return db_article
        
import re

# --- Media ---

def create_media(db: Session, filename: str, content_type: str, data: bytes, size: int, article_id: uuid.UUID = None):
    db_media = models.Media(
        filename=filename,
        content_type=content_type,
        data=data,
        size=size,
        article_id=article_id
    )
    db.add(db_media)
    db.commit()
    db.refresh(db_media)
    return db_media

def get_media(db: Session, media_id: uuid.UUID):
    return db.query(models.Media).filter(models.Media.id == media_id).first()

def get_all_media(db: Session, skip: int = 0, limit: int = 50):
    return db.query(models.Media).order_by(models.Media.created_at.desc()).offset(skip).limit(limit).all()

# --- User Contributions ---

def create_user_contribution(db: Session, user_id: uuid.UUID, data: schemas.UserContributionCreate):
    db_contribution = models.UserContribution(
        user_id=user_id,
        **data.model_dump()
    )
    db.add(db_contribution)
    db.commit()
    db.refresh(db_contribution)
    return db_contribution

def get_user_contributions(db: Session, skip: int = 0, limit: int = 20, status: str = None):
    query = db.query(models.UserContribution)
    if status:
        query = query.filter(models.UserContribution.status == status)
    return query.order_by(models.UserContribution.created_at.desc()).offset(skip).limit(limit).all()

def update_contribution_status(db: Session, contribution_id: uuid.UUID, status: str, admin_notes: str = None):
    db_contribution = db.query(models.UserContribution).filter(models.UserContribution.id == contribution_id).first()
    if db_contribution:
        db_contribution.status = status
        if admin_notes:
            db_contribution.admin_notes = admin_notes
        db.commit()
        db.refresh(db_contribution)
    return db_contribution

# --- Suggestions ---

def suggest_keywords(db: Session, text: str):
    # 1. Get all known keyword tags
    all_keywords = db.query(models.Keyword).all()
    suggestions = []
    
    # 2. Look for matches in the text (case-insensitive)
    text_lower = text.lower()
    for kw in all_keywords:
        if kw.tag.lower() in text_lower:
            suggestions.append({"tag": kw.tag, "score": 1.0})
            
    # 3. Frequency based fallback for new potential tags (simple)
    words = re.findall(r'\w+', text_lower)
    common = collections.Counter(words).most_common(10)
    for word, count in common:
        if len(word) > 4 and not any(s["tag"].lower() == word for s in suggestions):
            suggestions.append({"tag": word.capitalize(), "score": 0.5})
            
    return suggestions[:15]

def suggest_links(db: Session, article_id: uuid.UUID):
    # Find articles that share categories with the current one
    current_article = get_article(db, article_id)
    if not current_article:
        return []
        
    # Simplified logic: find articles in the same approximate space (first few tags or categories)
    # Since associations aren't fully linked in the existing CRUD, we'll just get recent published ones
    return db.query(models.Article)\
             .filter(models.Article.id != article_id)\
             .filter(models.Article.status == models.ArticleStatus.PUBLISHED)\
             .order_by(models.Article.published_at.desc())\
             .limit(5).all()

def delete_article(db: Session, db_article: models.Article):
    db_article.status = models.ArticleStatus.ARCHIVED
    db.commit()
    return db_article

# --- Interactions ---

def add_view(db: Session, article_id: uuid.UUID):
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if article:
        article.views_count += 1
        db.commit()
    return article

def toggle_like(db: Session, article_id: uuid.UUID, user_id: uuid.UUID):
    existing_like = db.query(models.ArticleLike).filter(
        models.ArticleLike.article_id == article_id,
        models.ArticleLike.user_id == user_id
    ).first()
    
    if existing_like:
        db.delete(existing_like)
        liked = False
    else:
        new_like = models.ArticleLike(article_id=article_id, user_id=user_id)
        db.add(new_like)
        liked = True
    
    db.commit()
    return liked

def add_reflection(db: Session, article_id: uuid.UUID, data: schemas.ReflectionCreate):
    db_reflection = models.Reflection(article_id=article_id, **data.model_dump())
    db.add(db_reflection)
    db.commit()
    db.refresh(db_reflection)
    return db_reflection

# --- Homepage & Discovery ---

def get_articles_by_section(db: Session, section: str, limit: int = 10):
    return db.query(models.Article)\
             .filter(models.Article.status == models.ArticleStatus.PUBLISHED)\
             .filter(func.lower(models.Article.homepage_section) == section.lower())\
             .order_by(models.Article.section_order.asc(), models.Article.published_at.desc())\
             .limit(limit).all()

def get_article_with_interactions(db: Session, slug: str):
    article = db.query(models.Article).filter(models.Article.slug == slug).first()
    if article:
        # Pydantic will handle the counting via relationship length if defined or we manually count
        # For simplicity, we just return the article object and let schemas filter
        pass
    return article
