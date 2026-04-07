import enum
import uuid
from sqlalchemy import Column, String, Boolean, Enum, DateTime, ForeignKey, Integer, Table, func, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from database import Base

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

class ThemeType(str, enum.Enum):
    STANDARD = "standard"
    INTELLIGENCE = "intelligence"
    SPORTS = "sports"

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

class Keyword(Base):
    __tablename__ = "keywords"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tag = Column(String, unique=True, index=True, nullable=False)

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

    # Relationships
    category_id = Column(UUID(as_uuid=True), ForeignKey('categories.id'), nullable=True)
    category = relationship("Category")
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

class SavedArticle(Base):
    __tablename__ = "saved_articles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False)
    saved_at = Column(DateTime(timezone=True), server_default=func.now())

class ReadingHistory(Base):
    __tablename__ = "reading_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False)
    read_at = Column(DateTime(timezone=True), server_default=func.now())

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
