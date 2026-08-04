from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import SessionLocal, engine
import os
import asyncio

from app.services.automation.engine import ArticleAutomationEngine
from app.services.automation.learning import SelfLearningEngine

async def run_pipeline_task():
    """Top-level function to run the engine with a fresh DB session (Serialization-safe)."""
    db: Session = SessionLocal()
    has_lock = db.execute(text("SELECT pg_try_advisory_lock(1001)")).scalar()
    if not has_lock:
        db.close()
        return
        
    try:
        batch_size = int(os.getenv("AUTOMATION_BATCH_SIZE", "3"))
        engine = ArticleAutomationEngine(db)
        await engine.run_pipeline(batch_size=batch_size)
    finally:
        db.execute(text("SELECT pg_advisory_unlock(1001)"))
        db.commit()
        db.close()

async def run_learning_loop_task():
    """Top-level function to run the learning loop (Serialization-safe)."""
    db: Session = SessionLocal()
    has_lock = db.execute(text("SELECT pg_try_advisory_lock(1002)")).scalar()
    if not has_lock:
        db.close()
        return
        
    try:
        engine = SelfLearningEngine(db)
        await engine.analyze_and_update_prompt()
    finally:
        db.execute(text("SELECT pg_advisory_unlock(1002)"))
        db.commit()
        db.close()

async def cleanup_deleted_articles_task():
    """Top-level function to clean up deleted articles (Serialization-safe)."""
    db: Session = SessionLocal()
    has_lock = db.execute(text("SELECT pg_try_advisory_lock(1003)")).scalar()
    if not has_lock:
        db.close()
        return
        
    try:
        from app.crud.crud import permanently_delete_old_articles
        permanently_delete_old_articles(db)
    finally:
        db.execute(text("SELECT pg_advisory_unlock(1003)"))
        db.commit()
        db.close()


async def run_homepage_placement_task():
    """Top-level function to curate homepage placements every 12 hours (Serialization-safe)."""
    db: Session = SessionLocal()
    has_lock = db.execute(text("SELECT pg_try_advisory_lock(1004)")).scalar()
    if not has_lock:
        db.close()
        return
        
    try:
        from app.services.automation.placement import HomepagePlacementEngine
        engine = HomepagePlacementEngine(db)
        await engine.reorder_homepage_placements()
    finally:
        db.execute(text("SELECT pg_advisory_unlock(1004)"))
        db.commit()
        db.close()


async def update_global_trends_task():
    """Top-level function to calculate global trends (Serialization-safe)."""
    db: Session = SessionLocal()
    has_lock = db.execute(text("SELECT pg_try_advisory_lock(1005)")).scalar()
    if not has_lock:
        db.close()
        return
        
    try:
        from app.services.analytics import calculate_and_cache_global_trends
        calculate_and_cache_global_trends(db)
    finally:
        db.execute(text("SELECT pg_advisory_unlock(1005)"))
        db.commit()
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
        
        self.scheduler.add_job(
            run_learning_loop_task,
            CronTrigger(hour=2), # Run at 2 AM every day
            id="self_learning_job",
            replace_existing=True,
            misfire_grace_time=3600
        )

        self.scheduler.add_job(
            cleanup_deleted_articles_task,
            CronTrigger(hour=3, minute=0), # Run at 3 AM daily
            id="cleanup_deleted_articles_job",
            replace_existing=True,
            misfire_grace_time=3600
        )

        self.scheduler.add_job(
            run_homepage_placement_task,
            CronTrigger(hour="0,12", minute=0), # Run at noon and midnight
            id="homepage_placement_job",
            replace_existing=True,
            misfire_grace_time=3600
        )
        
        # New job: update global trends every 3 hours
        self.scheduler.add_job(
            update_global_trends_task,
            CronTrigger(hour="*/3", minute=0),
            id="global_trends_job",
            replace_existing=True,
            misfire_grace_time=3600
        )

        try:
            self.scheduler.start()
        except Exception as e:
            print(f"Error starting scheduler: {e}")

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
