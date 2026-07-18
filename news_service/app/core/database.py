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

# These options are set at the connection level and protect news_service from being
# blocked by PostgreSQL row/table locks held by news_generation_service during its
# pipeline runs (ingestion, clustering, deduplication).
#
#   lock_timeout      — if a query waits >5s for a lock, abort it immediately
#   statement_timeout — if any single query takes >30s, abort it (prevents runaway queries)
#
# Both result in a clean OperationalError that FastAPI can handle gracefully,
# rather than a hung worker thread that makes the whole service unresponsive.
connect_args["options"] = "-c lock_timeout=5000 -c statement_timeout=30000"

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
