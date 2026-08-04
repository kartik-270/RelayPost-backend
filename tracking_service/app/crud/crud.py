"""
Tier limits configuration and usage CRUD for tracking_service.

FREE limits are per-month to motivate upgrades.
PLUS limits are per rolling 24h for AI features.
PRO: -1 = unlimited.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models import models


# ── limit definitions ─────────────────────────────────────────────────────────
# -1 = unlimited, 0 = blocked entirely

TIER_LIMITS = {
    "free": {
        "ai_summary":       {"limit": 10,  "window": "monthly"},    # 10/month → motivates upgrade
        "ask_ai":           {"limit": 5,   "window": "monthly"},    # 5 questions/month
        "cross_article":    {"limit": 0,   "window": "monthly"},    # blocked
        "research_mode":    {"limit": 0,   "window": "monthly"},    # blocked
        "weekly_report":    {"limit": 0,   "window": "monthly"},    # blocked (preview only)
        "bookmarks":        {"limit": 20,  "window": "monthly"},    # 20 total cap
        "followed_topics":  {"limit": 5,   "window": "none"},       # hard cap, no reset
        "export":           {"limit": 0,   "window": "monthly"},    # blocked
        "news_ai_summary":  {"limit": 5,   "window": "monthly"},    # 5 news AI summaries/month
    },
    "plus": {
        "ai_summary":       {"limit": 40,  "window": "rolling_24h"},  # slightly reduced
        "ask_ai":           {"limit": 25,  "window": "rolling_24h"},  # slightly reduced
        "cross_article":    {"limit": 0,   "window": "rolling_24h"},  # blocked
        "research_mode":    {"limit": 0,   "window": "rolling_24h"},  # blocked
        "weekly_report":    {"limit": -1,  "window": "rolling_24h"},  # unlimited
        "bookmarks":        {"limit": -1,  "window": "none"},          # unlimited
        "followed_topics":  {"limit": -1,  "window": "none"},          # unlimited
        "export":           {"limit": -1,  "window": "rolling_24h"},  # markdown only (enforced by endpoint)
        "news_ai_summary":  {"limit": 40,  "window": "rolling_24h"},
    },
    "pro": {
        "ai_summary":       {"limit": -1,  "window": "rolling_24h"},  # unlimited
        "ask_ai":           {"limit": -1,  "window": "rolling_24h"},
        "cross_article":    {"limit": -1,  "window": "rolling_24h"},
        "research_mode":    {"limit": 30,  "window": "monthly"},       # 30/month soft cap
        "weekly_report":    {"limit": -1,  "window": "rolling_24h"},
        "bookmarks":        {"limit": -1,  "window": "none"},
        "followed_topics":  {"limit": -1,  "window": "none"},
        "export":           {"limit": -1,  "window": "rolling_24h"},
        "news_ai_summary":  {"limit": -1,  "window": "rolling_24h"},
    },
}


def _now():
    return datetime.now(timezone.utc)


def _get_window_bounds(window_type: str):
    now = _now()
    if window_type == "rolling_24h":
        return now, now + timedelta(hours=24)
    elif window_type == "monthly":
        # First of current month to first of next month
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    else:  # "none" — no windowed limit, permanent
        return now, now + timedelta(days=36500)  # ~100 years


def _get_current_count(db: Session, user_id: str, feature: str, window_type: str) -> int:
    """Sum usage within the active window."""
    now = _now()
    if window_type == "rolling_24h":
        cutoff = now - timedelta(hours=24)
        records = db.query(models.UsageRecord).filter(
            and_(
                models.UsageRecord.user_id == user_id,
                models.UsageRecord.feature == feature,
                models.UsageRecord.window_start >= cutoff,
            )
        ).all()
    elif window_type == "monthly":
        start, _ = _get_window_bounds("monthly")
        records = db.query(models.UsageRecord).filter(
            and_(
                models.UsageRecord.user_id == user_id,
                models.UsageRecord.feature == feature,
                models.UsageRecord.window_start >= start,
            )
        ).all()
    else:
        records = db.query(models.UsageRecord).filter(
            and_(
                models.UsageRecord.user_id == user_id,
                models.UsageRecord.feature == feature,
            )
        ).all()
    return sum(r.count for r in records)


# ── public CRUD functions ─────────────────────────────────────────────────────

def check_limit(db: Session, user_id: str, feature: str, tier: str) -> dict:
    """
    Returns:
      allowed: bool — can the user use this feature?
      remaining: int — how many uses left (-1 = unlimited)
      limit: int — max allowed (-1 = unlimited)
      reset_at: str | None — when the window resets
    """
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    feature_cfg = limits.get(feature)

    if feature_cfg is None:
        return {"allowed": False, "remaining": 0, "limit": 0, "reset_at": None, "reason": "unknown_feature"}

    limit = feature_cfg["limit"]
    window = feature_cfg["window"]

    # Blocked feature
    if limit == 0:
        return {"allowed": False, "remaining": 0, "limit": 0, "used": 0, "window": window, "reset_at": None, "reason": "tier_blocked"}

    # Unlimited
    if limit == -1:
        return {"allowed": True, "remaining": -1, "limit": -1, "used": 0, "window": window, "reset_at": None}

    # Check current usage
    current = _get_current_count(db, user_id, feature, window)
    remaining = max(0, limit - current)
    _, window_end = _get_window_bounds(window)

    return {
        "allowed": current < limit,
        "remaining": remaining,
        "limit": limit,
        "used": current,
        "window": window,
        "reset_at": window_end.isoformat() if window != "none" else None,
    }


def track_usage(db: Session, user_id: str, feature: str, tier: str, count: int = 1) -> dict:
    """
    Record `count` uses of `feature` by `user_id`.
    Returns the new check_limit result after tracking.
    """
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    feature_cfg = limits.get(feature, {})
    window = feature_cfg.get("window", "rolling_24h")

    now = _now()
    _, window_end = _get_window_bounds(window)

    record = models.UsageRecord(
        user_id=user_id,
        feature=feature,
        window_type=window,
        count=count,
        window_start=now,
        window_end=window_end,
    )
    db.add(record)
    db.commit()

    return check_limit(db, user_id, feature, tier)


def get_usage_status(db: Session, user_id: str, tier: str) -> dict:
    """Full usage snapshot across all features for the given tier."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    status = {}
    for feature in limits:
        status[feature] = check_limit(db, user_id, feature, tier)
    return {"user_id": user_id, "tier": tier, "features": status}
