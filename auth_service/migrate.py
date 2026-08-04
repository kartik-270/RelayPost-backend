import os
from sqlalchemy import text
from database import engine

def run_migration():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE;"))
            print("Added is_verified column")
        except Exception as e:
            print(f"Error adding is_verified: {e}")
            
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN verification_token VARCHAR NULL;"))
            print("Added verification_token column")
        except Exception as e:
            print(f"Error adding verification_token: {e}")
            
        conn.commit()
        print("Migration complete")

if __name__ == "__main__":
    run_migration()
