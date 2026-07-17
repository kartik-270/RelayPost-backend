from fastapi import APIRouter
from app.services.scheduler import pause_news_job, resume_news_job, trigger_news_job

router = APIRouter()

@router.post("/admin/engine/pause")
def pause_engine():
    """Pause the automated news ingestion job"""
    pause_news_job()
    return {"status": "paused", "message": "News engine paused successfully"}

@router.post("/admin/engine/resume")
def resume_engine():
    """Resume the automated news ingestion job"""
    resume_news_job()
    return {"status": "resumed", "message": "News engine resumed successfully"}

@router.post("/admin/engine/trigger")
def trigger_engine():
    """Manually trigger the news ingestion job once"""
    trigger_news_job()
    return {"status": "triggered", "message": "News engine triggered successfully"}
