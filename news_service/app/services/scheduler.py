from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.ingestion import process_and_store_articles
from app.services.processing import update_article_clusters, generate_ai_summaries

scheduler = BackgroundScheduler()

from app.services.cache import update_top_news_cache

import subprocess
import sys

def scheduled_job():
    # Use subprocess.Popen instead of multiprocessing.
    # This guarantees the background job starts in a 100% fresh Python interpreter
    # completely avoiding any locked threads or database corruption in the FastAPI server.
    print("Spawning completely isolated background pipeline...")
    subprocess.Popen([sys.executable, "-m", "app.services.run_all"])

# Run every hour
scheduler.add_job(
    scheduled_job,
    IntervalTrigger(hours=1),
    id='news_ingestion_job',
    name='Fetch news and process clusters',
    replace_existing=True
)

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print("Scheduler started.")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        print("Scheduler stopped.")

def pause_news_job():
    scheduler.pause_job('news_ingestion_job')
    print("News ingestion job paused.")

def resume_news_job():
    scheduler.resume_job('news_ingestion_job')
    print("News ingestion job resumed.")

def trigger_news_job():
    # Execute the job immediately in the background
    scheduler.add_job(scheduled_job, id='manual_news_trigger', name='Manual News Trigger')
    print("News ingestion job triggered manually.")
