import os
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import uuid
import asyncio

from automation.tools import TavilyTool, GeminiTool, EmailTool, UnsplashTool
from automation.prompts import TOPIC_BRAINSTORM_PROMPT, CONTENT_GENERATION_PROMPT, SEO_OPTIMIZATION_PROMPT
import crud, models, schemas

class ArticleAutomationEngine:
    def __init__(self, db: Session):
        self.db = db
        self.tavily = TavilyTool()
        self.gemini = GeminiTool()
        self.email = EmailTool()
        self.unsplash = UnsplashTool() # Initialize UnsplashTool
        self.system_author_id = models.SYSTEM_AUTHOR_ID

    async def run_pipeline(self, batch_size: int = 1):
        """Runs the full article generation pipeline."""
        print(f"[{datetime.now()}] Starting automation pipeline for {batch_size} articles...")
        
        try:
            # 1. Topic Research (Gemini brainstorming)
            categories = [c.name for c in crud.get_categories(self.db)]
            
            # Fetch recent titles to avoid duplicates
            recent_articles = self.db.query(models.Article).order_by(models.Article.created_at.desc()).limit(20).all()
            existing_topics = [a.title for a in recent_articles]

            brainstorm_prompt = TOPIC_BRAINSTORM_PROMPT.format(
                categories=", ".join(categories),
                existing_topics=", ".join(existing_topics) if existing_topics else "None"
            )
            brainstorm_result = await self.gemini.generate_structured(brainstorm_prompt)
            topics = brainstorm_result.get("topics", [])[:batch_size]
            
            for topic_info in topics:
                await self.process_single_topic(topic_info)
                
        except Exception as e:
            print(f"Pipeline Execution Failed: {e}")
            self.log_notification("Automation Failure", f"Pipeline failed: {str(e)}", "error")

    async def process_single_topic(self, topic_info):
        """Processes a single topic through generation and SEO."""
        title = topic_info["title"]
        queries = topic_info["search_queries"]
        category_name = topic_info["category"]
        
        print(f"Processing Topic: {title}")
        
        try:
            # 2. Gather Content (Tavily)
            research_data = []
            for query in queries:
                results = await self.tavily.search(query, max_results=3) 
                research_data.extend(results)
            
            # 3. Content Generation (Gemini)
            gen_prompt = CONTENT_GENERATION_PROMPT.format(research_data=str(research_data))
            article_data = await self.gemini.generate_structured(gen_prompt)
            
            # 4. SEO & GEO Optimization
            seo_prompt = SEO_OPTIMIZATION_PROMPT.format(article_json=str(article_data))
            final_article_data = await self.gemini.generate_structured(seo_prompt)
            
            # Ensure required fields and fallbacks
            final_article_data["status"] = models.ArticleStatus.DRAFT
            final_article_data["author_id"] = self.system_author_id
            final_article_data["category_name"] = category_name
            
            # Fallbacks for slug, subtitle
            if not final_article_data.get("slug"):
                import re
                base_slug = final_article_data.get("title", title).lower()
                final_article_data["slug"] = re.sub(r'[^a-z0-9]+', '-', base_slug).strip('-')
                
            if not final_article_data.get("subtitle"):
                final_article_data["subtitle"] = f"An analytical deep-dive into {title}."

            # --- LOCAL IMAGE HOSTING ---
            
            # Create a temporary article ID if we need to link media before create
            temp_article_id = uuid.uuid4() 
            # (Actually, we can create the article first or just save media without ID then update)
            # Let's save media without article_id and update it later if needed, 
            # or just use the article's eventual ID.
            
            # 1. Fetch & Save Hero Image
            hero_query = final_article_data.get("image_prompt") or title or category_name
            hero_url = await self.unsplash.search_image(hero_query)
            if hero_url:
                local_hero_url = await self.save_local_image(hero_url, "hero_" + final_article_data["slug"])
                if local_hero_url:
                    final_article_data["hero_image"] = local_hero_url
            
            if not final_article_data.get("hero_image"):
                final_article_data["hero_image"] = "https://images.unsplash.com/photo-1544411047-c491574abb46?q=80&w=1200&auto=format&fit=crop"

            # 2. Fetch & Save Inline Images
            if "content_blocks" in final_article_data:
                for block in final_article_data["content_blocks"]:
                    if block.get("type") == "image":
                        block_query = block.get("metadata", {}).get("altText") or title
                        img_url = await self.unsplash.search_image(block_query)
                        if img_url:
                            local_img_url = await self.save_local_image(img_url, "inline_" + uuid.uuid4().hex[:8])
                            if local_img_url:
                                block["content"] = local_img_url
            
            # 5. Save as Draft
            article_create = schemas.ArticleCreate(**final_article_data)
            db_article = crud.create_article(self.db, article_create)
            
            print(f"Article Saved with Local Media: {db_article.title} (ID: {db_article.id})")
            
            # 6. Notify Stakeholders
            await self.notify_stakeholders(db_article)
            
        except Exception as e:
            print(f"Failed to process topic '{title}': {e}")
            self.log_notification("Article Generation Failed", f"Topic: {title}. Error: {str(e)}", "warning")
            
        print("Waiting 30 seconds before processing next potential topic to avoid rate limits...")
        await asyncio.sleep(30)

    async def save_local_image(self, remote_url: str, filename_prefix: str) -> Optional[str]:
        """Downloads an image and saves it to the local Media table."""
        try:
            image_bytes = await self.unsplash.download_image(remote_url)
            if not image_bytes:
                return None
            
            # Deduce filename/ext
            filename = f"{filename_prefix}.jpg"
            
            # Save to Database
            db_media = crud.create_media(
                db=self.db,
                filename=filename,
                content_type="image/jpeg",
                data=image_bytes,
                size=len(image_bytes)
            )
            
            # Construct Local URL
            # Note: This should match the backend's media serving endpoint
            base_url = os.getenv("BACKEND_URL", "http://localhost:8001")
            return f"{base_url}/public/media/{db_media.id}"
            
        except Exception as e:
            print(f"Error saving local image: {e}")
            return None

    async def notify_stakeholders(self, article):
        """Notifies admins and publishers via DB and Email."""
        # A. Database Notification
        msg = f"New AI-generated draft ready for review: '{article.title}'."
        self.log_notification("New Article Draft", msg, "success", f"/admin/articles/{article.id}")
        
        # B. Email Notification
        recipients = os.getenv("NOTIFICATION_RECIPIENTS", "").split(";")
        recipients = [r.strip() for r in recipients if r.strip()]
        
        if recipients:
            subject = f"[RelayPost] AI Draft Ready: {article.title}"
            html = f"""
            <h2>New Automated Draft</h2>
            <p>The Article Automation Engine has generated a new draft for your review.</p>
            <p><strong>Title:</strong> {article.title}</p>
            <p><strong>Category:</strong> {article.category.name if article.category else 'General'}</p>
            <p>Please review and publish it at the following link:</p>
            <p><a href='{os.getenv("FRONTEND_URL", "http://localhost:3000")}/admin/editor/{article.id}'>Open Editor</a></p>
            """
            await self.email.send_notification(recipients, subject, html)

    def log_notification(self, title: str, message: str, type: str = "info", link: str = None):
        """Logs a notification to the AdminNotification table."""
        notif = models.AdminNotification(
            title=title,
            message=message,
            type=type,
            link=link
        )
        self.db.add(notif)
        self.db.commit()
