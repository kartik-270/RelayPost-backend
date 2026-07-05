import enum
import uuid
from sqlalchemy import Column, String, Boolean, Enum, DateTime, func, Integer
from sqlalchemy.dialects.postgresql import UUID
from database import Base

class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    PUBLISHER = "publisher"
    VIEWER = "viewer"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    google_id = Column(String, unique=True, index=True, nullable=True) # For OAuth
    hashed_password = Column(String, nullable=True) # Can be null if only Google Auth
    display_name = Column(String, nullable=True)
    avatar = Column(String, nullable=True) # Profile
    bio = Column(String, nullable=True) # Profile
    specialization = Column(String, nullable=True) # Expertise
    
    role = Column(Enum(RoleEnum), default=RoleEnum.VIEWER, nullable=False)
    
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Invite(Base):
    __tablename__ = "invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, index=True, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.VIEWER, nullable=False)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Contribution(Base):
    __tablename__ = "contributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False) # Must be linked to a user
    amount = Column(Integer, nullable=False) # In paise
    currency = Column(String, default="INR", nullable=False)
    razorpay_order_id = Column(String, unique=True, index=True, nullable=False)
    razorpay_payment_id = Column(String, nullable=True)
    status = Column(String, default="PENDING", nullable=False) # PENDING, SUCCESS, FAILED
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
