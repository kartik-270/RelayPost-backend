import uuid
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models

# --- DATA DEFINITIONS ---

CATEGORIES = [
    {"name": "Maritime Intelligence", "slug": "maritime-intelligence", "description": "Global shipping and naval strategy"},
    {"name": "Artificial Intelligence", "slug": "ai", "description": "Future of technology and policy"},
    {"name": "Global Trade", "slug": "global-trade", "description": "International commerce and logistics"},
    {"name": "Geopolitics", "slug": "geopolitics", "description": "Power dynamics and regional shifts"},
    {"name": "Technology", "slug": "technology", "description": "Cutting edge innovations"},
    {"name": "Policy & Economy", "slug": "policy-economy", "description": "Financial and political landscape"}
]

ARTICLES = [
    {
        "title": "The Silent Reshaping of Global Maritime Corridors",
        "slug": "the-silent-reshaping-of-global-maritime-corridors",
        "subtitle": "The arteries of global trade are pulsing with a new, frantic energy.",
        "excerpt": "How geopolitical tremors are redrawing the world's commercial shipping maps in real-time.",
        "template_type": models.TemplateType.STANDARD,
        "homepage_section": "Hero",
        "section_order": 1,
        "is_featured": True,
        "status": models.ArticleStatus.PUBLISHED,
        "hero_image": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200",
        "content_blocks": [
            {"id": "1", "type": "paragraph", "content": "The arteries of global trade are pulsing with a new, frantic energy. As geopolitical tremors shift the bedrock of international relations, the very maps that have guided commercial shipping for half a century are being redrawn in real-time.", "styles": {"align": "left", "fontFamily": "Merriweather"}},
            {"id": "2", "type": "heading", "content": "The End of the Hub-and-Spoke", "metadata": {"level": 2}},
            {"id": "3", "type": "paragraph", "content": "Traditional hub-and-spoke models are facing an existential challenge. Regional powers are investing in secondary 'Shadow Hubs' designed to bypass traditional bottlenecks.", "styles": {"align": "left", "fontFamily": "Inter"}},
            {"id": "4", "type": "quote", "content": "The sea does not change, but our relationship to its depths is dictated by the maps we draw in times of crisis.", "metadata": {"caption": "Admiral Horatio Vance"}}
        ],
        "secondary_keywords": ["Maritime", "Logistics", "Geopolitics"],
        "category_name": "Maritime Intelligence",
        "ai_summary": "A deep dive into how changing geopolitical alliances are forcing the global shipping industry to find alternative trade routes.",
        "views_count": 12480
    },
    {
        "title": "The Arctic Pivot: A New Era of Maritime Sovereignty",
        "slug": "the-arctic-pivot",
        "subtitle": "Melting ice is opening new corridors that challenge the status quo.",
        "excerpt": "Who really owns the Northern Sea Route, and what does it mean for global supply chains?",
        "template_type": models.TemplateType.TECH,
        "homepage_section": "TrendingNow",
        "section_order": 1,
        "status": models.ArticleStatus.PUBLISHED,
        "hero_image": "https://images.unsplash.com/photo-1663456887564-28e5b4b2e0d5?auto=format&fit=crop&w=800",
        "content_blocks": [
            {"id": "1", "type": "paragraph", "content": "For the first time in human history, the Arctic is becoming a navigable arena for commercial shipping on a scale previously thought impossible."}
        ],
        "secondary_keywords": ["Arctic", "Climate", "Trade"],
        "category_name": "Maritime Intelligence",
        "views_count": 8900
    },
    {
        "title": "Singapore 2050: Reimagining the Transshipment Hub",
        "slug": "singapore-2050",
        "status": models.ArticleStatus.PUBLISHED,
        "homepage_section": "TrendingNow",
        "section_order": 2,
        "hero_image": "https://images.unsplash.com/photo-1663456887564-28e5b4b2e0d5?auto=format&fit=crop&w=800",
        "content_blocks": [],
        "secondary_keywords": ["Singapore", "Future", "Logistics"],
        "category_name": "Maritime Intelligence"
    },
    {
        "title": "The Digital Twin: Simulation and Supply Resilience",
        "slug": "digital-twin-resilience",
        "status": models.ArticleStatus.PUBLISHED,
        "homepage_section": "ExpertAnalysis",
        "section_order": 1,
        "hero_image": "https://images.unsplash.com/photo-1648614593495-e0955bf287e5?auto=format&fit=crop&w=800",
        "content_blocks": [],
        "secondary_keywords": ["AI", "SupplyChain", "Simulation"],
        "category_name": "Artificial Intelligence"
    },
    {
        "title": "Quantum Supremacy: Beyond the Hype",
        "slug": "quantum-supremacy-beyond-hype",
        "status": models.ArticleStatus.PUBLISHED,
        "homepage_section": "ExpertAnalysis",
        "section_order": 2,
        "hero_image": "https://images.unsplash.com/photo-1681908571122-97f349e1ace0?auto=format&fit=crop&w=800",
        "content_blocks": [],
        "secondary_keywords": ["Quantum", "Computing", "Tech"],
        "category_name": "Technology"
    },
    {
        "title": "The Rise of Semi-Autonomous Freight Corridors",
        "slug": "semi-autonomous-freight",
        "status": models.ArticleStatus.PUBLISHED,
        "homepage_section": "LatestInsights",
        "section_order": 1,
        "hero_image": "https://images.unsplash.com/photo-1653549893012-b8b4fbe97630?auto=format&fit=crop&w=800",
        "content_blocks": [],
        "secondary_keywords": ["Automation", "Freight", "Logistics"],
        "category_name": "Global Trade"
    },
    {
        "title": "Decarbonizing the High Seas: A 2030 Roadmap",
        "slug": "decarbonizing-high-seas",
        "status": models.ArticleStatus.PUBLISHED,
        "homepage_section": "LatestInsights",
        "section_order": 2,
        "hero_image": "https://images.unsplash.com/photo-1498084393753-b411b2d26b34?auto=format&fit=crop&w=800",
        "content_blocks": [],
        "secondary_keywords": ["Sustainability", "Maritime", "GreenEnergy"],
        "category_name": "Maritime Intelligence"
    },
    {
        "title": "Geopolitical Shifts in the South China Sea",
        "slug": "south-china-sea-geopolitics",
        "status": models.ArticleStatus.PUBLISHED,
        "homepage_section": "LatestInsights",
        "section_order": 3,
        "hero_image": "https://images.unsplash.com/photo-1516738901171-8eb4fc13bd20?auto=format&fit=crop&w=800",
        "content_blocks": [],
        "secondary_keywords": ["Geopolitics", "Naval", "Pacific"],
        "category_name": "Geopolitics"
    }
]

