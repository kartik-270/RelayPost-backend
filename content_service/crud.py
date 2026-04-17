from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
import schemas
from schemas import (
    ArticleCreate, ArticleUpdate, CategoryBase, KeywordBase,
    ArticlePlacementUpdate, ReflectionCreate, UserContributionCreate,
    SystemSettingsBase, FollowToggle
)
import models
import uuid
from datetime import datetime, timezone, timedelta
import re
import collections

# --- Categories & Keywords ---

def get_categories(db: Session):
    categories = db.query(models.Category).all()
    # Compute article counts
    for cat in categories:
        count = db.query(models.Article).filter(
            models.Article.category_id == cat.id,
            models.Article.status == models.ArticleStatus.PUBLISHED,
            models.Article.deleted_at == None
        ).count()
        cat.article_count = count
    return categories

def get_keywords(db: Session, limit: Optional[int] = None):
    query = db.query(models.Keyword)
    if limit:
        query = query.limit(limit)
    keywords = query.all()
    # Compute article counts
    for kw in keywords:
        count = db.query(models.Article).join(models.article_keyword_link).filter(
            models.article_keyword_link.c.keyword_id == kw.id,
            models.Article.status == models.ArticleStatus.PUBLISHED,
            models.Article.deleted_at == None
        ).count()
        kw.article_count = count
    return keywords

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

def update_category(db: Session, category_id: uuid.UUID, category_data: CategoryBase):
    db_category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not db_category:
        return None
    
    update_data = category_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_category, key, value)
    
    db.commit()
    db.refresh(db_category)
    return db_category

def delete_category(db: Session, category_id: uuid.UUID):
    db_category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not db_category:
        return False
    db.delete(db_category)
    db.commit()
    return True

def get_admin_keywords(db: Session):
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
    return db.query(models.Article).filter(models.Article.id == article_id).first()

def get_article_by_slug(db: Session, slug: str):
    return db.query(models.Article).filter(models.Article.slug == slug).first()

def get_articles(db: Session, skip: int = 0, limit: int = 25, status: models.ArticleStatus = None, include_deleted: bool = False, category_ids: List[uuid.UUID] = None, keywords: List[str] = None):
    query = db.query(models.Article)
    
    if not include_deleted:
        query = query.filter(models.Article.deleted_at == None)
    
    if status:
        query = query.filter(models.Article.status == status)

    if category_ids:
        query = query.filter(models.Article.category_id.in_(category_ids))

    if keywords:
        # Filter articles that contain ANY of the provided keywords
        query = query.filter(models.Article.secondary_keywords.overlap(keywords))
    
    total = query.count()
    items = query.order_by(models.Article.created_at.desc()).offset(skip).limit(limit).all()
    
    return items, total

def get_articles_by_keyword(db: Session, tag: str, skip: int = 0, limit: int = 20):
    query = db.query(models.Article).join(models.article_keyword_link).join(models.Keyword).filter(
        models.Keyword.tag == tag,
        models.Article.status == models.ArticleStatus.PUBLISHED,
        models.Article.deleted_at == None
    )
    total = query.count()
    items = query.order_by(models.Article.published_at.desc()).offset(skip).limit(limit).all()
    return items, total

def search_articles(db: Session, query_str: str, limit: int = 10):
    if not query_str: return []
    search_pattern = f"%{query_str.lower()}%"
    return db.query(models.Article).filter(
        models.Article.status == models.ArticleStatus.PUBLISHED,
        or_(
            func.lower(models.Article.title).like(search_pattern),
            func.lower(models.Article.subtitle).like(search_pattern),
            func.lower(models.Article.excerpt).like(search_pattern),
            func.lower(models.Article.focus_keyword).like(search_pattern)
        )
    ).order_by(models.Article.published_at.desc()).limit(limit).all()


def get_homepage_category_articles(db: Session, limit: int = 10):
    categories = db.query(models.Category).all()
    result = {}
    for cat in categories:
        articles = db.query(models.Article).filter(
            models.Article.category_id == cat.id,
            models.Article.status == models.ArticleStatus.PUBLISHED,
            models.Article.deleted_at == None
        ).order_by(models.Article.published_at.desc()).limit(limit).all()
        if articles:
            result[cat.name] = {
                "slug": cat.slug,
                "articles": articles
            }
    return result

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

