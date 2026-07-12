from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.models import RoleEnum

class UserBase(BaseModel):
    email: EmailStr
    display_name: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    specialization: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

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

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ForgotPasswordReset(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=72)

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

class CreateOrderRequest(BaseModel):
    amount: int = Field(..., ge=100, le=5000000, description="Amount in paise (min 100, max 5000000)")

class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str

class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str

class VerifyPaymentResponse(BaseModel):
    status: str
    message: str


# --- SUBSCRIPTION SCHEMAS ---

from app.models.models import SubscriptionTier, SubscriptionStatus, BillingInterval

class SubscriptionCreate(BaseModel):
    tier: SubscriptionTier
    billing_interval: BillingInterval = BillingInterval.MONTHLY
    with_trial: bool = True  # whether to start a 7-day trial

class SubscriptionResponse(BaseModel):
    id: UUID
    user_id: UUID
    tier: SubscriptionTier
    status: SubscriptionStatus
    billing_interval: Optional[BillingInterval] = None
    is_trial: bool
    has_used_trial: bool
    trial_start: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool
    cancelled_at: Optional[datetime] = None
    payment_failed_at: Optional[datetime] = None
    payment_retry_count: int
    grace_period_end: Optional[datetime] = None
    amount_paise: Optional[int] = None
    currency: str
    razorpay_subscription_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class TierStatusResponse(BaseModel):
    """Quick status used by all services for tier gating checks."""
    user_id: str
    tier: str
    status: str
    is_active: bool          # True if user can use tier features right now
    is_trial: bool
    trial_end: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool

class SubscriptionCancelRequest(BaseModel):
    reason: Optional[str] = None   # optional feedback

class SubscriptionReactivateRequest(BaseModel):
    pass

class SubscriptionOverrideRequest(BaseModel):
    tier: SubscriptionTier

class CreateRazorpaySubscriptionRequest(BaseModel):
    tier: SubscriptionTier
    billing_interval: BillingInterval = BillingInterval.MONTHLY

class RazorpaySubscriptionResponse(BaseModel):
    razorpay_subscription_id: str
    razorpay_key_id: str
    tier: str
    amount_paise: int
    currency: str
    trial_end: Optional[datetime] = None
    is_upgrade_eligible: bool = False

# --- USER NOTIFICATION SCHEMAS ---

class UserNotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    title: str
    message: str
    action_url: Optional[str] = None
    is_read: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