# --- SEEDING LOGIC ---

def seed():
    # Ensure schema is up to date
    print("Dropping and recreating tables to sync schema...")
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    print("Seeding database...")
    
    # Random placeholder for author_id
    DUMMY_AUTHOR_ID = uuid.uuid4()
    
    # 1. Categories
    cat_map = {}
    for cat_data in CATEGORIES:
        db_cat = db.query(models.Category).filter(models.Category.slug == cat_data["slug"]).first()
        if not db_cat:
            db_cat = models.Category(**cat_data)
            db.add(db_cat)
            db.commit()
            db.refresh(db_cat)
        cat_map[cat_data["name"]] = db_cat.id
    
    # 2. Articles
    for art_data in ARTICLES:
        db_art = db.query(models.Article).filter(models.Article.slug == art_data["slug"]).first()
        if db_art:
            db.delete(db_art)
            db.commit()
            
        category_name = art_data.pop("category_name", None)
        secondary_keywords = art_data.pop("secondary_keywords", [])
        
        db_art = models.Article(
            **art_data,
            author_id=DUMMY_AUTHOR_ID,
            category_id=cat_map.get(category_name),
            secondary_keywords=secondary_keywords,
            published_at=datetime.now(timezone.utc)
        )
        db.add(db_art)
        db.commit()
        db.refresh(db_art)
        
        # Add a couple of reflections
        ref1 = models.Reflection(
            article_id=db_art.id,
            content="Fascinating analysis of the shifting corridors. We are seeing this first-hand in our logistics strategy.",
            author_name="Marcus Vance",
            author_role="Logistics Consultant",
            author_img="https://api.dicebear.com/7.x/avataaars/svg?seed=Marcus"
        )
        ref2 = models.Reflection(
            article_id=db_art.id,
            content="The point about Singapore is critical. Competition is fierce.",
            is_anonymous=True
        )
        db.add_all([ref1, ref2])
        db.commit()

    print("Seeding completed successfully!")
    db.close()

if __name__ == "__main__":
    seed()
