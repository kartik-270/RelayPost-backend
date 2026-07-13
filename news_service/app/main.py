import os
from dotenv import load_dotenv
load_dotenv()

import cloudinary
import cloudinary.uploader
import cloudinary.api

CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL")
if CLOUDINARY_URL:
    cloudinary.config(url=CLOUDINARY_URL)
elif os.environ.get("CLOUDINARY_CLOUD_NAME"):
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET")
    )

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models import models
from app.core.database import engine

try:
    models.Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Startup Warning: Database table creation failed: {e}")

from app.api.routers import news
from app.api.routers import premium as news_premium
from app.services.scheduler import start_scheduler

app = FastAPI(
    title="News Service API",
    description="Microservice for ingesting, processing, and serving news data.",
    version="1.0.0"
)

# Standard CORS setup
raw_origins = os.environ.get("CORS_ORIGINS", "")
if raw_origins:
    cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
else:
    cors_origins = []

if not cors_origins:
    cors_origins = ["https://relaypost.me"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    print("Application starting... Initializing scheduler.")
    start_scheduler()
    try:
        from app.services.cache import update_top_news_cache
        update_top_news_cache()
    except Exception as e:
        print(f"Startup Warning: Failed to populate cache on startup: {e}")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "news_service"}

app.include_router(news.router, prefix="/api/news", tags=["News"])
app.include_router(news_premium.router)
