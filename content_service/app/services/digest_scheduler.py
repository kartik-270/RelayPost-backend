"""
digest_scheduler.py — Weekly Digest Scheduler

Runs every Sunday at 06:00 UTC as an APScheduler cron job inside content_service.

Flow:
  1. Acquire Postgres advisory lock 1010 (prevent duplicate runs)
  2. Pause article automation scheduler
  3. Generate and persist the WeeklyDigest via digest_service
  4. Fetch all user emails from auth_service (internal endpoint)
  5. Filter out opted-out users
  6. Dispatch HTML digest email in batches of 50 (async, with 2s delay between batches)
  7. Update digest.is_sent + emails_sent
  8. Resume article automation scheduler
  9. Release lock

Designed to be safe in production:
  - Idempotent digest generation (skips if week already done)
  - Advisory lock prevents concurrent runs across worker instances
  - Email failures are logged but don't abort the batch
  - Automation is ALWAYS resumed in the finally block
"""

import asyncio
import logging
import os
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import text

log = logging.getLogger(__name__)

FRONTEND_URL    = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")[0].strip()
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth_service:8000")
INTERNAL_SECRET  = os.environ.get("INTERNAL_SECRET", "relaypost-internal")
BATCH_SIZE       = int(os.environ.get("DIGEST_EMAIL_BATCH_SIZE", "50"))
BATCH_DELAY_SEC  = float(os.environ.get("DIGEST_EMAIL_BATCH_DELAY", "2.0"))

ADVISORY_LOCK_ID = 1010  # unique ID for digest job


async def _fetch_all_users() -> list[dict]:
    """
    Call auth_service internal endpoint to get all active users.
    Returns list of {user_id, email, display_name}.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{AUTH_SERVICE_URL}/internal/users/digest-recipients",
                headers={"X-Internal-Secret": INTERNAL_SECRET},
            )
            if resp.status_code == 200:
                return resp.json()
            log.warning(f"[DIGEST] Failed to fetch users: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        log.error(f"[DIGEST] Error fetching users: {e}")
    return []


async def _send_email_to_user(
    user: dict,
    digest_dict: dict,
    opt_out_url: str,
    display_name: str,
) -> bool:
    """Send weekly digest email to a single user via auth_service mail endpoint."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{AUTH_SERVICE_URL}/internal/send-digest-email",
                headers={"X-Internal-Secret": INTERNAL_SECRET},
                json={
                    "email":        user["email"],
                    "display_name": user.get("display_name") or user["email"].split("@")[0],
                    "digest":       digest_dict,
                    "opt_out_url":  opt_out_url,
                    "frontend_url": FRONTEND_URL,
                },
            )
            return resp.status_code == 200
    except Exception as e:
        log.warning(f"[DIGEST EMAIL] Failed for {user.get('email')}: {e}")
        return False


async def _run_digest_job():
    """Main async digest job."""
    from app.core.database import SessionLocal
    from app.models.models import DigestOptOut, WeeklyDigest
    from app.services.premium.digest_service import publish_weekly_digest, _digest_to_dict
    from app.services.automation.scheduler import automation_scheduler

    db: Session = SessionLocal()

    # Advisory lock — prevent concurrent runs across gunicorn workers
    has_lock = db.execute(text(f"SELECT pg_try_advisory_lock({ADVISORY_LOCK_ID})")).scalar()
    if not has_lock:
        db.close()
        log.info("[DIGEST] Another worker already running digest job — skipping.")
        return

    log.info("[DIGEST] Starting weekly digest job...")

    try:
        # ── Step 1: Pause content automation ─────────────────────────────────
        log.info("[DIGEST] Pausing article automation...")
        automation_scheduler.pause_automation()

        # ── Step 2: Generate + persist digest ────────────────────────────────
        digest = await publish_weekly_digest(db)
        if not digest:
            log.error("[DIGEST] Digest generation returned None — aborting email dispatch.")
            return

        digest_dict = _digest_to_dict(digest)
        week_label  = digest.week_label

        # ── Step 3: Skip email if already sent this week ──────────────────────
        if digest.is_sent:
            log.info(f"[DIGEST] Emails already sent for {week_label} — skipping dispatch.")
            return

        # ── Step 4: Fetch users + filter opt-outs ────────────────────────────
        all_users = await _fetch_all_users()
        if not all_users:
            log.warning("[DIGEST] No users returned from auth_service — skipping email batch.")
            return

        # Build opt-out set
        opted_out_ids = {
            str(row.user_id)
            for row in db.query(DigestOptOut.user_id).all()
        }

        recipients = [u for u in all_users if u.get("user_id") not in opted_out_ids]
        log.info(f"[DIGEST] Sending to {len(recipients)} users ({len(all_users) - len(recipients)} opted out)...")

        # ── Step 5: Batched email dispatch ────────────────────────────────────
        emails_sent = 0
        for i in range(0, len(recipients), BATCH_SIZE):
            batch = recipients[i : i + BATCH_SIZE]
            log.info(f"[DIGEST] Batch {i // BATCH_SIZE + 1}: sending {len(batch)} emails...")

            tasks = []
            for user in batch:
                user_id = user.get("user_id", "")
                opt_out_url = f"{FRONTEND_URL}/digest/opt-out?user_id={user_id}&token={user_id}"
                tasks.append(_send_email_to_user(user, digest_dict, opt_out_url, user.get("display_name", "")))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_sent = sum(1 for r in results if r is True)
            emails_sent += batch_sent
            log.info(f"[DIGEST] Batch done: {batch_sent}/{len(batch)} sent successfully.")

            # Pause between batches to avoid SMTP rate limits
            if i + BATCH_SIZE < len(recipients):
                await asyncio.sleep(BATCH_DELAY_SEC)

        # ── Step 6: Mark digest as sent ───────────────────────────────────────
        digest.is_sent    = True
        digest.emails_sent = emails_sent
        db.commit()
        log.info(f"[DIGEST] Completed. {emails_sent} emails dispatched for {week_label}.")

    except Exception as e:
        log.error(f"[DIGEST] Job failed: {e}", exc_info=True)
    finally:
        # ALWAYS resume automation + release lock
        log.info("[DIGEST] Resuming article automation...")
        automation_scheduler.resume_automation()
        db.execute(text(f"SELECT pg_advisory_unlock({ADVISORY_LOCK_ID})"))
        db.commit()
        db.close()
        log.info("[DIGEST] Lock released.")


def run_digest_job_sync():
    """
    Synchronous wrapper — APScheduler calls this from a thread.
    We run the async job in a fresh event loop.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_digest_job())
    except Exception as e:
        log.error(f"[DIGEST] Sync wrapper error: {e}", exc_info=True)
    finally:
        try:
            loop.close()
        except Exception:
            pass
