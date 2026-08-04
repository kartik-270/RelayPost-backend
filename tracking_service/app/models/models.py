"""
Usage tracking models.
Each row represents a rolling window counter for a (user, feature) pair.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base


class UsageRecord(Base):
    """
    Rolling usage counter.
    For AI features: window_type='rolling_24h', window refreshes continuously.
    For other caps:  window_type='monthly', window resets on 1st of each month.
    """
    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(String, index=True, nullable=False)        # UUID string

    # feature identifiers match TIER_LIMITS keys
    feature = Column(String, index=True, nullable=False)
    # e.g. ai_summary | ask_ai | cross_article | research_mode
    #      weekly_report | bookmarks | followed_topics | export

    window_type = Column(String, nullable=False)                # rolling_24h | monthly
    count = Column(Integer, default=0, nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
