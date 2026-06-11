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
import models
from database import engine
from routers import news
from scheduler import start_scheduler

app = FastAPI(
    title="News Service API",
    description="Microservice for ingesting, processing, and serving news data.",
    version="1.0.0"
)

# Standard CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    print("Application starting... Initializing scheduler.")
    start_scheduler()

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "news_service"}

app.include_router(news.router, prefix="/api/news", tags=["News"])
