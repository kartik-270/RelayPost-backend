from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.ingestion import process_and_store_articles
from app.services.processing import update_article_clusters, generate_ai_summaries

scheduler = BackgroundScheduler()

from app.services.cache import update_top_news_cache

import multiprocessing
import sys
import traceback

def _run_job_process():
    try:
        import os
        # Give this background process the lowest possible CPU priority 
        # so it NEVER steals CPU from the main FastAPI server.
        if hasattr(os, 'nice'):
            os.nice(19)
            
        # Stop PyTorch from spawning 100 threads and locking the CPU
        os.environ["OMP_NUM_THREADS"] = "1"
        os.environ["MKL_NUM_THREADS"] = "1"
        try:
            import torch
            torch.set_num_threads(1)
        except ImportError:
            pass

        # Dispose of inherited DB connections to avoid SSL/socket corruption in the fork
        from app.core.database import engine
        engine.dispose()
        
        print("Running scheduled ingestion and processing in background process...", flush=True)
        process_and_store_articles()
        update_article_clusters()
        generate_ai_summaries()
        update_top_news_cache()
        print("Ingestion and processing completed successfully.", flush=True)
    except Exception as e:
        print(f"ERROR in background ingestion process: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()

def scheduled_job():
    # Run the heavy ML/ingestion tasks in a completely separate process to free up the API
    p = multiprocessing.Process(target=_run_job_process)
    p.start()

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