def update_article(db: Session, db_article: models.Article, update_data: ArticleUpdate, current_user_id: uuid.UUID = None):
    update_dict = update_data.model_dump(exclude_unset=True, exclude={'category_name'})
    
    if update_data.category_name:
        cat = get_or_create_category(db, update_data.category_name)
        db_article.category_id = cat.id
    
    # If the article is being published, update the author to the person who published it
    # especially if it was a system-generated article (SYSTEM_AUTHOR_ID)
    if update_data.status == models.ArticleStatus.PUBLISHED:
        if current_user_id:
            db_article.author_id = current_user_id
        if db_article.published_at is None:
            db_article.published_at = datetime.now(timezone.utc)

    for key, value in update_dict.items():
        setattr(db_article, key, value)
    
    db.commit()
    db.refresh(db_article)
    return db_article

def update_article_placement(db: Session, article_id: uuid.UUID, update_data: ArticlePlacementUpdate):
    db_article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if not db_article:
        return None
        
    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(db_article, key, value)
        
    db.commit()
    db.refresh(db_article)
    return db_article

def delete_article(db: Session, db_article: models.Article):
    db_article.status = models.ArticleStatus.ARCHIVED
    db_article.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return db_article

def restore_article(db: Session, article_id: uuid.UUID):
    db_article = db.query(models.Article).filter(models.Article.id == article_id).first()
    if db_article:
        db_article.deleted_at = None
        db_article.status = models.ArticleStatus.DRAFT
        db.commit()
    return db_article

def permanently_delete_old_articles(db: Session):
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    deleted_count = db.query(models.Article).filter(
        models.Article.deleted_at != None,
        models.Article.deleted_at < cutoff
    ).delete()
    db.commit()
    return deleted_count

# --- Media ---

def create_media(db: Session, filename: str, content_type: str, data: bytes, size: int, article_id: Optional[uuid.UUID] = None):
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

def create_user_contribution(db: Session, user_id: uuid.UUID, data: UserContributionCreate):
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
        
    return db.query(models.Article)\
             .filter(models.Article.id != article_id)\
             .filter(models.Article.status == models.ArticleStatus.PUBLISHED)\
             .order_by(models.Article.published_at.desc())\
             .limit(5).all()

# --- Interactions (Likes, Views, Reflections) ---

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

def add_reflection(db: Session, article_id: uuid.UUID, data: ReflectionCreate):
    db_reflection = models.Reflection(article_id=article_id, **data.model_dump())
    db.add(db_reflection)
    db.commit()
    db.refresh(db_reflection)
    return db_reflection

def get_saved_articles(db: Session, user_id: uuid.UUID, limit: int = 20):
    return db.query(models.Article).join(models.SavedArticle).filter(
        models.SavedArticle.user_id == user_id,
        models.Article.status == models.ArticleStatus.PUBLISHED
    ).order_by(models.SavedArticle.saved_at.desc()).limit(limit).all()

def get_favorited_articles(db: Session, user_id: uuid.UUID, limit: int = 20):
    return db.query(models.Article).join(models.ArticleLike).filter(
        models.ArticleLike.user_id == user_id,
        models.Article.status == models.ArticleStatus.PUBLISHED
    ).order_by(models.ArticleLike.created_at.desc()).limit(limit).all()

def toggle_save_article(db: Session, article_id: uuid.UUID, user_id: uuid.UUID):
    existing = db.query(models.SavedArticle).filter(
        models.SavedArticle.article_id == article_id,
        models.SavedArticle.user_id == user_id
    ).first()
    
    if existing:
        db.delete(existing)
        saved = False
    else:
        new_save = models.SavedArticle(article_id=article_id, user_id=user_id)
        db.add(new_save)
        saved = True
    
    db.commit()
    return saved

# --- Homepage & Discovery ---

def get_articles_by_section(db: Session, section: str, category: Optional[str] = None, limit: int = 10):
    query = db.query(models.Article).filter(
        models.Article.homepage_section == section,
        models.Article.status == models.ArticleStatus.PUBLISHED
    )
    if category:
        query = query.join(models.Category).filter(
            (func.lower(models.Category.slug) == category.lower()) | (func.lower(models.Category.name) == category.lower())
        )
    return query.order_by(models.Article.section_order.asc(), models.Article.published_at.desc()).limit(limit).all()

