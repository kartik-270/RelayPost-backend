"""
Tracking Service — FastAPI app.
Port: 8003 (internal docker network only).

Endpoints:
  POST /usage/check   — check if a user can use a feature
  POST /usage/track   — record usage
  GET  /usage/status/{user_id}?tier=... — full snapshot
"""
import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.models import models
from app.crud import crud
from app.core.database import engine, get_db

# Create tables on startup
try:
    models.Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Startup Warning: DB creation failed: {e}")

app = FastAPI(title="RelayPost Tracking Service", version="1.0.0")

import os

raw_origins = os.environ.get("CORS_ORIGINS", "")
if raw_origins:
    cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
else:
    cors_origins = ["https://relaypost.me"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "online", "service": "RelayPost Tracking Service", "version": "1.0.0"}


class CheckRequest(BaseModel):
    user_id: str
    feature: str
    tier: str


class TrackRequest(BaseModel):
    user_id: str
    feature: str
    tier: str
    count: int = 1


@app.post("/usage/check")
def check_usage(payload: CheckRequest, db: Session = Depends(get_db)):
    """
    Check if a user can use a feature right now.
    Called by content_service and news_service before processing premium requests.
    """
    result = crud.check_limit(db, payload.user_id, payload.feature, payload.tier)
    return result


@app.post("/usage/track")
def track_usage(payload: TrackRequest, db: Session = Depends(get_db)):
    """
    Record usage of a feature.
    Called after successful premium feature execution.
    """
    result = crud.track_usage(db, payload.user_id, payload.feature, payload.tier, payload.count)
    return result


@app.get("/usage/status/{user_id}")
def get_usage_status(user_id: str, tier: str = "free", db: Session = Depends(get_db)):
    """
    Full usage status across all features.
    Used by the frontend to show usage meters.
    """
    return crud.get_usage_status(db, user_id, tier)
