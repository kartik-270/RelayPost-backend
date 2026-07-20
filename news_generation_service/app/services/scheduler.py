from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.ingestion import process_and_store_articles
from app.services.processing import update_article_clusters, generate_ai_summaries
from datetime import datetime

scheduler = BackgroundScheduler()

from app.services.cache import update_top_news_cache

import subprocess
import sys

PIPELINE_TIMEOUT_SECONDS = 25 * 60  # 25 minutes hard limit

def scheduled_job():
    """
    Spawns the pipeline in a completely isolated subprocess.
    A watchdog daemon thread monitors the process and force-kills it
    if it exceeds PIPELINE_TIMEOUT_SECONDS. This guarantees that:
      1. The subprocess can NEVER hang forever.
      2. When killed, its open PostgreSQL transactions are immediately
         rolled back by the DB, releasing all locks so news_service
         can always serve frontend requests without contention.
    """
    print("Spawning completely isolated background pipeline...", flush=True)
    proc = subprocess.Popen([sys.executable, "-m", "app.services.run_all"])

    def watchdog(p, timeout):
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(
                f"Pipeline watchdog: process {p.pid} exceeded {timeout}s limit. Force killing...",
                flush=True
            )
            p.kill()
            p.wait()
            print(f"Pipeline watchdog: process {p.pid} killed.", flush=True)

    import threading
    t = threading.Thread(target=watchdog, args=(proc, PIPELINE_TIMEOUT_SECONDS), daemon=True)
    t.start()
    print(f"Pipeline watchdog started (PID {proc.pid}, timeout={PIPELINE_TIMEOUT_SECONDS}s)", flush=True)

# Run immediately, then every hour
scheduler.add_job(
    scheduled_job,
    IntervalTrigger(hours=1),
    id='news_ingestion_job',
    name='Fetch news and process clusters',
    replace_existing=True,
    next_run_time=datetime.now()
)

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print("Scheduler started.", flush=True)

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
    # Execute the job immediately in the background
    scheduler.add_job(scheduled_job, name='Manual News Trigger')
    print("News ingestion job triggered manually.")