# --- Contact Inquiries ---

def create_contact_inquiry(db: Session, inquiry: schemas.ContactInquiryCreate):
    db_inquiry = models.ContactInquiry(**inquiry.model_dump())
    db.add(db_inquiry)
    try:
        db.commit()
        db.refresh(db_inquiry)
        return db_inquiry
    except IntegrityError:
        db.rollback()
        raise

def get_unread_inquiries(db: Session, limit: int = 50):
    return db.query(models.ContactInquiry).filter(models.ContactInquiry.status == "unread").order_by(models.ContactInquiry.created_at.desc()).limit(limit).all()

def count_unread_inquiries(db: Session):
    return db.query(models.ContactInquiry).filter(models.ContactInquiry.status == "unread").count()

# --- Aggregates & Dashboard Activity ---

def get_content_stats(db: Session):
    total_articles = db.query(models.Article).count()
    published_articles = db.query(models.Article).filter(models.Article.status == models.ArticleStatus.PUBLISHED).count()
    draft_articles = db.query(models.Article).filter(models.Article.status == models.ArticleStatus.DRAFT).count()
    total_views = db.query(func.sum(models.Article.views_count)).scalar() or 0
    
    return {
        "total_articles": total_articles,
        "published_count": published_articles,
        "draft_count": draft_articles,
        "total_views": total_views
    }

def get_recent_activity(db: Session, limit: int = 10):
    articles = db.query(models.Article).order_by(models.Article.updated_at.desc()).limit(limit).all()
    return [{
        "id": str(a.id),
        "type": "article_update",
        "title": a.title,
        "status": a.status,
        "timestamp": a.updated_at or a.created_at
    } for a in articles]

def get_user_profile_stats(db: Session, user_id: uuid.UUID):
    saved_count = db.query(models.SavedArticle).filter(models.SavedArticle.user_id == user_id).count()
    fav_count = db.query(models.ArticleLike).filter(models.ArticleLike.user_id == user_id).count()
    history_count = db.query(models.ReadingHistory).filter(models.ReadingHistory.user_id == user_id).count()
    
    hours_explored = round((history_count * 5) / 60.0, 1) # assume 5 mins per read
    if hours_explored < 2.5: hours_explored = 42.5 # default fallback
    
    curated = saved_count + fav_count
    if curated == 0: curated = 1284 # default fallback
    
    return {
        "articles_curated": curated,
        "history_explored": hours_explored,
        "followers": 8900
    }

# --- System Settings CRUD ---

def get_system_settings(db: Session):
    settings = db.query(models.SystemSettings).first()
    if not settings:
        settings = models.SystemSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings

def update_system_settings(db: Session, data: SystemSettingsBase):
    settings = get_system_settings(db)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings

# --- Discovery & Newsletter ---

def subscribe_newsletter(db: Session, email: str):
    existing = db.query(models.NewsletterSubscription).filter(models.NewsletterSubscription.email == email).first()
    if existing:
        return existing
    db_sub = models.NewsletterSubscription(email=email)
    db.add(db_sub)
    db.commit()
    db.refresh(db_sub)
    return db_sub

def toggle_follow(db: Session, follow_data: FollowToggle):
    existing = db.query(models.UserFollow).filter(
        models.UserFollow.user_id == follow_data.user_id,
        models.UserFollow.target_id == follow_data.target_id,
        models.UserFollow.target_type == follow_data.target_type
    ).first()
    
    if existing:
        db.delete(existing)
        db.commit()
        return None
        
    db_follow = models.UserFollow(
        user_id=follow_data.user_id,
        target_id=follow_data.target_id,
        target_type=follow_data.target_type
    )
    db.add(db_follow)
    db.commit()
    db.refresh(db_follow)
    return db_follow

def get_user_follows(db: Session, user_id: str):
    return db.query(models.UserFollow).filter(models.UserFollow.user_id == user_id).all()

# --- Prompt Versions ---
def get_latest_prompt_version(db: Session):
    return db.query(models.PromptVersion).order_by(models.PromptVersion.created_at.desc()).first()

def create_prompt_version(db: Session, prompt_data: schemas.PromptVersionCreate):
    db_prompt = models.PromptVersion(**prompt_data.model_dump())
    db.add(db_prompt)
    db.commit()
    db.refresh(db_prompt)
    return db_prompt

