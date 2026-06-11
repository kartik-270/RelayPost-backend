import os
from sqlalchemy import create_engine, text
from database import DATABASE_URL

def run_sql(conn, sql, msg):
    try:
        result = conn.execute(text(sql))
        conn.commit()
        if result and result.supports_execution_as_sql and result.rowcount > 0:
            print(f"✅ {msg} (Affected {result.rowcount} rows)")
        else:
            print(f"✅ {msg}")
        return True
    except Exception as e:
        print(f"❌ Error during {msg}: {e}")
        conn.rollback()
        return False

def migrate():
    print(f"Connecting to {DATABASE_URL}...")
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        print("Starting robust migration...")
        
        # 1. Column additions (will error if they exist, and that's okay)
        print("Attempting column updates...")
        run_sql(conn, "ALTER TABLE articles ADD COLUMN homepage_section VARCHAR;", "Add homepage_section")
        run_sql(conn, "ALTER TABLE articles ADD COLUMN section_order INTEGER DEFAULT 0;", "Add section_order")
        run_sql(conn, "ALTER TABLE articles ADD COLUMN theme VARCHAR DEFAULT 'STANDARD';", "Add theme")
        
        # 2. Data normalization (ALWAYS run these)
        print("Normalizing existing data...")
        
        # Theme: lowercase 'standard' -> uppercase 'STANDARD'
        run_sql(conn, "UPDATE articles SET theme = 'STANDARD' WHERE theme = 'standard' OR theme IS NULL;", "Normalize theme")
        
        # Status: lowercase -> uppercase
        run_sql(conn, "UPDATE articles SET status = UPPER(status) WHERE status = LOWER(status);", "Normalize status")
        
        # Template Type: handle native enum or varchar
        # We'll use a cast to text for safety if it's a native enum
        run_sql(conn, "UPDATE articles SET template_type = UPPER(template_type::text) WHERE template_type::text = LOWER(template_type::text);", "Normalize template_type")
        
        print("Migration process finished.")

if __name__ == "__main__":
    migrate()
