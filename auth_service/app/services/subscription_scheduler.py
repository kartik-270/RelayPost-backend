"""
APScheduler-based background jobs for subscription lifecycle management.
Runs inside auth_service. Checks every hour for:
  - Expiring trials (send 3-day reminder)
  - Trials that ended with no active payment → downgrade to free
  - Cancelled subscriptions whose period ended → downgrade to free
  - Past-due subscriptions past grace period → downgrade to free
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)


def _run_subscription_checks():
    """Main hourly check — import inside to avoid circular imports at startup."""
    from app.core.database import SessionLocal
    from app.crud import subscription_crud as sc
    from app.core import mail_utils

    db = SessionLocal()
    try:
        # 1. Trial ending soon → send reminder (72h window, fire once)
        expiring = sc.get_expiring_trials(db, hours_ahead=72)
        for sub in expiring:
            # Check if reminder already sent (look for event)
            from models import SubscriptionEvent
            already_notified = db.query(SubscriptionEvent).filter(
                SubscriptionEvent.subscription_id == sub.id,
                SubscriptionEvent.event_type == "trial_ending_soon",
            ).first()
            if not already_notified:
                days_left = max(0, (sub.trial_end - sc._now()).days)
                try:
                    import asyncio
                    asyncio.run(mail_utils.send_trial_ending_email(
                        sub.user.email, sub.tier.value, days_left
                    ))
                except Exception as e:
                    log.warning(f"Trial ending email failed for {sub.user_id}: {e}")
                sc.create_user_notification(
                    db, sub.user_id,
                    "trial_ending",
                    f"Your {sub.tier.value.title()} trial ends in {days_left} day(s)",
                    "Your subscription will auto-activate when the trial ends. Make sure your payment method is set.",
                    action_url="/subscription",
                )
                sc.log_event(db, sub, "trial_ending_soon", {"days_left": days_left})

        # 2. Trials that expired with no payment (razorpay_subscription_id may be None if checkout abandoned)
        expired_trials = sc.get_expired_trials(db)
        for sub in expired_trials:
            # If they have a Razorpay subscription, the webhook will handle billing
            # Only downgrade if no Razorpay subscription linked (checkout abandoned)
            if not sub.razorpay_subscription_id:
                sc.expire_trial_no_payment(db, sub)
                try:
                    import asyncio
                    asyncio.run(mail_utils.send_subscription_expired_email(
                        sub.user.email, sub.tier.value, reason="trial_ended"
                    ))
                except Exception as e:
                    log.warning(f"Trial expired email failed for {sub.user_id}: {e}")
                sc.create_user_notification(
                    db, sub.user_id,
                    "subscription_expired",
                    "Your free trial has ended",
                    f"Your {sub.tier.value.title()} trial ended. You're now on the Free plan. Upgrade anytime to restore access.",
                    action_url="/pricing",
                )

        # 3. Cancelled subscriptions whose period has ended → downgrade
        ended_cancelled = sc.get_period_ended_cancelled(db)
        for sub in ended_cancelled:
            sc.expire_cancelled_subscription(db, sub)
            try:
                import asyncio
                asyncio.run(mail_utils.send_subscription_expired_email(
                    sub.user.email, sub.tier.value, reason="cancelled"
                ))
            except Exception as e:
                log.warning(f"Cancelled-expired email failed for {sub.user_id}: {e}")
            sc.create_user_notification(
                db, sub.user_id,
                "subscription_expired",
                f"Your {sub.tier.value.title()} plan has ended",
                "Your subscription period has ended. You've been moved to the Free plan. Re-subscribe anytime.",
                action_url="/pricing",
            )

        # 4. Past-due subs whose grace period has expired → downgrade
        grace_expired = sc.get_grace_expired(db)
        for sub in grace_expired:
            sc.expire_grace_period(db, sub)
            try:
                import asyncio
                asyncio.run(mail_utils.send_subscription_expired_email(
                    sub.user.email, sub.tier.value, reason="payment_failed"
                ))
            except Exception as e:
                log.warning(f"Grace-expired email failed for {sub.user_id}: {e}")
            sc.create_user_notification(
                db, sub.user_id,
                "subscription_expired",
                "Payment failed — plan downgraded",
                "We couldn't process your payment after multiple retries. You're now on the Free plan. Update your payment method to resubscribe.",
                action_url="/subscription",
            )

    except Exception as e:
        log.error(f"Subscription scheduler error: {e}", exc_info=True)
    finally:
        db.close()


# ── scheduler singleton ───────────────────────────────────────────────────────

subscription_scheduler = BackgroundScheduler(timezone="UTC")
subscription_scheduler.add_job(
    _run_subscription_checks,
    trigger=IntervalTrigger(hours=1),
    id="subscription_lifecycle_check",
    replace_existing=True,
    max_instances=1,  # never run concurrently
)
