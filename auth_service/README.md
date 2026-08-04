# Auth Service

The `auth_service` is a FastAPI-based microservice responsible for handling all user authentication, authorization, profile management, and billing/subscription logic for RelayPost.

## Key Features
- **JWT Authentication**: Standard OAuth2 Password Bearer flow for email/password authentication.
- **Google OAuth Integration**: Allows users to sign in or sign up using their Google accounts (`/auth/google`).
- **Role-Based Access Control (RBAC)**: Supports roles like `admin`, `publisher`, `editor`, and `user`.
- **Subscription & Billing**: Integrates with Razorpay to handle user tiers (`free`, `plus`, `pro`), webhooks, and subscription lifecycle management.
- **Email Verification & Password Resets**: Handles sending OTPs via SMTP.

## Tech Stack
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Migrations**: Alembic
- **Payments**: Razorpay SDK
- **Authentication**: Passlib (Bcrypt), PyJWT, Google Auth

## Key Commands

**1. Setup Environment**
Ensure you have a `.env` file populated with `DATABASE_URL`, `JWT_SECRET`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and SMTP credentials.

**2. Database Migrations & Running the Server**
The entire backend ecosystem, including the PostgreSQL database, runs via Docker Compose. From the root directory of the project, run:
```bash
docker compose up -d
```
This will automatically spin up the database, apply all Alembic migrations on startup, and start the `auth_service` on port 8000.

**3. Seed Admin User (via Docker)**
To bootstrap the application with a default admin user, run the seed script inside the running container:
```bash
docker compose exec auth_service python seed_admin.py
```
