import enum
import uuid
from sqlalchemy import Column, String, Boolean, Enum, DateTime, ForeignKey, Integer, Float, Table, func, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from app.core.database import Base

class ArticleStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    REJECTED = "rejected"

class TemplateType(str, enum.Enum):
    STANDARD = "standard"
    NEWS = "news"
    TECH = "tech"
    SEO_BLOG = "seo_blog"
    GUIDE = "guide"
    TREND = "trend"

class ThemeType(str, enum.Enum):
    STANDARD = "standard"
    INTELLIGENCE = "intelligence"
    SPORTS = "sports"

class NotificationType(str, enum.Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

# Constants
SYSTEM_AUTHOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

# Association Tables for Many-to-Many Relationships
article_category_link = Table(
    'article_category_link',
    Base.metadata,
    Column('article_id', UUID(as_uuid=True), ForeignKey('articles.id'), primary_key=True),
    Column('category_id', UUID(as_uuid=True), ForeignKey('categories.id'), primary_key=True)
)

article_keyword_link = Table(
    'article_keyword_link',
    Base.metadata,
    Column('article_id', UUID(as_uuid=True), ForeignKey('articles.id'), primary_key=True),
    Column('keyword_id', UUID(as_uuid=True), ForeignKey('keywords.id'), primary_key=True)
)

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    image_url = Column(String, nullable=True)

class Keyword(Base):
    __tablename__ = "keywords"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tag = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)

class Article(Base):
    __tablename__ = "articles"

    # Core Fields
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False) # H1
    slug = Column(String, unique=True, index=True, nullable=False)
    subtitle = Column(String, nullable=True) # Tagline
    author_id = Column(UUID(as_uuid=True), index=True, nullable=False) # from auth_service
    hero_image = Column(String, nullable=True) # Featured Image
    excerpt = Column(String, nullable=True) # Summary
    
    # Structure & Sections
    template_type = Column(Enum(TemplateType), default=TemplateType.STANDARD, nullable=False)
    content_blocks = Column(JSONB, nullable=False, default=list) # H2, Text, Quotes, Tables, etc.
    media_gallery = Column(JSONB, default=list) # Infographics, video embeds, GIFs
    
    # SEO Sections
    meta_title = Column(String, nullable=True)
    meta_description = Column(String, nullable=True)
    focus_keyword = Column(String, nullable=True)
    secondary_keywords = Column(ARRAY(String), default=list) # Text array
    canonical_url = Column(String, nullable=True)
    schema_markup = Column(JSONB, default=dict) # FAQ, Article Schema
    
    # GEO / AI SEO
    ai_summary = Column(String, nullable=True)
    key_takeaways = Column(JSONB, default=list)
    faq_section = Column(JSONB, default=list)
    
    # Admin / Backend Fields
    status = Column(Enum(ArticleStatus, native_enum=False), default=ArticleStatus.DRAFT, nullable=False)
    visibility = Column(String, default="public") # public/private
    is_featured = Column(Boolean, default=False) # Feature on homepage
    
    # Homepage Layout Management
    homepage_section = Column(String, nullable=True) # e.g. "TrendingNow", "ExpertAnalysis"
    section_order = Column(Integer, default=0) # Positioning within the section
    
    # Interactions
    views_count = Column(Integer, default=0)
    theme = Column(Enum(ThemeType, native_enum=False), default=ThemeType.STANDARD, nullable=False)
    
    # Timestamps
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


    # Relationships
    category_id = Column(UUID(as_uuid=True), ForeignKey('categories.id'), nullable=True)
    category = relationship("Category")
    
    @property
    def category_name(self):
        return self.category.name if self.category else None

    media_refs = relationship("Media", back_populates="article", cascade="all, delete-orphan")
    reflections = relationship("Reflection", back_populates="article", cascade="all, delete-orphan")
    likes = relationship("ArticleLike", back_populates="article", cascade="all, delete-orphan")

class Media(Base):
    __tablename__ = "media"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    data = Column(LargeBinary, nullable=False) # The actual file bytes
    size = Column(Integer, nullable=False)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    article = relationship("Article", back_populates="media_refs")

class BookmarkFolder(Base):
    """Folders for organizing bookmarks — Plus and Pro users only."""
    __tablename__ = "bookmark_folders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    # Pro-only: auto-sort rules e.g. {"category": "AI", "keyword": "machine learning"}
    is_smart = Column(Boolean, default=False)
    auto_sort_rule = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BookmarkTag(Base):
    """User-defined tags for bookmarks — Plus and Pro users only."""
    __tablename__ = "bookmark_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    name = Column(String, nullable=False)
    color = Column(String, default="#6366f1")   # hex color
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SavedArticle(Base):
    """
    Unified bookmark model for both content articles and news articles.
    source_type = 'article' → article_id is content_service article UUID
    source_type = 'news'    → news_article_id is news_service integer ID
    """
    __tablename__ = "saved_articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)

    # Source type distinguishes article vs news bookmarks
    source_type = Column(String, default="article", nullable=False)  # 'article' | 'news'

    # For content articles
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=True)

    # For news articles (integer ID from news_service)
    news_article_id = Column(Integer, nullable=True)
    # Cache news article metadata so it's usable offline/without news_service call
    news_title = Column(String, nullable=True)
    news_slug = Column(String, nullable=True)
    news_image_url = Column(String, nullable=True)
    news_source = Column(String, nullable=True)

    # Organization — Plus and Pro features
    folder_id = Column(UUID(as_uuid=True), ForeignKey("bookmark_folders.id"), nullable=True)
    tag_ids = Column(ARRAY(String), default=list)   # list of tag UUIDs as strings
    notes = Column(String, nullable=True)            # user notes on this bookmark

    saved_at = Column(DateTime(timezone=True), server_default=func.now())


