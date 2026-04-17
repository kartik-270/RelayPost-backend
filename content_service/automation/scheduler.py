from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import os
import asyncio

from automation.engine import ArticleAutomationEngine
from automation.learning import SelfLearningEngine

async def run_pipeline_task():
    """Top-level function to run the engine with a fresh DB session (Serialization-safe)."""
    db: Session = SessionLocal()
    batch_size = int(os.getenv("AUTOMATION_BATCH_SIZE", "3"))
    try:
        engine = ArticleAutomationEngine(db)
        await engine.run_pipeline(batch_size=batch_size)
    finally:
        db.close()

async def run_learning_loop_task():
    """Top-level function to run the learning loop (Serialization-safe)."""
    db: Session = SessionLocal()
    try:
        engine = SelfLearningEngine(db)
        await engine.analyze_and_update_prompt()
    finally:
        db.close()

async def cleanup_deleted_articles_task():
    """Top-level function to clean up deleted articles (Serialization-safe)."""
    db: Session = SessionLocal()
    try:
        from crud import permanently_delete_old_articles
        permanently_delete_old_articles(db)
    finally:
        db.close()


class AutomationScheduler:
    def __init__(self):
        jobstores = {
            'default': SQLAlchemyJobStore(engine=engine)
        }
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)


    def start(self):
        """Starts the scheduler."""
        print("Starting Automation Scheduler...")
        # Run every hour at the top of the hour
        self.scheduler.add_job(
            run_pipeline_task,
            CronTrigger(minute=0), 
            id="article_automation_job",
            replace_existing=True,
            misfire_grace_time=3600
        )
        
        # Run cleanup once a day at midnight
        self.scheduler.add_job(
            cleanup_deleted_articles_task,
            CronTrigger(hour=0, minute=0),
            id="article_cleanup_job",
            replace_existing=True,
            misfire_grace_time=3600
        )

        # Run Self-Learning loop once a day at 12:00 PM
        self.scheduler.add_job(
            run_learning_loop_task,
            CronTrigger(hour=12, minute=0),
            id="self_learning_job",
            replace_existing=True,
            misfire_grace_time=3600
        )

        self.scheduler.start()

    def pause_automation(self):
        """Pauses the article automation generation job."""
        job = self.scheduler.get_job("article_automation_job")
        if job:
            job.pause()
            
    def resume_automation(self):
        """Resumes the article automation generation job."""
        job = self.scheduler.get_job("article_automation_job")
        if job:
            job.resume()


    def shutdown(self):
        """Stops the scheduler."""
        self.scheduler.shutdown()

# Singleton instance
automation_scheduler = AutomationScheduler()
