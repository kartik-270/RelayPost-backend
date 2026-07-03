from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from models import RoleEnum

class UserBase(BaseModel):
    email: EmailStr
    display_name: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    specialization: Optional[str] = None

class UserCreate(UserBase):
    password: Optional[str] = Field(None, min_length=8, max_length=72, description="Password must be between 8 and 72 characters")
    google_id: Optional[str] = None
    role: Optional[RoleEnum] = RoleEnum.VIEWER

class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    specialization: Optional[str] = None
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None

class UserResponse(UserBase):
    id: UUID
    role: RoleEnum
    is_active: bool
    is_deleted: bool
    is_verified: bool
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[RoleEnum] = None

class VerifyRequest(BaseModel):
    token: str

class InviteCreate(BaseModel):
    email: EmailStr
    role: RoleEnum = RoleEnum.VIEWER

class InviteResponse(BaseModel):
    id: UUID
    email: EmailStr
    token: str
    role: RoleEnum
    expires_at: datetime
    is_used: bool

    class Config:
        from_attributes = True

class InviteSignup(BaseModel):
    token: str
    password: str = Field(..., min_length=8, max_length=72)
    display_name: Optional[str] = None

class AuthStats(BaseModel):
    total_users: int
    admin_count: int
    publisher_count: int
    viewer_count: int
