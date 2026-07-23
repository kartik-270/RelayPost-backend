# RelayPost Backend Microservices

This repository contains the high-fidelity backend architecture for **RelayPost**, an advanced maritime and technology editorial platform. The system is built using a microservice-oriented approach with **FastAPI** and **PostgreSQL**.

## Architecture Overview

RelayPost is composed of a Next.js 14 frontend and four FastAPI microservices:

### 1. Auth Service (`/auth_service`)
Handles user registration, JWT authentication, Google OAuth, Role-Based Access Control (RBAC), and Razorpay subscriptions.
- **Technology**: FastAPI, SQLAlchemy, PostgreSQL, Alembic.
- **Port**: 8000

### 2. Content Service (`/content_service`)
Manages the editorial workflow, manual article publishing, category management, and Google Gemini AI generation pipelines.
- **Technology**: FastAPI, SQLAlchemy, PostgreSQL, Alembic, Gemini SDK.
- **Port**: 8001

### 3. News Service (`/news_service`)
Automates ingestion of external RSS feeds, clustering of similar news stories, and background AI summarization.
- **Technology**: FastAPI, PostgreSQL, `newspaper3k`, `feedparser`, APScheduler.
- **Port**: 8002

### 4. Tracking Service (`/tracking_service`)
A lightweight, high-throughput service for recording page views and engagement analytics.
- **Technology**: FastAPI, PostgreSQL.
- **Port**: 8003

### 5. RelayPost Frontend (`/RelayPost`)
The public-facing Next.js application and internal CMS admin dashboard.
- **Technology**: Next.js 14 (App Router), Tailwind CSS.
- **Port**: 3000

---

## Production Deployment (Render + Neon DB)

The system is configured for a professional deployment on **Render.com** using **Neon.tech** as the PostgreSQL provider.

### 1. Database Setup (Neon)
You must create **two separate databases** (one for each service) and update the `DATABASE_URL` in your environment variables.
- Neon requires `sslmode=require` which is handled automatically by our `database.py` logic.

### 2. Deployment via Render Blueprint
We have provided a `render.yaml` file in the root directory. To deploy:
1. Connect this GitHub repo to Render.
2. Select **"Blueprint"** from the New menu.
3. Configure the following Environment Variables in the Render dashboard:
   - `DATABASE_URL` (Auth/Content specific)
   - `JWT_SECRET` (Must match for both services)
   - `CORS_ORIGINS` (Set to your frontend URL)
   - `MEDIA_BASE_URL` (Set to your Content Service production URL)

---

## Database Migration & Seeding

To initialize your cloud database with high-fidelity editorial content:

### Auth Service Initialization:
```powershell
cd auth_service
python -c "from database import engine; import models; models.Base.metadata.create_all(bind=engine)"
```

### Content Service Seeding:
```powershell
cd content_service
python seed_data.py
```
> [!IMPORTANT]
> The seeding script will **drop existing tables** and recreate them to ensure the schema is perfectly synced with the latest models.

## Local Development (Docker)

To run the entire stack locally using Docker Compose, which sets up the database, `auth_service`, `content_service`, and `news_service`:

```powershell
# Build and start all services in detached mode
docker compose up -d --build

# Restart services if you make changes to their .env files
docker compose restart
```