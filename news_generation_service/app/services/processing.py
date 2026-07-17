# Removed sklearn imports as we use PostgreSQL for similarity search
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import SessionLocal
from app.models import models
# Removed numpy as we use PostgreSQL for vector operations
import os
from datetime import datetime, timedelta
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    genai.configure(api_key=GEMINI_API_KEY)

def backfill_missing_embeddings():
    """
    Before clustering, find any recent articles that were saved without an
    embedding (e.g. because all API keys were briefly rate-limited during
    ingestion) and attempt to embed them now using the same multi-key model.
    This ensures no article is permanently stuck without an embedding.
    """
    from app.services.ingestion import get_embedding_model
    import time

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=12)
        articles_without_embeddings = db.query(models.Article).filter(
            models.Article.embedding == None,
            models.Article.cluster_id == None,
            models.Article.created_at >= cutoff
        ).all()

        if not articles_without_embeddings:
            return

        print(f"Backfilling embeddings for {len(articles_without_embeddings)} article(s)...")
        model = get_embedding_model()
        backfilled = 0

        for article in articles_without_embeddings:
            text_for_embedding = f"{article.title or ''} {article.description or ''}".strip()
            if not text_for_embedding:
                continue
            try:
                embedding = model.embed_one(text_for_embedding)
                if embedding is not None:
                    article.embedding = embedding
                    db.commit()
                    backfilled += 1
                    time.sleep(0.5)  # light rate-limit guard
            except Exception as e:
                db.rollback()
                print(f"Backfill embedding failed for article {article.id}: {e}")

        print(f"Backfill complete: {backfilled}/{len(articles_without_embeddings)} article(s) re-embedded.")
    except Exception as e:
        print(f"Error during embedding backfill: {e}")
    finally:
        db.close()


def cleanup_duplicate_articles():
    """
    Remove duplicate articles by URL/slug in a single atomic statement,
    avoiding the select-then-delete race with concurrent ingestion.
    """
    db = SessionLocal()
    try:
        url_result = db.execute(text("""
            DELETE FROM articles a
            USING articles b
            WHERE a.url = b.url
              AND a.url IS NOT NULL AND a.url != ''
              AND (a.created_at, a.id) < (b.created_at, b.id)
        """))
        db.commit()
        if url_result.rowcount:
            print(f"Database Cleanup: Removed {url_result.rowcount} duplicate URL row(s).")

        slug_result = db.execute(text("""
            DELETE FROM articles a
            USING articles b
            WHERE a.slug = b.slug
              AND a.slug IS NOT NULL AND a.slug != ''
              AND (a.created_at, a.id) < (b.created_at, b.id)
        """))
        db.commit()
        if slug_result.rowcount:
            print(f"Database Cleanup: Removed {slug_result.rowcount} duplicate slug row(s).")

        # Critical: clear the ORM identity map so subsequent queries in this
        # session don't hold stale references to rows just deleted via raw SQL
        db.expire_all()
    except Exception as e:
        db.rollback()
        print(f"Database Cleanup Error: {e}")
    finally:
        db.close()

