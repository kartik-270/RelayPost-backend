# RelayPost Backend Microservices

This repository contains the high-fidelity backend architecture for **RelayPost**, an advanced maritime and technology editorial platform. The system is built using a microservice-oriented approach with **FastAPI** and **PostgreSQL**.

## Architecture Overview

### 1. Auth Service (`/auth_service`)
Handles user registration, authentication (including Google OAuth), and role-based access control (RBAC).
- **Technology**: FastAPI, SQLAlchemy, PostgreSQL, PyJWT.
- **Port**: 8000 (Local)

### 2. Content Service (`/content_service`)
Manages the entire editorial workflow, including article lifecycle (drafts, scheduled, published), categories, keywords, and media management.
- **Technology**: FastAPI, SQLAlchemy, PostgreSQL, AWS S3 (for future) / Local LargeBinary (current).
- **Port**: 8001 (Local)

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

To run the entire stack locally with a hot-reloading PostgreSQL:
```powershell
docker-compose up --build
```

---

## Backend Troubleshooting

### "Nothing reflected in Neon DB"
If the seeding script says "Seeding completed successfully!" but you don't see tables in your Neon Dashboard:
1. **Check Connection String**: Ensure the `DATABASE_URL` in your `.env` file matches the project and branch you are viewing in Neon.
2. **Neon Branches**: Neon uses branching. Ensure you are checking the "Main" branch (or the branch specified in your URI).
3. **Database Name**: By default, Neon uses `/neondb`. Confirm if your URI specifies a different database name.
