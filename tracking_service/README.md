# Tracking Service

The `tracking_service` is a lightweight microservice designed to handle high-throughput analytics, view counts, and user interactions without bogging down the primary content database.

## Key Features
- **View Tracking**: Records page views for both system-generated articles and news articles.
- **Engagement Analytics**: Tracks "likes", "shares", and other user interactions.
- **Asynchronous Design**: Built to quickly absorb and acknowledge tracking events without blocking the frontend, allowing for offline aggregation if necessary.

## Tech Stack
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy ORM (Does not use Alembic; uses `create_all` during container startup).

## Key Commands

**1. Setup Environment**
Ensure you have a `.env` file populated with `DATABASE_URL`.

**2. Running the Server**
The entire backend ecosystem, including the PostgreSQL database, runs via Docker Compose. From the root directory of the project, run:
```bash
docker compose up -d
```
The startup command inside `docker-compose.yml` will automatically create the required database tables before launching the server on port 8003.
The API documentation will be available at `http://localhost:8003/docs`.
