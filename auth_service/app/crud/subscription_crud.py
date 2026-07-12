"""
Subscription CRUD for auth_service.
All state transitions go through log_event() to maintain a full audit trail.
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timedelta, timezone
import uuid
from typing import Optional

from app.models import models


# ── pricing constants ─────────────────────────────────────────────────────────

TIER_PRICES_PAISE = {
    ("plus",  "monthly"): 9900,      # ₹99
    ("plus",  "annual"):  89900,     # ₹899
    ("pro",   "monthly"): 19900,     # ₹199
    ("pro",   "annual"):  179900,    # ₹1799
}

TRIAL_DAYS = 7
GRACE_DAYS = 3   # days before past_due → expired


def _now():
    return datetime.now(timezone.utc)


def _is_tier_active(sub: models.Subscription) -> bool:
    """Return True if the user may use their tier's features right now."""
    if sub is None:
        return False
    if sub.tier == models.SubscriptionTier.FREE:
        return True
    if sub.status in (models.SubscriptionStatus.ACTIVE, models.SubscriptionStatus.TRIALING):
        return True
    # During grace period after payment failure, still allow access
    if sub.status == models.SubscriptionStatus.PAST_DUE and sub.grace_period_end:
        return _now() <= sub.grace_period_end
    return False


# ── subscription queries ──────────────────────────────────────────────────────

def get_subscription(db: Session, user_id: uuid.UUID) -> Optional[models.Subscription]:
    return db.query(models.Subscription).filter(
        models.Subscription.user_id == user_id
    ).first()


def get_subscription_by_rzp_id(db: Session, rzp_id: str) -> Optional[models.Subscription]:
    return db.query(models.Subscription).filter(
        models.Subscription.razorpay_subscription_id == rzp_id
    ).first()


