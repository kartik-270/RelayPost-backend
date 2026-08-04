import enum
import uuid
from sqlalchemy import Column, String, Boolean, Enum, DateTime, func, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base

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
    
    # IP-based location data
    country = Column(String, nullable=True)
    state = Column(String, nullable=True)
    city = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    latitude = Column(String, nullable=True)
    longitude = Column(String, nullable=True)
    
    role = Column(Enum(RoleEnum), default=RoleEnum.VIEWER, nullable=False)
    
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)
    
    # Forgot password OTP
    reset_otp_hash = Column(String, nullable=True)
    reset_otp_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # one-to-one: each user has at most one active subscription row
    subscription = relationship("Subscription", back_populates="user", uselist=False)


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


# --- SUBSCRIPTION SYSTEM ---

class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    PLUS = "plus"
    PRO = "pro"

class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PAUSED = "paused"

class BillingInterval(str, enum.Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, index=True, nullable=False)

    tier = Column(Enum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
    billing_interval = Column(Enum(BillingInterval), nullable=True)

    # Razorpay integration fields
    razorpay_subscription_id = Column(String, unique=True, index=True, nullable=True)
    razorpay_plan_id = Column(String, nullable=True)
    razorpay_customer_id = Column(String, nullable=True)

    # Period tracking
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)

    # Trial tracking — 7 days for Plus/Pro
    trial_start = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    is_trial = Column(Boolean, default=False)
    has_used_trial = Column(Boolean, default=False)  # prevent double trials

    # Cancellation — user disabled autopay but plan remains active till period end
    cancel_at_period_end = Column(Boolean, default=False)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Payment health
    payment_failed_at = Column(DateTime(timezone=True), nullable=True)
    payment_retry_count = Column(Integer, default=0)
    grace_period_end = Column(DateTime(timezone=True), nullable=True)  # 3-day grace window

    # Pricing (what the user is actually billed)
    amount_paise = Column(Integer, nullable=True)
    currency = Column(String, default="INR")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="subscription")
    events = relationship(
        "SubscriptionEvent",
        back_populates="subscription",
        order_by="desc(SubscriptionEvent.created_at)",
    )


class SubscriptionEvent(Base):
    """Immutable audit log of every subscription state transition."""
    __tablename__ = "subscription_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), index=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)

    # event_type values:
    # created | trial_started | trial_ending_soon | payment_succeeded
    # payment_failed | past_due | grace_expired | cancelled
    # cancel_at_period_end | expired | reactivated | upgraded | downgraded
    event_type = Column(String, nullable=False)
    event_metadata = Column(JSONB, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subscription = relationship("Subscription", back_populates="events")


class UserNotification(Base):
    """In-app notifications for billing events, trials, and plan changes."""
    __tablename__ = "user_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)

    # notification types:
    # payment_failed | trial_ending | subscription_expired | plan_upgraded
    # plan_downgraded | payment_success | autopay_cancelled | reactivated
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    action_url = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
