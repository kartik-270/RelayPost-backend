import os
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import uuid
import asyncio

import re
from sqlalchemy import func
from automation.tools import TavilyTool, GeminiTool, EmailTool, UnsplashTool
from automation.prompts import (
    TOPIC_BRAINSTORM_CORE_PROMPT, 
    TOPIC_BRAINSTORM_DYNAMIC_PROMPT, 
    CONTENT_GENERATION_CORE_PROMPT, 
    CONTENT_GENERATION_DYNAMIC_PROMPT, 
    SEO_OPTIMIZATION_PROMPT
)
import crud, models, schemas

class ArticleAutomationEngine:
    def __init__(self, db: Session):
        self.db = db
        self.tavily = TavilyTool()
        self.gemini = GeminiTool()
        self.email = EmailTool()
        self.unsplash = UnsplashTool() # Initialize UnsplashTool
        self.system_author_id = models.SYSTEM_AUTHOR_ID

    async def run_pipeline(self, batch_size: int = 3):
        """Runs the full article generation pipeline."""
        print(f"[{datetime.now()}] Starting automation pipeline for {batch_size} articles...")
        
        try:
            # 1. Topic Research (Gemini brainstorming)
            categories = [c.name for c in crud.get_categories(self.db)]
            
            # Fetch recent titles to avoid duplicates
            recent_articles = self.db.query(models.Article).order_by(models.Article.created_at.desc()).limit(20).all()
            existing_topics = [a.title for a in recent_articles]

            # Fetch a sample of keywords to encourage reuse
            keywords_list = self.db.query(models.Keyword).order_by(func.random()).limit(40).all()
            existing_keywords = ", ".join([k.tag for k in keywords_list])

            # Fetch the latest dynamic prompts from DB, otherwise fall back to prompts.py
            latest_prompt = crud.get_latest_prompt_version(self.db)
            dynamic_topic = latest_prompt.topic_brainstorm_dynamic if latest_prompt else TOPIC_BRAINSTORM_DYNAMIC_PROMPT
            dynamic_content = latest_prompt.content_generation_dynamic if latest_prompt else CONTENT_GENERATION_DYNAMIC_PROMPT

            self.current_content_prompt = dynamic_content # Store for process_single_topic

            brainstorm_prompt = TOPIC_BRAINSTORM_CORE_PROMPT.format(
                dynamic_instructions=dynamic_topic,
                categories=", ".join(categories),
                existing_topics=", ".join(existing_topics) if existing_topics else "None",
                existing_keywords=existing_keywords if existing_keywords else "None"
            )
            brainstorm_result = await self.gemini.generate_structured(brainstorm_prompt, temperature=0.9)
            if isinstance(brainstorm_result, list) and len(brainstorm_result) > 0:
                for item in brainstorm_result:
                    if isinstance(item, dict):
                        brainstorm_result = item
                        break
            if not isinstance(brainstorm_result, dict):
                brainstorm_result = {}
            raw_topics = brainstorm_result.get("topics", [])
            topics = raw_topics[:batch_size]
            
            print(f"[PIPELINE] Brainstorm returned {len(raw_topics)} topic(s). Processing {len(topics)} (batch_size={batch_size}).")
            for i, t in enumerate(topics):
                print(f"  Topic {i+1}: {t.get('title')} | template: {t.get('template_type')}")
            
            for i, topic_info in enumerate(topics):
                print(f"\n[PIPELINE] ===== Processing topic {i+1}/{len(topics)} =====")
                await self.process_single_topic(topic_info)
                print(f"[PIPELINE] ===== Finished topic {i+1}/{len(topics)} =====\n")
                
        except Exception as e:
            print(f"Pipeline Execution Failed: {e}")
            import traceback
            traceback.print_exc()
            self.log_notification("Automation Failure", f"Pipeline failed: {str(e)}", "error")

    async def process_single_topic(self, topic_info):
        """Processes a single topic through generation and SEO."""
        title = topic_info["title"]
        queries = topic_info["search_queries"]
        category_name = topic_info["category"]
        template_type = topic_info.get("template_type", "standard")
        
        print(f"Processing Topic: {title}")
        
        try:
            # 2. Gather Content (Tavily)
            research_data = []
            for query in queries:
                results = await self.tavily.search(query, max_results=3) 
                research_data.extend(results)
            
            # 3. Content Generation (Gemini)
            gen_prompt = CONTENT_GENERATION_CORE_PROMPT.format(
                dynamic_instructions=self.current_content_prompt,
                research_data=str(research_data),
                template_type=template_type
            )
            article_data = await self.gemini.generate_structured(gen_prompt, temperature=0.7)
            if isinstance(article_data, list) and len(article_data) > 0:
                for item in article_data:
                    if isinstance(item, dict):
                        article_data = item
                        break
            if not isinstance(article_data, dict):
                article_data = {}
            
            # 4. SEO & GEO Optimization
            # Fetch random keywords to pass to SEO prompt for mapping
            keywords_list = self.db.query(models.Keyword).order_by(func.random()).limit(30).all()
            existing_keywords = ", ".join([k.tag for k in keywords_list])

            seo_prompt = SEO_OPTIMIZATION_PROMPT.format(
                article_json=str(article_data),
                existing_keywords=existing_keywords
            )
            final_article_data = await self.gemini.generate_structured(seo_prompt, temperature=0.5)
            if isinstance(final_article_data, list) and len(final_article_data) > 0:
                for item in final_article_data:
                    if isinstance(item, dict):
                        final_article_data = item
                        break
            if not isinstance(final_article_data, dict):
                final_article_data = {}
            
            # Ensure required fields and fallbacks
            final_article_data["status"] = models.ArticleStatus.DRAFT
            final_article_data["author_id"] = self.system_author_id
            final_article_data["category_name"] = category_name
            
            # Clean markdown formatting from all text fields
            final_article_data = self.strip_markdown(final_article_data)
            
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
            
            # 5. Verify Structure and Images before Publishing
            is_valid = True
            
            # Check structure
            if not final_article_data.get("title") or not final_article_data.get("slug"):
                is_valid = False
            if not isinstance(final_article_data.get("content_blocks"), list) or len(final_article_data["content_blocks"]) == 0:
                is_valid = False
            
            # Check images
            if not final_article_data.get("hero_image"):
                is_valid = False
                
            valid_blocks = []
            if "content_blocks" in final_article_data:
                for block in final_article_data["content_blocks"]:
                    if block.get("type") == "image":
                        content = block.get("content")
                        if not content or not content.startswith("http"):
                            # Filter out invalid image blocks to ensure cleanliness
                            is_valid = False
                            continue
                    valid_blocks.append(block)
                final_article_data["content_blocks"] = valid_blocks
                
            if is_valid:
                final_article_data["status"] = models.ArticleStatus.PUBLISHED
                print(f"[PIPELINE] Validation passed. Publishing directly.")
            else:
                final_article_data["status"] = models.ArticleStatus.DRAFT
                print(f"[PIPELINE] Validation failed. Saving as DRAFT.")

            # 6. Save Article
            article_create = schemas.ArticleCreate(**final_article_data)
            db_article = crud.create_article(self.db, article_create)
            
            print(f"Article Saved with Local Media: {db_article.title} (ID: {db_article.id})")
            
            # 7. Notify Stakeholders
            await self.notify_stakeholders(db_article)
            
        except Exception as e:
            print(f"Failed to process topic '{title}': {e}")
            try:
                self.db.rollback()  # Recover the session for the next article
            except Exception:
                pass
            self.log_notification("Article Generation Failed", f"Topic: {title}. Error: {str(e)}", "warning")
            
        print("Waiting 5 seconds before processing next topic...")
        await asyncio.sleep(5)

    def strip_markdown(self, data):
        """Recursively strips markdown bold/italic/header formatting from all string values."""
        if isinstance(data, str):
            # Remove bold: **text** or __text__
            data = re.sub(r'\*\*(.*?)\*\*', r'\1', data)
            data = re.sub(r'__(.*?)__', r'\1', data)
            # Remove italic: *text* or _text_
            data = re.sub(r'\*(.*?)\*', r'\1', data)
            data = re.sub(r'_(.*?)_', r'\1', data)
            # Remove markdown headers: ## Title -> Title
            data = re.sub(r'^#{1,6}\s+', '', data, flags=re.MULTILINE)
            return data
        elif isinstance(data, dict):
            return {k: self.strip_markdown(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.strip_markdown(item) for item in data]
        return data

    async def save_local_image(self, remote_url: str, filename_prefix: str) -> Optional[str]:
        """Downloads an image and uploads it to Cloudinary."""
        try:
            image_bytes = await self.unsplash.download_image(remote_url)
            if not image_bytes:
                return None
            
            import cloudinary.uploader
            
            upload_result = cloudinary.uploader.upload(
                image_bytes,
                public_id=filename_prefix,
                fetch_format="auto",
                quality="auto"
            )
            
            return upload_result.get("secure_url")
            
        except Exception as e:
            print(f"Error saving image to Cloudinary: {e}")
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
        try:
            notif = models.AdminNotification(
                title=title,
                message=message,
                type=type,
                link=link
            )
            self.db.add(notif)
            self.db.commit()
        except Exception as e:
            print(f"Could not log notification: {e}")
            try:
                self.db.rollback()
            except Exception:
                pass
