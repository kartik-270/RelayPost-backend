from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://content_user:content_password@127.0.0.1:5433/content_db")

# Fix for Render/Heroku postgres:// vs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Neon/Cloud DBs require SSL
is_local = "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL or "content_db" in DATABASE_URL
connect_args = {"sslmode": "require"} if not is_local else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
