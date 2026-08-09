from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.ingestion import process_and_store_articles
from app.services.processing import update_article_clusters, generate_ai_summaries
from datetime import datetime, timedelta

scheduler = BackgroundScheduler()

from app.services.cache import update_top_news_cache

import subprocess
import sys
import threading

PIPELINE_TIMEOUT_SECONDS = 15 * 60  # 15 minutes hard limit — enough for 35 articles + AI summaries

# ── Process Guard ──────────────────────────────────────────────────────────────
# Prevents multiple concurrent pipeline processes from spawning simultaneously.
# Only one pipeline subprocess can run at a time.
_process_lock = threading.Lock()
_current_process: subprocess.Popen | None = None


def scheduled_job():
    """
    Spawns the pipeline in a completely isolated subprocess.

    Guard: If a previous pipeline process is still running, this invocation
    is skipped entirely. This prevents multiple heavy processes from running
    concurrently and causing OOM / health check timeouts.

    A watchdog daemon thread monitors the process and force-kills it if it
    exceeds PIPELINE_TIMEOUT_SECONDS. This guarantees:
      1. The subprocess can NEVER hang forever.
      2. When killed, its open PostgreSQL transactions are immediately
         rolled back by the DB, releasing all locks so news_service
         can always serve frontend requests without contention.
    """
    global _current_process

    with _process_lock:
        # Check if a pipeline is already running
        if _current_process is not None and _current_process.poll() is None:
            print(
                f"Pipeline guard: previous process (PID {_current_process.pid}) is still running. "
                "Skipping this cycle.",
                flush=True,
            )
            return

        print("Spawning completely isolated background pipeline...", flush=True)
        _current_process = subprocess.Popen(
            [sys.executable, "-m", "app.services.run_all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def watchdog(p: subprocess.Popen, timeout: int):
        """
        Streams stdout in real-time AND enforces a hard timeout.

        A reader thread continuously drains stdout line-by-line so:
          1. The subprocess can never block on a full pipe buffer.
          2. Log output appears immediately in the parent's logs.

        The main thread calls p.wait(timeout=timeout) independently,
        so the timeout fires even if the subprocess is completely silent
        (e.g. frozen during an import or a network call with no output).
        """
        def _stream_output():
            try:
                for line in iter(p.stdout.readline, b""):
                    print(line.decode(errors="replace"), end="", flush=True)
            except Exception:
                pass

        reader = threading.Thread(target=_stream_output, daemon=True)
        reader.start()

        try:
            p.wait(timeout=timeout)
            reader.join(timeout=5)
            print(f"Pipeline process {p.pid} exited with code {p.returncode}.", flush=True)
        except subprocess.TimeoutExpired:
            print(
                f"Pipeline watchdog: process {p.pid} exceeded {timeout}s limit. Force killing...",
                flush=True,
            )
            p.kill()
            p.wait()
            reader.join(timeout=5)
            print(f"Pipeline watchdog: process {p.pid} killed.", flush=True)
        except Exception as e:
            print(f"Pipeline watchdog error: {e}", flush=True)
            try:
                p.kill()
                p.wait()
            except Exception:
                pass

    t = threading.Thread(
        target=watchdog,
        args=(_current_process, PIPELINE_TIMEOUT_SECONDS),
        daemon=True,
    )
    t.start()
    print(
        f"Pipeline watchdog started (PID {_current_process.pid}, timeout={PIPELINE_TIMEOUT_SECONDS}s)",
        flush=True,
    )


# ── Scheduler Setup ────────────────────────────────────────────────────────────
# Delay the very first run by 2 minutes so FastAPI finishes booting, migrations
# complete, health checks stabilise, and we don't flood the system on startup.
_initial_run_time = datetime.now() + timedelta(seconds=120)

scheduler.add_job(
    scheduled_job,
    IntervalTrigger(hours=1),
    id='news_ingestion_job',
    name='Fetch news and process clusters',
    replace_existing=True,
    next_run_time=_initial_run_time,
)


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print(
            f"Scheduler started. First pipeline run at {_initial_run_time.strftime('%H:%M:%S')}.",
            flush=True,
        )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        print("Scheduler stopped.", flush=True)


def pause_news_job():
    scheduler.pause_job('news_ingestion_job')
    print("News ingestion job paused.", flush=True)


def resume_news_job():
    scheduler.resume_job('news_ingestion_job')
    print("News ingestion job resumed.")


def trigger_news_job():
    """Execute the job immediately — only if no pipeline is currently running."""
    scheduler.add_job(scheduled_job, name='Manual News Trigger')
    print("News ingestion job triggered manually.")
