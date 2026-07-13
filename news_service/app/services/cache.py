import datetime
from app.core.database import SessionLocal
from app.models.models import Article, SystemCache
from sqlalchemy.orm import Session

def update_top_news_cache():
    """Fetch top 5 news based on views and update the database system_cache table"""
    print("Updating top news cache in database...")
    db = SessionLocal()
    try:
        from sqlalchemy import or_
        time_threshold = datetime.datetime.utcnow() - datetime.timedelta(days=2)
        import random
        # Fetch top 5 news ordered by views desc then published_at desc, verified only, from last 48 hours
        top_articles = db.query(Article).filter(
            Article.is_verified == True,
            or_(Article.published_at >= time_threshold, Article.created_at >= time_threshold)
        ).order_by(Article.views.desc(), Article.published_at.desc()).limit(5).all()
        
        # Serialize to dictionary for database storage
        serialized = []
        for a in top_articles:
            serialized.append({
                c.name: getattr(a, c.name).isoformat() if isinstance(getattr(a, c.name), datetime.date) or isinstance(getattr(a, c.name), datetime.datetime)
                        else (getattr(a, c.name).__str__() if not isinstance(getattr(a, c.name), (str, int, float, bool, type(None), list, dict)) else getattr(a, c.name))
                for c in a.__table__.columns
            })
        
        # Update or insert into system_cache
        cache_entry = db.query(SystemCache).filter(SystemCache.key == "top_news").first()
        if not cache_entry:
            cache_entry = SystemCache(key="top_news", value=serialized)
            db.add(cache_entry)
        else:
            cache_entry.value = serialized
        
        db.commit()
        print(f"Top news cache updated in database with {len(serialized)} articles.")
    except Exception as e:
        print(f"Error updating top news cache: {e}")
    finally:
        db.close()

def get_top_news_from_cache():
    """Read the top news cache from the database system_cache table"""
    db = SessionLocal()
    try:
        cache_entry = db.query(SystemCache).filter(SystemCache.key == "top_news").first()
        if cache_entry and cache_entry.value:
            return cache_entry.value
        return []
    except Exception as e:
        print(f"Error reading top news cache: {e}")
        return []
    finally:
        db.close()
