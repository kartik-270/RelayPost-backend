from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from database import SessionLocal
import os
import asyncio

from automation.engine import ArticleAutomationEngine
from automation.learning import SelfLearningEngine

class AutomationScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.batch_size = int(os.getenv("AUTOMATION_BATCH_SIZE", "3"))

    async def _run_task(self):
        """Internal method to run the engine with a fresh DB session."""
        db: Session = SessionLocal()
        try:
            engine = ArticleAutomationEngine(db)
            await engine.run_pipeline(batch_size=self.batch_size)
        finally:
            db.close()

    async def _run_learning_loop(self):
        """Internal method to run the self learning loop with a fresh DB session."""
        db: Session = SessionLocal()
        try:
            engine = SelfLearningEngine(db)
            await engine.analyze_and_update_prompt()
        finally:
            db.close()

    async def _cleanup_deleted_articles(self):
        """Delete articles that have been in trash for > 30 days."""
        db: Session = SessionLocal()
        try:
            from crud import permanently_delete_old_articles
            permanently_delete_old_articles(db)
        finally:
            db.close()


    def start(self):
        """Starts the scheduler."""
        print("Starting Automation Scheduler...")
        # Run every hour at the top of the hour
        self.scheduler.add_job(
            self._run_task,
            CronTrigger(minute=0), 
            id="article_automation_job",
            replace_existing=True
        )
        
        # Run cleanup once a day at midnight
        self.scheduler.add_job(
            self._cleanup_deleted_articles,
            CronTrigger(hour=0, minute=0),
            id="article_cleanup_job",
            replace_existing=True
        )

        # Run Self-Learning loop once a day at 12:00 PM
        self.scheduler.add_job(
            self._run_learning_loop,
            CronTrigger(hour=12, minute=0),
            id="self_learning_job",
            replace_existing=True
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
