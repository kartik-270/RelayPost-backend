import json
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import models
from app.services.automation.tools import GeminiTool
from app.services.automation.prompts import HOMEPAGE_PLACEMENT_PROMPT

def log_notification(db: Session, title: str, message: str, type: str = "info"):
    """Helper to log admin notifications."""
    try:
        notif = models.AdminNotification(
            title=title,
            message=message,
            type=type
        )
        db.add(notif)
        db.commit()
    except Exception as e:
        print(f"Could not log notification: {e}")
        try:
            db.rollback()
        except Exception:
            pass

class HomepagePlacementEngine:
    def __init__(self, db: Session):
        self.db = db
        self.gemini = GeminiTool()

    async def reorder_homepage_placements(self, limit: int = 30):
        """Fetches recent published articles, sends them to Gemini for curation, and updates their placements."""
        print(f"[{datetime.now()}] Starting automated homepage placement reordering...")
        try:
            # 1. Fetch recent published articles (up to the limit)
            articles = self.db.query(models.Article).filter(
                models.Article.status == models.ArticleStatus.PUBLISHED,
                models.Article.deleted_at == None
            ).order_by(models.Article.published_at.desc()).limit(limit).all()

            if not articles:
                print("No published articles found for homepage curation.")
                return

            # 2. Format article data for Gemini
            articles_data = []
            for a in articles:
                articles_data.append({
                    "id": str(a.id),
                    "title": a.title,
                    "category": a.category.name if a.category else "Uncategorized",
                    "excerpt": a.excerpt or a.subtitle or "",
                    "published_at": a.published_at.isoformat() if a.published_at else "",
                    "views_count": a.views_count,
                    "current_placement": {
                        "homepage_section": a.homepage_section,
                        "section_order": a.section_order,
                        "is_featured": a.is_featured
                    }
                })

            # 3. Call Gemini to assign placements
            prompt = HOMEPAGE_PLACEMENT_PROMPT.format(articles_json=json.dumps(articles_data, indent=2))
            result = await self.gemini.generate_structured(prompt, temperature=0.5)

            # Extract placement list from result
            if isinstance(result, list) and len(result) > 0:
                for item in result:
                    if isinstance(item, dict):
                        result = item
                        break
            if not isinstance(result, dict):
                result = {}

            placements = result.get("placements", [])
            if not isinstance(placements, list):
                placements = []

            print(f"[PLACEMENT] Gemini returned curation decisions for {len(placements)} articles.")

            # 4. Group, sort, and programmatically enforce section size limits
            section_groups = {
                "Hero": [],
                "TrendingNow": [],
                "ExpertAnalysis": [],
                "LatestInsights": []
            }

            for p in placements:
                art_id_str = p.get("article_id")
                section = p.get("homepage_section")
                order = p.get("section_order", 0)
                
                if art_id_str and section in section_groups:
                    section_groups[section].append({
                        "id": art_id_str,
                        "order": int(order) if order is not None else 999
                    })

            # Limits per section
            section_limits = {
                "Hero": 3,
                "TrendingNow": 6,
                "ExpertAnalysis": 6,
                "LatestInsights": 6
            }

            # Map containing sanitized final updates
            final_placements = {}
            for section, items in section_groups.items():
                # Sort items by assigned section_order ascending
                items.sort(key=lambda x: x["order"])
                # Limit count
                limit_num = section_limits[section]
                for idx, item in enumerate(items[:limit_num]):
                    final_placements[item["id"]] = {
                        "homepage_section": section,
                        "section_order": idx + 1,  # 1-based sequential order
                        "is_featured": True
                    }

            # 5. Apply database updates
            updated_count = 0
            for a in articles:
                art_id_str = str(a.id)
                if art_id_str in final_placements:
                    decision = final_placements[art_id_str]
                    a.homepage_section = decision["homepage_section"]
                    a.section_order = decision["section_order"]
                    a.is_featured = decision["is_featured"]
                    updated_count += 1
                else:
                    # Demoted or not assigned
                    a.homepage_section = None
                    a.section_order = 0
                    a.is_featured = False

            self.db.commit()
            msg = f"Homepage placements successfully reordered. Curated {updated_count} articles across home sections (limits strictly enforced: Hero max 3, others max 6)."
            print(f"[PLACEMENT] {msg}")
            log_notification(self.db, "Homepage Curation Success", msg, "success")

        except Exception as e:
            error_msg = f"Failed to run homepage curation: {str(e)}"
            print(f"[PLACEMENT ERROR] {error_msg}")
            import traceback
            traceback.print_exc()
            log_notification(self.db, "Homepage Curation Failure", error_msg, "error")