def update_article_clusters():
    # First, clean up any duplicate URLs to prevent UniqueViolations during updates
    cleanup_duplicate_articles()

    # Next, retry embedding for any articles that were saved without one
    backfill_missing_embeddings()

    db = SessionLocal()
    try:
        # Only cluster articles ingested in the last 12 hours to prevent stale mixing
        cutoff = datetime.utcnow() - timedelta(hours=12)
        unclustered_articles = db.query(models.Article).filter(
            models.Article.cluster_id == None,
            models.Article.created_at >= cutoff
        ).all()
        if not unclustered_articles:
            return
        
        # Ensure the sequence exists (PostgreSQL specific)
        db.execute(text("CREATE SEQUENCE IF NOT EXISTS article_cluster_id_seq START WITH 1;"))
        db.commit()
        
        clustered_count = 0
        failed_count = 0
        for article in unclustered_articles:
            try:
                if article.embedding is not None:
                    # Use vector similarity to find an existing cluster to join
                    nearest = db.query(
                        models.Article,
                        models.Article.embedding.cosine_distance(article.embedding).label("distance")
                    ).filter(
                        models.Article.id != article.id,
                        models.Article.cluster_id.isnot(None),
                        models.Article.created_at >= cutoff
                    ).order_by(
                        models.Article.embedding.cosine_distance(article.embedding)
                    ).first()
                    
                    if nearest and nearest.distance is not None and nearest.distance < 0.18:
                        article.cluster_id = nearest.Article.cluster_id
                    else:
                        result = db.execute(text("SELECT nextval('article_cluster_id_seq')"))
                        article.cluster_id = result.scalar()
                else:
                    # No embedding — still assign a solo cluster so this article is
                    # not permanently invisible. It will be AI-processed on its own.
                    print(f"Article {article.id} has no embedding, assigning solo cluster.")
                    result = db.execute(text("SELECT nextval('article_cluster_id_seq')"))
                    article.cluster_id = result.scalar()
                
                db.commit()
                clustered_count += 1
            except Exception as e:
                db.rollback()
                failed_count += 1
                print(f"Failed to cluster article {article.id}: {e}")

        print(f"Clustering complete: {clustered_count} clustered, {failed_count} failed.")
    except Exception as e:
        db.rollback()
        print(f"Error during clustering: {e}")
    finally:
        db.close()

