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
connect_args = {
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 5,
    "keepalives_count": 3,
}
if not is_local:
    connect_args["sslmode"] = "require"

# idle_in_transaction_session_timeout prevents transaction locks from being held indefinitely
# statement_timeout prevents infinite query executions
connect_args["options"] = "-c idle_in_transaction_session_timeout=30000 -c statement_timeout=60000"

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=15,    # raises TimeoutError after 15s if all connections are checked out
    pool_size=5,
    max_overflow=5,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
