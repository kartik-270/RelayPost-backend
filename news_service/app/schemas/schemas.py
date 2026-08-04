from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Any
from datetime import datetime

class ArticleBase(BaseModel):
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    source_name: Optional[str] = None
    author: Optional[str] = None
    url: str
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None
    category: Optional[str] = None
    keywords: Optional[List[str]] = None
    cluster_id: Optional[int] = None
    ai_summary: Optional[str] = None
    slug: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    is_verified: Optional[bool] = False
    full_analysis: Optional[str] = None
    views: Optional[int] = 0

class RelatedSource(BaseModel):
    id: int
    source_name: Optional[str]
    url: str

class ArticleWithSources(ArticleBase):
    id: int
    created_at: datetime
    related_sources: Optional[List[RelatedSource]] = []

    class Config:
        from_attributes = True

class ArticleCreate(ArticleBase):
    pass

class Article(ArticleBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class ArticlePaginated(BaseModel):
    items: List[Article]
    total: int
    page: int
    size: int
    pages: int
