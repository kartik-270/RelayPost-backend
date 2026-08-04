# Content Service

The `content_service` is the core backend API for RelayPost, handling the creation, management, and AI-generation of articles and content.

## Key Features
- **Article Management**: CRUD operations for articles, categories, and tags.
- **AI Content Generation**: Integrates heavily with Google Gemini to generate high-quality articles, SEO metadata, tags, and formatting based on prompt pipelines.
- **Automated Workflows**: Includes scheduling services and pipelines for autonomous article publishing (`app/services/automation/`).
- **Interactive AI Features**: Powers user-facing AI interactions, like "Ask AI about this article" and generating cross-article summaries.
- **Admin CMS API**: Provides the necessary endpoints for the RelayPost frontend Admin Dashboard to edit and publish content.

## Tech Stack
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Migrations**: Alembic
- **AI Models**: Google Generative AI (Gemini)

## Key Commands

**1. Setup Environment**
Ensure you have a `.env` file populated with `DATABASE_URL`, `GEMINI_API_KEY`, and authentication verification endpoints.

**2. Database Migrations & Running the Server**
The entire backend ecosystem, including the PostgreSQL database, runs via Docker Compose. From the root directory of the project, run:
```bash
docker compose up -d
```
This will automatically spin up the database, apply all Alembic migrations on startup, and start the `content_service` on port 8001.

**3. Seed Data (via Docker)**
To populate the database with initial categories and test articles, run the seed script inside the container:
```bash
docker compose exec content_service python seed_data.py
```
