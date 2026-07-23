# News Service

The `news_service` is responsible for ingesting, clustering, and analyzing real-time news from various RSS feeds and external APIs.

## Key Features
- **RSS Ingestion Pipeline**: Scrapes news articles from popular RSS feeds (e.g., Hacker News, TechCrunch) using libraries like `feedparser` and `newspaper3k`.
- **Automated Content Clustering**: Groups similar news stories together using TF-IDF and cosine similarity to prevent duplicate reporting.
- **AI Synthesis**: Utilizes Google Gemini to summarize clustered news stories, verify factual consistency, and generate a cohesive `full_analysis` for readers.
- **Background Schedulers**: Uses APScheduler to periodically poll feeds, process clusters, and generate AI summaries without blocking the main API.

## Tech Stack
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Migrations**: Alembic
- **Scraping**: `newspaper3k`, `feedparser`, `BeautifulSoup`
- **AI Models**: Google Generative AI (Gemini)

## Key Commands

**1. Setup Environment**
Ensure you have a `.env` file populated with `DATABASE_URL`, `GEMINI_API_KEY`, and Cloudinary keys for image hosting.

**2. Database Migrations & Running the Server**
The entire backend ecosystem, including the PostgreSQL database, runs via Docker Compose. From the root directory of the project, run:
```bash
docker compose up -d
```
This will automatically spin up the database, apply all Alembic migrations on startup, and start the `news_service` on port 8002.
The API documentation will be available at `http://localhost:8002/docs`.
