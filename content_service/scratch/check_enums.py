import sys
import os
sys.path.append('content_service')
from database import engine
from sqlalchemy import text

def check_enums():
    with engine.connect() as conn:
        print("Checking 'templatetype' labels:")
        res = conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_type.oid = pg_enum.enumtypid WHERE pg_type.typname = 'templatetype'"))
        labels = [r[0] for r in res.fetchall()]
        print(labels)
        
        print("\nChecking 'articlestatus' labels:")
        res = conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_type.oid = pg_enum.enumtypid WHERE pg_type.typname = 'articlestatus'"))
        labels = [r[0] for r in res.fetchall()]
        print(labels)

if __name__ == "__main__":
    check_enums()