def generate_ai_summaries():
    """
    Uses Gemini to generate a refined article for each cluster
    that lacks an ai_summary.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        print("Gemini API key missing. Skipping AI summarization.")
        return

    db = SessionLocal()
    try:
        # Find articles that belong to a cluster but have no AI summary
        unsummarized_articles = db.query(models.Article).filter(
            models.Article.cluster_id.isnot(None),
            models.Article.ai_summary.is_(None)
        ).all()

        if not unsummarized_articles:
            return

        # Group by cluster
        cluster_map = {}
        for article in unsummarized_articles:
            if article.cluster_id not in cluster_map:
                cluster_map[article.cluster_id] = []
            cluster_map[article.cluster_id].append(article)
            
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemma-4-31b-it")
        fallback_model_name = "gemma-4-26b-a4b-it"
        
        primary_key = os.getenv("GEMINI_API_KEY")
        secondary_key = os.getenv("GEMINI_API_KEY_SECONDARY")
        api_keys = [k for k in [primary_key, secondary_key] if k]
        current_key_idx = 0
        
        model = genai.GenerativeModel(model_name)
        rate_limit_hits = 0
        import time
        import re

        for cluster_id, articles in cluster_map.items():
            # Rotate API keys round-robin if multiple keys are provided
            if api_keys:
                genai.configure(api_key=api_keys[current_key_idx])
                model = genai.GenerativeModel(model_name)
                current_key_idx = (current_key_idx + 1) % len(api_keys)

            # Gemma API Limits: 30 RPM, 16k TPM. 
            # With 2 keys, we can safely reduce sleep to 5s (12 requests/min, ~24k TPM shared across 2 keys)
            time.sleep(5) 

            # Fetch up to 3 articles per cluster to keep context small and token count low
            all_cluster_articles = db.query(models.Article).filter(models.Article.cluster_id == cluster_id).limit(3).all()
            
            context_text = "\n\n".join([
                f"Headline: {a.title}\nDetails: {a.description or ''}\nContent: {(a.content or '')[:800]}" 
                for a in all_cluster_articles
            ])

            prompt = (
                "You are an expert news editor, SEO specialist, and fact-checker. Analyze the following grouped "
                "news reports. First, determine if the information across these sources appears to be genuine, "
                "factual, and coherent. Synthesize a highly detailed, deeply analyzed, and comprehensive narrative as 'full_analysis'. "
                "The 'full_analysis' MUST be at least 5-7 long paragraphs. To achieve this length, you must expand upon the context by providing relevant background information, explaining the broader implications of the event, discussing historical context, and predicting future trends based on your expert knowledge.\n"
                "CRITICAL RELEVANCE RULE: The 'Context' below contains extracted factual sentences (not the full raw text). While you must use your expert knowledge to expand on the topic, your entire analysis MUST remain explicitly and strictly anchored to these specific facts. Do NOT pivot to unrelated news stories, hallucinate events that did not happen, or simply paraphrase the input. Every paragraph must directly tie back to explaining or analyzing the core news event.\n"
                "HALLUCINATION SAFETY VALVE: If the provided news event is highly niche, hyper-local, or you possess absolutely zero prior world knowledge about it, DO NOT invent facts or history just to reach the 5-7 paragraph length. In this specific case, write a shorter, concise analysis strictly based on the provided context to guarantee 100% factual accuracy.\n"
                "IMPORTANT FORMATTING: The 'full_analysis' MUST be formatted as standard Markdown (using ##, ###, **, *, -, >) so it renders perfectly in our frontend. Do NOT use HTML tags. Include an engaging introduction, deeply analytical body paragraphs with subheadings, and a conclusive summary.\n"
                "Also generate a crisp 'ai_summary' (plain text, strictly 2-3 short sentences max, under 3-4 lines total), a URL-friendly 'slug', an SEO title (max 60 chars), an SEO meta description (max 160 chars), and a specific 'category'.\n\n"
                "CRITICAL CATEGORY RULE: You MUST choose the category from this EXACT list: ['World News', 'India News', 'Politics', 'Business', 'Technology', 'Science', 'Health', 'Sports', 'Entertainment']. Do not invent or use any other category names.\n\n"
                "Return a JSON object with these EXACT keys:\n"
                "'is_genuine' (boolean), 'category' (string), 'ai_summary', 'full_analysis' (Markdown string), 'slug', 'meta_title', 'meta_description'.\n\n"
                f"Context:\n{context_text}"
            )

            max_retries = 3
            generation_config = {"temperature": 0.7, "top_p": 0.95, "response_mime_type": "application/json"}
            
            print(f"Generating Gemini SEO summary and analysis for Cluster ID {cluster_id}...")
            
            for attempt in range(max_retries):
                try:
                    response = model.generate_content(
                        prompt, 
                        generation_config=generation_config,
                        request_options={"timeout": 60}
                    )
                    
                    import json
                    import re
                    
                    text = response.text
                    
                    # Clean up common Gemma JSON formatting artifacts
                    text = text.strip()
                    if text.startswith("```json"):
                        text = text[7:]
                    elif text.startswith("```"):
                        text = text[3:]
                    if text.endswith("```"):
                        text = text[:-3]
                    text = text.strip()
                    
                    # Use raw_decode loop to extract all valid JSON objects/arrays
                    decoder = json.JSONDecoder()
                    pos = 0
                    parsed_objects = []
                    while pos < len(text):
                        start_obj = text.find('{', pos)
                        start_arr = text.find('[', pos)
                        
                        start = -1
                        if start_obj != -1 and start_arr != -1:
                            start = min(start_obj, start_arr)
                        elif start_obj != -1:
                            start = start_obj
                        elif start_arr != -1:
                            start = start_arr
                            
                        if start == -1:
                            break
                            
                        try:
                            obj, end_pos = decoder.raw_decode(text[start:])
                            parsed_objects.append(obj)
                            pos = start + end_pos
                        except json.JSONDecodeError:
                            pos = start + 1
                    
                    data = None
                    if parsed_objects:
                        # Normalize lists containing a single dict or other list
                        normalized_objects = []
                        for obj in parsed_objects:
                            curr = obj
                            while isinstance(curr, list) and len(curr) == 1:
                                curr = curr[0]
                            normalized_objects.append(curr)
                        
                        # Also include any dicts nested within top-level lists
                        extended_objects = []
                        for obj in normalized_objects:
                            extended_objects.append(obj)
                            if isinstance(obj, list):
                                for item in obj:
                                    if isinstance(item, dict):
                                        extended_objects.append(item)

                        # Prioritize object matching our expected schema
                        for obj in reversed(extended_objects):
                            if isinstance(obj, dict) and ('is_genuine' in obj or 'ai_summary' in obj or 'full_analysis' in obj):
                                data = obj
                                break
                        if not data:
                            # Fallback to the last parsed dict
                            for obj in reversed(extended_objects):
                                if isinstance(obj, dict):
                                    data = obj
                                    break
                    
                    if not data:
                        # Fallback to standard loads if raw_decode found nothing
                        try:
                            parsed = json.loads(text)
                            while isinstance(parsed, list) and len(parsed) == 1:
                                parsed = parsed[0]
                            if isinstance(parsed, dict):
                                data = parsed
                        except Exception:
                            pass
                    
                    if data and ('ai_summary' in data or 'full_analysis' in data):
                        import uuid
                        primary_article = articles[0]
                        primary_article.ai_summary = data.get('ai_summary')
                        primary_article.full_analysis = data.get('full_analysis')
                        base_slug = data.get('slug') or primary_article.slug
                        primary_article.slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                        primary_article.meta_title = data.get('meta_title')
                        primary_article.meta_description = data.get('meta_description')
                        is_genuine = bool(data.get('is_genuine', False))
                        primary_article.is_verified = is_genuine
                        primary_article.published_at = datetime.utcnow() # Set publish time to when the AI summary is generated on our site
                        if data.get('category'):
                            primary_article.category = data.get('category')
                            
                        # Secondary articles are kept as related sources (not verified)
                        # so they don't duplicate the primary on the frontend.
                        for other_article in articles[1:]:
                            other_article.is_verified = False
                            
                        db.commit()
                        print(f"Successfully generated summary for cluster {cluster_id}")
                        break # Success, exit retry loop
                    else:
                        print(f"Attempt {attempt + 1}: Data missing required keys. Raw response: {text[:200]}...")
                        if attempt == max_retries - 1:
                            print(f"Failed to generate valid summary for cluster {cluster_id}")
                            articles[0].ai_summary = "[GENERATION_FAILED]"
                            db.commit()
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"Gemini Generation Attempt {attempt + 1} Failed for cluster {cluster_id}: {error_msg[:200]}")
                    
                    if "response.parts quick accessor requires a single candidate" in error_msg or "blocked" in error_msg.lower():
                        print(f"Skipping cluster {cluster_id} due to Gemini safety block.")
                        articles[0].ai_summary = "[GENERATION_SKIPPED_SAFETY]"
                        db.commit()
                        break

                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        rate_limit_hits += 1
                        if rate_limit_hits > 3 and model_name != fallback_model_name:
                            print(f"Hit rate limit {rate_limit_hits} times, falling back to {fallback_model_name}")
                            model_name = fallback_model_name
                            model = genai.GenerativeModel(model_name)
                            rate_limit_hits = 0  # reset after fallback
                        
                        if attempt < max_retries - 1:
                            import re
                            match = (
                                re.search(r'Please retry in (\d+)', error_msg) or
                                re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', error_msg)
                            )
                            wait_time = int(match.group(1)) + 5 if match else 60 * (attempt + 1)
                            print(f"Rate limited. Retrying in {wait_time} seconds...")
                            time.sleep(wait_time)
                        elif attempt == max_retries - 1:
                            print(f"Warning: Failed to generate summary for cluster {cluster_id} after {max_retries} attempts.")
                            articles[0].ai_summary = "[GENERATION_FAILED]"
                            db.commit()
                    elif attempt == max_retries - 1:
                        print(f"Warning: Failed to generate summary for cluster {cluster_id} after {max_retries} attempts.")
                        articles[0].ai_summary = "[GENERATION_FAILED]"
                        db.commit()
                    else:
                        time.sleep(10) # Wait 10 seconds on general internal errors before retry

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error during AI summarization: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    update_article_clusters()
    generate_ai_summaries()
