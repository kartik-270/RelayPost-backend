from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://news_user:news_password@127.0.0.1:5434/news_db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

is_local = "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL or "news_db" in DATABASE_URL
connect_args = {"sslmode": "require"} if not is_local else {}

# idle_in_transaction_session_timeout: if a transaction is open but idle (e.g. frozen
# waiting for Gemini API), PostgreSQL auto-rolls it back after 30s, releasing all locks.
# statement_timeout: no single SQL statement can run for more than 60s.
connect_args["options"] = "-c idle_in_transaction_session_timeout=30000 -c statement_timeout=60000"

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
