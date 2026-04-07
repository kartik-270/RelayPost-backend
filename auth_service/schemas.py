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
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[RoleEnum] = None
