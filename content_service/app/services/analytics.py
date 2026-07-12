from collections import Counter
from sqlalchemy.orm import Session
from app.models import models

def calculate_and_cache_global_trends(db: Session):
    articles = db.query(models.Article).filter(models.Article.status == models.ArticleStatus.PUBLISHED).all()
    
    total_views = sum((a.views_count or 0) for a in articles)
    if total_views == 0:
        total_views = 1 # Avoid division by zero if there are no views at all
        
    category_views = Counter()
    for a in articles:
        if a.category_name:
            category_views[a.category_name] += (a.views_count or 0)
            
    top_categories = category_views.most_common(5)
    global_trends = []
    
    for idx, (cat, views) in enumerate(top_categories):
        percentage = round((views / total_views) * 100)
        global_trends.append({"topic": cat, "rank": idx + 1, "score": percentage})
        
    cache = db.query(models.SystemCache).filter(models.SystemCache.key == "global_trends").first()
    if not cache:
        cache = models.SystemCache(key="global_trends", value=global_trends)
        db.add(cache)
    else:
        cache.value = global_trends
        
    db.commit()
