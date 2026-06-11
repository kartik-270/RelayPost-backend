from database import SessionLocal
import models
import uuid

def seed_discovery():
    db = SessionLocal()
    try:
        # Update Categories with images and descriptions
        cats = db.query(models.Category).all()
        featured_meta = {
            "technology": {
                "img": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&q=80&w=1200",
                "desc": "Analyzing the convergence of quantum computing, distributed systems, and the next frontier of human-machine interfaces."
            },
            "business-economy": {
                "img": "https://images.unsplash.com/photo-1611974714658-058e11e0dc4f?auto=format&fit=crop&q=80&w=1200",
                "desc": "Geopolitical economic shifts, decentralized finance protocols, and the evolution of global capital sovereignity."
            },
            "science-health": {
                "img": "https://images.unsplash.com/photo-1507413245164-6160d8298b31?auto=format&fit=crop&q=80&w=1200",
                "desc": "Breakthroughs in longevity, cellular rejuvenation, and the ethical frameworks governing planetary-scale engineering."
            },
            "lifestyle-culture": {
                "img": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&q=80&w=1200",
                "desc": "The intersection of ancestral heritage and digital modernism; exploring the new aesthetics of the hyper-connected era."
            },
            "global": {
                "img": "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?auto=format&fit=crop&q=80&w=1200",
                "desc": "Transcontinental intelligence streams capturing systemic shifts in global policy, demographics, and infrastructure."
            },
            "sports": {
                "img": "https://images.unsplash.com/photo-1504450758481-7338eba7524a?auto=format&fit=crop&q=80&w=1200",
                "desc": "The new frontier of bio-optimization, human performance analytics, and the evolution of competitive systems."
            },
            "professionals-careers": {
                "img": "https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?auto=format&fit=crop&q=80&w=1200",
                "desc": "Intelligence for the hybrid era: navigating algorithmic management and the decentralization of expertise."
            }
        }

        for cat in cats:
            slug = cat.slug.lower()
            if slug in featured_meta:
                cat.image_url = featured_meta[slug]["img"]
                cat.description = featured_meta[slug]["desc"]
            else:
                cat.description = f"Specialized intelligence corridor focusing on {cat.name} and its systemic impact on global networks."
        
        # Update some Keywords with descriptions
        kws = db.query(models.Keyword).limit(20).all()
        for kw in kws:
            kw.description = f"Analytical node investigating the latest research and market signals related to {kw.tag}."
            
        db.commit()
        print("Discovery ecosystem seeded with high-fidelity metadata.")
    except Exception as e:
        print(f"Seeding failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_discovery()
