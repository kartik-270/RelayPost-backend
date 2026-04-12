import sys
import os
sys.path.append('content_service')
from database import engine
from sqlalchemy import text

def add_enum_values():
    with engine.connect() as conn:
        with conn.execution_options(isolation_level="AUTOCOMMIT"):
            try:
                conn.execute(text("ALTER TYPE templatetype ADD VALUE 'GUIDE'"))
                print("Added GUIDE")
            except Exception as e:
                print(f"GUIDE error (might already exist): {e}")
            
            try:
                conn.execute(text("ALTER TYPE templatetype ADD VALUE 'TREND'"))
                print("Added TREND")
            except Exception as e:
                print(f"TREND error (might already exist): {e}")

if __name__ == "__main__":
    add_enum_values()