def get_or_create_free_subscription(db: Session, user_id: uuid.UUID) -> models.Subscription:
    """Every user has exactly one subscription row. Free is the default."""
    sub = get_subscription(db, user_id)
    if not sub:
        sub = models.Subscription(
            user_id=user_id,
            tier=models.SubscriptionTier.FREE,
            status=models.SubscriptionStatus.ACTIVE,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        log_event(db, sub, "created", {"tier": "free"})
    return sub


# ── tier status (lightweight dict for internal service consumption) ───────────

def get_tier_status(db: Session, user_id: uuid.UUID) -> dict:
    sub = get_subscription(db, user_id)
    if not sub:
        return {
            "user_id": str(user_id),
            "tier": "free",
            "status": "active",
            "is_active": True,
            "is_trial": False,
            "trial_end": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
        }
    return {
        "user_id": str(user_id),
        "tier": sub.tier.value,
        "status": sub.status.value,
        "is_active": _is_tier_active(sub),
        "is_trial": sub.is_trial,
        "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


# ── create / start trial ──────────────────────────────────────────────────────

def create_subscription(
    db: Session,
    user_id: uuid.UUID,
    tier: models.SubscriptionTier,
    billing_interval: models.BillingInterval,
    razorpay_subscription_id: str,
    razorpay_plan_id: str,
    with_trial: bool = True,
) -> models.Subscription:
    """
    Called once Razorpay subscription is created and the payment method
    (mandate) has been authorised by the user.
    If with_trial=True and user has not used a trial, status=TRIALING.
    """
    existing = get_subscription(db, user_id)
    tier_val = tier.value
    interval_val = billing_interval.value
    amount = TIER_PRICES_PAISE.get((tier_val, interval_val), 0)

    now = _now()
    
    # Trial eligibility: only if never used before
    do_trial = with_trial and (existing is None or not existing.has_used_trial)
    trial_end = now + timedelta(days=TRIAL_DAYS) if do_trial else None
    status = models.SubscriptionStatus.TRIALING if do_trial else models.SubscriptionStatus.ACTIVE
    
    if do_trial:
        period_end = trial_end
    else:
        period_end = now + timedelta(days=365 if billing_interval == models.BillingInterval.ANNUAL else 30)

    if existing:
        existing.tier = tier
        existing.status = status
        existing.billing_interval = billing_interval
        existing.razorpay_subscription_id = razorpay_subscription_id
        existing.razorpay_plan_id = razorpay_plan_id
        existing.current_period_start = now
        existing.current_period_end = period_end
        existing.trial_start = now if do_trial else None
        existing.trial_end = trial_end
        existing.is_trial = do_trial
        existing.has_used_trial = existing.has_used_trial or do_trial
        existing.cancel_at_period_end = False
        existing.cancelled_at = None
        existing.payment_failed_at = None
        existing.payment_retry_count = 0
        existing.grace_period_end = None
        existing.amount_paise = amount
        sub = existing
    else:
        sub = models.Subscription(
            user_id=user_id,
            tier=tier,
            status=status,
            billing_interval=billing_interval,
            razorpay_subscription_id=razorpay_subscription_id,
            razorpay_plan_id=razorpay_plan_id,
            current_period_start=now,
            current_period_end=period_end,
            trial_start=now if do_trial else None,
            trial_end=trial_end,
            is_trial=do_trial,
            has_used_trial=do_trial,
            amount_paise=amount,
        )
        db.add(sub)

    db.commit()
    db.refresh(sub)

    event_type = "trial_started" if do_trial else "created"
    log_event(db, sub, event_type, {
        "tier": tier_val, "interval": interval_val,
        "amount_paise": amount, "razorpay_subscription_id": razorpay_subscription_id,
    })
    return sub


# ── payment webhook events ────────────────────────────────────────────────────

def on_payment_success(db: Session, rzp_subscription_id: str) -> Optional[models.Subscription]:
    sub = get_subscription_by_rzp_id(db, rzp_subscription_id)
    if not sub:
        return None
    now = _now()
    period_end = now + timedelta(days=365 if sub.billing_interval == models.BillingInterval.ANNUAL else 30)
    sub.status = models.SubscriptionStatus.ACTIVE
    sub.is_trial = False
    sub.current_period_start = now
    sub.current_period_end = period_end
    sub.payment_failed_at = None
    sub.payment_retry_count = 0
    sub.grace_period_end = None
    db.commit()
    db.refresh(sub)
    log_event(db, sub, "payment_succeeded", {"next_period_end": period_end.isoformat()})
    return sub


def on_payment_failed(db: Session, rzp_subscription_id: str) -> Optional[models.Subscription]:
    sub = get_subscription_by_rzp_id(db, rzp_subscription_id)
    if not sub:
        return None
    now = _now()
    sub.status = models.SubscriptionStatus.PAST_DUE
    sub.payment_failed_at = now
    sub.payment_retry_count = (sub.payment_retry_count or 0) + 1
    sub.grace_period_end = now + timedelta(days=GRACE_DAYS)
    db.commit()
    db.refresh(sub)
    log_event(db, sub, "payment_failed", {"retry_count": sub.payment_retry_count})
    return sub


def on_subscription_halted(db: Session, rzp_subscription_id: str) -> Optional[models.Subscription]:
    """Razorpay halted all retries — downgrade to free."""
    sub = get_subscription_by_rzp_id(db, rzp_subscription_id)
    if not sub:
        return None
    sub.status = models.SubscriptionStatus.EXPIRED
    sub.tier = models.SubscriptionTier.FREE
    sub.is_trial = False
    db.commit()
    db.refresh(sub)
    log_event(db, sub, "grace_expired", {"reason": "razorpay_halted"})
    return sub


def on_subscription_cancelled(db: Session, rzp_subscription_id: str) -> Optional[models.Subscription]:
    sub = get_subscription_by_rzp_id(db, rzp_subscription_id)
    if not sub:
        return None
    now = _now()
    sub.cancel_at_period_end = True
    sub.cancelled_at = now
    db.commit()
    db.refresh(sub)
    log_event(db, sub, "cancelled", {"via": "razorpay_webhook"})
    return sub


# ── user-initiated actions ────────────────────────────────────────────────────

def cancel_at_period_end(db: Session, user_id: uuid.UUID, reason: Optional[str] = None) -> Optional[models.Subscription]:
    """User turns off autopay; plan stays active until current_period_end."""
    sub = get_subscription(db, user_id)
    if not sub or sub.tier == models.SubscriptionTier.FREE:
        return None
    now = _now()
    sub.cancel_at_period_end = True
    sub.cancelled_at = now
    db.commit()
    db.refresh(sub)
    log_event(db, sub, "cancel_at_period_end", {"reason": reason or "user_request"})
    return sub


def reactivate_subscription(db: Session, user_id: uuid.UUID) -> Optional[models.Subscription]:
    """User re-enables autopay before period end."""
    sub = get_subscription(db, user_id)
    if not sub:
        return None
    sub.cancel_at_period_end = False
    sub.cancelled_at = None
    db.commit()
    db.refresh(sub)
    log_event(db, sub, "reactivated", {})
    return sub


# ── scheduler batch helpers ───────────────────────────────────────────────────

def expire_trial_no_payment(db: Session, sub: models.Subscription):
    sub.status = models.SubscriptionStatus.EXPIRED
    sub.tier = models.SubscriptionTier.FREE
    sub.is_trial = False
    db.commit()
    log_event(db, sub, "expired", {"reason": "trial_no_payment"})


def expire_cancelled_subscription(db: Session, sub: models.Subscription):
    sub.status = models.SubscriptionStatus.EXPIRED
    sub.tier = models.SubscriptionTier.FREE
    sub.is_trial = False
    db.commit()
    log_event(db, sub, "expired", {"reason": "period_ended_after_cancel"})


def expire_grace_period(db: Session, sub: models.Subscription):
    sub.status = models.SubscriptionStatus.EXPIRED
    sub.tier = models.SubscriptionTier.FREE
    sub.is_trial = False
    db.commit()
    log_event(db, sub, "grace_expired", {"reason": "no_payment_after_grace"})


def get_expiring_trials(db: Session, hours_ahead: int = 72):
    now = _now()
    return db.query(models.Subscription).filter(
        models.Subscription.status == models.SubscriptionStatus.TRIALING,
        models.Subscription.trial_end <= now + timedelta(hours=hours_ahead),
        models.Subscription.trial_end > now,
    ).all()


def get_expired_trials(db: Session):
    now = _now()
    return db.query(models.Subscription).filter(
        models.Subscription.status == models.SubscriptionStatus.TRIALING,
        models.Subscription.trial_end <= now,
    ).all()


def get_period_ended_cancelled(db: Session):
    now = _now()
    return db.query(models.Subscription).filter(
        models.Subscription.status == models.SubscriptionStatus.ACTIVE,
        models.Subscription.cancel_at_period_end == True,
        models.Subscription.current_period_end <= now,
    ).all()


def get_grace_expired(db: Session):
    now = _now()
    return db.query(models.Subscription).filter(
        models.Subscription.status == models.SubscriptionStatus.PAST_DUE,
        models.Subscription.grace_period_end <= now,
    ).all()


# ── notification helpers ──────────────────────────────────────────────────────

def create_user_notification(
    db: Session, user_id: uuid.UUID, notif_type: str,
    title: str, message: str, action_url: Optional[str] = None,
) -> models.UserNotification:
    notif = models.UserNotification(
        user_id=user_id, type=notif_type,
        title=title, message=message, action_url=action_url,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def get_user_notifications(db: Session, user_id: uuid.UUID, limit: int = 20):
    return (
        db.query(models.UserNotification)
        .filter(models.UserNotification.user_id == user_id)
        .order_by(desc(models.UserNotification.created_at))
        .limit(limit)
        .all()
    )


def mark_notification_read(db: Session, notif_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    notif = db.query(models.UserNotification).filter(
        models.UserNotification.id == notif_id,
        models.UserNotification.user_id == user_id,
    ).first()
    if not notif:
        return False
    notif.is_read = True
    db.commit()
    return True


def mark_all_notifications_read(db: Session, user_id: uuid.UUID):
    db.query(models.UserNotification).filter(
        models.UserNotification.user_id == user_id,
        models.UserNotification.is_read == False,
    ).update({"is_read": True})
    db.commit()


def get_unread_count(db: Session, user_id: uuid.UUID) -> int:
    return db.query(models.UserNotification).filter(
        models.UserNotification.user_id == user_id,
        models.UserNotification.is_read == False,
    ).count()


# ── audit log ─────────────────────────────────────────────────────────────────

def log_event(db: Session, sub: models.Subscription, event_type: str, metadata: dict):
    event = models.SubscriptionEvent(
        subscription_id=sub.id,
        user_id=sub.user_id,
        event_type=event_type,
        event_metadata=metadata,
    )
    db.add(event)
    db.commit()
