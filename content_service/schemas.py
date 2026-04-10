from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from uuid import UUID
from datetime import datetime
from models import ArticleStatus, TemplateType, ThemeType

# -- Categories & Keywords --
class CategoryBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None

class CategoryResponse(CategoryBase):
    id: UUID
    class Config:
        from_attributes = True

class KeywordBase(BaseModel):
    tag: str

class KeywordResponse(KeywordBase):
    id: UUID
    class Config:
        from_attributes = True

# -- Articles --
class ArticleBase(BaseModel):
    # Core
    title: str
    slug: str
    subtitle: Optional[str] = None
    hero_image: Optional[str] = None
    excerpt: Optional[str] = None
    
    # Structure
    template_type: TemplateType = TemplateType.STANDARD
    theme: ThemeType = ThemeType.STANDARD
    content_blocks: List[Any] = []
    media_gallery: List[Any] = []
    
    # SEO
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    focus_keyword: Optional[str] = None
    secondary_keywords: List[str] = []
    canonical_url: Optional[str] = None
    schema_markup: Dict[str, Any] = {}
    
    # AI / GEO
    ai_summary: Optional[str] = None
    key_takeaways: List[Dict[str, Any]] = []
    faq_section: List[Dict[str, Any]] = []
    
    # Admin
    status: ArticleStatus = ArticleStatus.DRAFT
    visibility: str = "public"
    is_featured: bool = False
    
    # Placement
    homepage_section: Optional[str] = None
    section_order: int = 0

class ArticleCreate(ArticleBase):
    author_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    keyword_ids: List[UUID] = []

class ArticleUpdate(BaseModel):
    # Make everything optional for partial updates
    title: Optional[str] = None
    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    slug: Optional[str] = None
    subtitle: Optional[str] = None
    hero_image: Optional[str] = None
    excerpt: Optional[str] = None
    template_type: Optional[TemplateType] = None
    content_blocks: Optional[List[Any]] = None
    media_gallery: Optional[List[Any]] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    focus_keyword: Optional[str] = None
    secondary_keywords: Optional[List[str]] = None
    canonical_url: Optional[str] = None
    schema_markup: Optional[Dict[str, Any]] = None
    ai_summary: Optional[str] = None
    key_takeaways: Optional[List[Dict[str, Any]]] = None
    faq_section: Optional[List[Dict[str, Any]]] = None
    status: Optional[ArticleStatus] = None
    visibility: Optional[str] = None
    is_featured: Optional[bool] = None
    scheduled_at: Optional[datetime] = None
    homepage_section: Optional[str] = None
    section_order: Optional[int] = None

class ArticleResponse(ArticleBase):
    id: UUID
    author_id: UUID
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# -- Media --
class MediaResponse(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size: int
    created_at: datetime
    url: Optional[str] = None # Will be populated by the frontend or helper

    class Config:
        from_attributes = True

# -- Suggestions --
class KeywordSuggestion(BaseModel):
    tag: str
    score: float

class LinkSuggestion(BaseModel):
    id: UUID
    title: str
    slug: str
    excerpt: Optional[str] = None

# -- Interactions --
class UserInteractionBase(BaseModel):
    article_id: UUID

class SavedArticleResponse(UserInteractionBase):
    id: UUID
    user_id: UUID
    saved_at: datetime
    class Config:
        from_attributes = True

class ReadingHistoryResponse(UserInteractionBase):
    id: UUID
    user_id: UUID
    read_at: datetime
    class Config:
        from_attributes = True

class ReflectionBase(BaseModel):
    content: str
    author_name: Optional[str] = None
    author_role: Optional[str] = None
    author_img: Optional[str] = None
    is_anonymous: bool = False

class ReflectionCreate(ReflectionBase):
    pass

class ReflectionResponse(ReflectionBase):
    id: UUID
    article_id: UUID
    created_at: datetime
    class Config:
        from_attributes = True

class ArticleLikeResponse(BaseModel):
    id: UUID
    user_id: UUID
    article_id: UUID
    created_at: datetime
    class Config:
        from_attributes = True

# Extended Article Response with stats and relations
class ArticleDetailResponse(ArticleResponse):
    views_count: int = 0
    likes_count: int = 0
    reflections: List[ReflectionResponse] = []

# -- User Contributions --
class UserContributionBase(BaseModel):
    content_type: str
    header: str
    main_content: str
    media_urls: List[str] = []
    related_info: Dict[str, Any] = {}

class UserContributionCreate(UserContributionBase):
    pass

class UserContributionResponse(UserContributionBase):
    id: UUID
    user_id: UUID
    status: str
    admin_notes: Optional[str] = None
    published_article_id: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# -- System Settings --
class SystemSettingsBase(BaseModel):
    site_name: str = "RelayPost"
    site_tagline: str = "Digital Editorial Intelligence"
    site_description: Optional[str] = None
    contact_email: Optional[str] = None
    social_links: Dict[str, str] = {}
    seo_defaults: Dict[str, str] = {}

class SystemSettingsResponse(SystemSettingsBase):
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# -- Contact Inquiries --
class ContactInquiryBase(BaseModel):
    full_name: str
    email: str
    subject: str
    message: str

class ContactInquiryCreate(ContactInquiryBase):
    pass

class ContactInquiryResponse(ContactInquiryBase):
    id: UUID
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True
