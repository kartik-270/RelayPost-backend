from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session
from database import SessionLocal
import models
import numpy as np
import os
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    genai.configure(api_key=GEMINI_API_KEY)

def update_article_clusters():
    db = SessionLocal()
    try:
        # Get unclustered articles from the last 24 hours
        articles = db.query(models.Article).filter(models.Article.cluster_id == None).all()
        if len(articles) < 2:
            return
        
        texts = [f"{a.title} {a.description or ''}" for a in articles]
        
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(texts)
        
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # Simple clustering: if similarity > 0.5, they belong to the same cluster
        visited = set()
        clusters = []
        
        for i in range(len(articles)):
            if i in visited:
                continue
                
            cluster = [i]
            visited.add(i)
            
            for j in range(i + 1, len(articles)):
                if similarity_matrix[i][j] > 0.5:
                    cluster.append(j)
                    visited.add(j)
            
            clusters.append(cluster)
            
        # Get the max cluster_id from DB to ensure uniqueness
        max_cluster_id_result = db.query(models.Article).order_by(models.Article.cluster_id.desc()).first()
        current_cluster_id = 1
        if max_cluster_id_result and max_cluster_id_result.cluster_id is not None:
             current_cluster_id = max_cluster_id_result.cluster_id + 1
        
        for cluster_indices in clusters:
            for idx in cluster_indices:
                articles[idx].cluster_id = current_cluster_id
                
                # Try simple keyword extraction from the title (very basic mockup)
                title_words = set(articles[idx].title.lower().split())
                # Just mock keywords for now
                articles[idx].keywords = list(title_words)[:5] 
            
            current_cluster_id += 1
            
        db.commit()
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
            
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemma-4-26b-a4b-it")
        model = genai.GenerativeModel(model_name)
        import time
        import re

        for cluster_id, articles in cluster_map.items():
            time.sleep(2) # Prevent rate limits

            # Also fetch any other articles in the cluster to provide full context
            all_cluster_articles = db.query(models.Article).filter(models.Article.cluster_id == cluster_id).all()
            
            context_text = "\n\n".join([
                f"Headline: {a.title}\nDetails: {a.description or ''}" 
                for a in all_cluster_articles
            ])

            prompt = (
                "You are an expert news editor, SEO specialist, and fact-checker. Analyze the following grouped "
                "news reports. First, determine if the information across these sources appears to be genuine, "
                "factual, and coherent. Synthesize a single refined, highly structured narrative as a detailed 'full_analysis'. "
                "The 'full_analysis' MUST be formatted as rich HTML (using <h2>, <h3>, <p>, <ul>, <li>, <strong>, <blockquote>) so it reads like a premium, deep-dive article from the Content Engine. Include an engaging introduction, structured body paragraphs with subheadings, and a conclusive summary.\n"
                "Also generate a short 'ai_summary' (plain text), a URL-friendly 'slug', an SEO title (max 60 chars), an SEO meta description (max 160 chars), and a specific 'category' (e.g. 'Cybersecurity', 'Startups', 'Politics', 'Healthcare', rather than generic ones).\n\n"
                "Return the response in pure JSON format with these exact keys: "
                "'is_genuine' (boolean), 'category' (string), 'ai_summary', 'full_analysis' (HTML string), 'slug', 'meta_title', 'meta_description'.\n\n"
                f"Context:\n{context_text}"
            )

            max_retries = 3
            generation_config = {"temperature": 0.7, "top_p": 0.95, "response_mime_type": "application/json"}
            
            print(f"Generating Gemini SEO summary and analysis for Cluster ID {cluster_id}...")
            
            for attempt in range(max_retries):
                try:
                    response = model.generate_content(prompt, generation_config=generation_config)
                    
                    import json
                    text = response.text
                    
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
                        for article in articles:
                            article.ai_summary = data.get('ai_summary')
                            article.full_analysis = data.get('full_analysis')
                            base_slug = data.get('slug') or article.slug
                            article.slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                            article.meta_title = data.get('meta_title')
                            article.meta_description = data.get('meta_description')
                            article.is_verified = bool(data.get('is_genuine', False))
                            if data.get('category'):
                                article.category = data.get('category')
                        db.commit()
                        print(f"Successfully generated summary for cluster {cluster_id}")
                        break # Success, exit retry loop
                    else:
                        print(f"Attempt {attempt + 1}: Data missing required keys. Raw response: {text[:200]}...")
                        if attempt == max_retries - 1:
                            print(f"Failed to generate valid summary for cluster {cluster_id}")
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"Gemini Generation Attempt {attempt + 1} Failed for cluster {cluster_id}: {error_msg[:200]}")
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg and attempt < max_retries - 1:
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
                    else:
                        time.sleep(5) # Small delay for other errors before retry

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error during AI summarization: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    update_article_clusters()
    generate_ai_summaries()
