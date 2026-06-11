from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean
from sqlalchemy.sql import func
from database import Base
import datetime

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    source_name = Column(String, index=True, nullable=True)
    author = Column(String, nullable=True)
    url = Column(String, unique=True, index=True)
    image_url = Column(String, nullable=True)
    published_at = Column(DateTime, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    category = Column(String, index=True, nullable=True)
    keywords = Column(JSON, nullable=True)
    cluster_id = Column(Integer, index=True, nullable=True)
    ai_summary = Column(Text, nullable=True) 
    slug = Column(String, unique=True, index=True, nullable=True)
    meta_title = Column(String, nullable=True)
    meta_description = Column(Text, nullable=True)
    is_verified = Column(Boolean, default=False)
    full_analysis = Column(Text, nullable=True)
