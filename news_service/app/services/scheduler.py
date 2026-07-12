from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.ingestion import process_and_store_articles
from app.services.processing import update_article_clusters, generate_ai_summaries

scheduler = BackgroundScheduler()

def scheduled_job():
    print("Running scheduled ingestion and processing...")
    process_and_store_articles()
    update_article_clusters()
    generate_ai_summaries()

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