class ReadingHistory(Base):
    __tablename__ = "reading_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    
    source_type = Column(String, default="article", nullable=False) # 'article' or 'news'
    
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=True)
    news_article_id = Column(Integer, nullable=True)
    news_title = Column(String, nullable=True)
    news_slug = Column(String, nullable=True)
    
    read_at = Column(DateTime(timezone=True), server_default=func.now())
    duration_seconds = Column(Integer, default=0)
    
    article = relationship("Article")

class ArticleLike(Base):
    __tablename__ = "article_likes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    article = relationship("Article", back_populates="likes")

class Reflection(Base):
    __tablename__ = "reflections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False)
    content = Column(String, nullable=False)
    author_name = Column(String, nullable=True)
    author_role = Column(String, nullable=True)
    author_img = Column(String, nullable=True)
    is_anonymous = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    article = relationship("Article", back_populates="reflections")

class UserContribution(Base):
    __tablename__ = "user_contributions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    content_type = Column(String, nullable=False) # e.g. "article", "insight", "tip"
    header = Column(String, nullable=False)
    main_content = Column(String, nullable=False)
    media_urls = Column(JSONB, default=list) # List of strings
    related_info = Column(JSONB, default=dict)
    
    status = Column(String, default="pending") # pending, approved, rejected
    admin_notes = Column(String, nullable=True)
    published_article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class SystemCache(Base):
    __tablename__ = "system_cache"
    key = Column(String, primary_key=True, index=True)
    value = Column(JSONB)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SystemSettings(Base):
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, default=1) # Singleton pattern
    site_name = Column(String, default="RelayPost")
    site_tagline = Column(String, default="Digital Editorial Intelligence")
    site_description = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    
    # Flexible JSON fields for social and extra config
    social_links = Column(JSONB, default=dict) # {twitter: "", linkedin: ""}
    seo_defaults = Column(JSONB, default=dict) # {meta_description: ""}
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class ContactInquiry(Base):
    __tablename__ = "contact_inquiries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    message = Column(String, nullable=False)
    status = Column(String, default="unread") # unread, read, archived
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AdminNotification(Base):
    __tablename__ = "admin_notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    type = Column(Enum(NotificationType, native_enum=False), default=NotificationType.INFO)
    link = Column(String, nullable=True) # Optional link to the related item
    is_read = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class NewsletterSubscription(Base):
    __tablename__ = "newsletter_subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserFollow(Base):
    __tablename__ = "user_follows"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(String, index=True, nullable=False) # Client side identifier
    target_id = Column(String, nullable=False) # Category or Keyword ID
    target_type = Column(String, nullable=False) # "category" or "keyword"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    version = Column(String, unique=True, index=True, nullable=False)
    score = Column(Float, nullable=True)
    diversity_score = Column(Float, nullable=True)
    changes = Column(String, nullable=True)
    topic_brainstorm_dynamic = Column(String, nullable=False)
    content_generation_dynamic = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# WEEKLY DIGEST SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class WeeklyDigest(Base):
    """
    Stores the canonical weekly digest published every Sunday.
    One row per ISO week — idempotent generation (skips if already published).
    """
    __tablename__ = "weekly_digests"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    week_label   = Column(String, unique=True, nullable=False, index=True)  # e.g. "2026-W28"
    week_start   = Column(DateTime(timezone=True), nullable=False)
    week_end     = Column(DateTime(timezone=True), nullable=False)
    published_at = Column(DateTime(timezone=True), server_default=func.now())

    # ── AI-generated editorial sections ──────────────────────────────────────
    executive_summary = Column(String, nullable=True)   # 3-4 sentence overview
    major_themes      = Column(String, nullable=True)   # markdown bullet list
    emerging_signals  = Column(String, nullable=True)   # trends / weak signals
    editors_note      = Column(String, nullable=True)   # short editorial voice
    stat_of_week      = Column(String, nullable=True)   # one compelling data point

    # ── Curated content (rich JSON lists) ────────────────────────────────────
    # Articles: [{id, title, slug, category, excerpt, hero_image, views_count}]
    top_articles  = Column(JSONB, default=list, nullable=False)
    # News: [{id, title, slug, source, category, image_url, published_at}]
    top_news      = Column(JSONB, default=list, nullable=False)
    # What to Watch: [{title, description}] × 3
    what_to_watch = Column(JSONB, default=list, nullable=False)

    # ── Stats ────────────────────────────────────────────────────────────────
    article_count = Column(Integer, default=0)
    news_count    = Column(Integer, default=0)

    # ── Delivery tracking ────────────────────────────────────────────────────
    is_sent       = Column(Boolean, default=False)   # email batch dispatched?
    emails_sent   = Column(Integer, default=0)       # how many emails went out
    generation_status = Column(String, default="pending")  # pending|generating|done|failed


class DigestOptOut(Base):
    """
    Users who have opted out of weekly digest emails.
    Indexed by user_id for fast lookup during batch send.
    """
    __tablename__ = "digest_opt_outs"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id    = Column(UUID(as_uuid=True), unique=True, index=True, nullable=False)
    email      = Column(String, nullable=True)   # cached for reference
    opted_out_at = Column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# AUTOMATION STATE (Key-value store for round-robin queue persistence)
# ─────────────────────────────────────────────────────────────────────────────

class AutomationState(Base):
    """Lightweight key-value store for persisting automation queue state."""
    __tablename__ = "automation_state"

    key = Column(String, primary_key=True, nullable=False)
    value = Column(JSONB, nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

