import os
import html
import feedparser
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import models
from app.core.database import SessionLocal
from newspaper import Article as NewspaperArticle, Config as NewspaperConfig
import nltk

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

# Load embedding model lazily to prevent API startup crashes
embedding_model = None

class GeminiEmbeddingModel:
    """
    Embeds text using the Gemini API with round-robin rotation across
    multiple API keys (GEMINI_API_KEY, GEMINI_API_KEY_SECONDARY,
    GEMINI_API_KEY_TERTIARY). Each key has a ~30K TPM limit; rotating
    across 3 keys effectively gives ~90K TPM combined throughput.
    On a 429 rate-limit hit, the next key is tried immediately.
    """

    def __init__(self):
        import os
        keys = [
            os.environ.get("GEMINI_API_KEY"),
            os.environ.get("GEMINI_API_KEY_SECONDARY"),
            os.environ.get("GEMINI_API_KEY_TERTIARY"),
        ]
        # Filter out missing/placeholder keys
        self._keys = [k for k in keys if k and k != "your_gemini_api_key_here"]
        self._current_idx = 0
        if not self._keys:
            print("Warning: No Gemini API keys configured for embeddings.")
        else:
            print(f"GeminiEmbeddingModel initialized with {len(self._keys)} API key(s).")

    def _next_key(self):
        """Advance to the next key in round-robin order."""
        self._current_idx = (self._current_idx + 1) % len(self._keys)

    def embed_one(self, text: str):
        """
        Embed a single text string, rotating through API keys.
        Returns a list of 384 floats, or None if all keys fail.
        """
        import google.generativeai as genai

        if not self._keys:
            return None

        # Try each key at most once before giving up
        for attempt in range(len(self._keys)):
            api_key = self._keys[self._current_idx]
            try:
                genai.configure(api_key=api_key)
                result = genai.embed_content(
                    model="models/gemini-embedding-2",
                    content=text,
                    output_dimensionality=384
                )
                # Advance key index for the NEXT call (round-robin)
                self._next_key()
                return result['embedding']

            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    print(f"Embedding key [{self._current_idx}] rate limited — switching to next key.")
                    self._next_key()
                    # No sleep — just try the next key immediately
                else:
                    print(f"Embedding failed on key [{self._current_idx}]: {err[:120]}")
                    self._next_key()

        print(f"All {len(self._keys)} embedding key(s) failed for this text.")
        return None

def get_embedding_model():
    global embedding_model
    if embedding_model is None:
        print("Initializing Gemini embedding model...")
        embedding_model = GeminiEmbeddingModel()
    return embedding_model


RSS_FEEDS = {
    "general": [
        "https://feeds.reuters.com/Reuters/worldNews",
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://apnews.com/hub/ap-top-news?output=rss",
        "https://www.theguardian.com/world/rss",
    ],
    "technology": [
        "https://feeds.reuters.com/reuters/technologyNews",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://www.theguardian.com/uk/technology/rss",
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "http://feeds.arstechnica.com/arstechnica/index",
        "https://venturebeat.com/feed/",
        "https://news.ycombinator.com/rss",
    ],
    "ai": [
        "https://openai.com/news/rss.xml",
        "https://deepmind.google/blog/rss.xml",
        "https://www.anthropic.com/news/rss.xml",
        "https://huggingface.co/blog/feed.xml",
    ],
    "business": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://finance.yahoo.com/news/rssindex",
    ],
    "crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ],
    "sports": [
        "https://www.espn.com/espn/rss/news",
        "https://www.cricbuzz.com/rss-news",
    ],
    "india": [
        "https://www.thehindu.com/news/national/feeder/default.rss",
        "https://indianexpress.com/feed/",
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "https://feeds.feedburner.com/ndtvnews-top-stories",
        "https://www.hindustantimes.com/feeds/rss/latest/rssfeed.xml",
    ]
}

def process_and_store_articles(page: int = 1, page_size: int = 10):
    """
    Ingest articles from all RSS feeds.
    Each article is embedded and committed individually so a single
    failure never rolls back the entire batch.
    """
    db = SessionLocal()
    seen_urls = set()
    saved_count = 0
    failed_count = 0

    start_index = (page - 1) * page_size
    end_index = start_index + page_size

    # Configure newspaper parser with a browser-like user agent to bypass WAF / Cloudflare blocks
    config = NewspaperConfig()
    config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    config.request_timeout = 15

    embedding_model = get_embedding_model()

    import re
    import uuid
    import time

    try:
        for category, feeds in RSS_FEEDS.items():
            for feed_url in feeds:
                print(f"Parsing feed (page={page}): {feed_url}")
                try:
                    parsed_feed = feedparser.parse(feed_url)
                    source_title = parsed_feed.feed.get("title", "Unknown Source")

                    for entry in parsed_feed.entries[start_index:end_index]:
                        url = entry.get("link")
                        if not url or not entry.get("title"):
                            continue

                        if url in seen_urls:
                            continue

                        existing = db.query(models.Article).filter(models.Article.url == url).first()
                        if existing:
                            seen_urls.add(url)
                            continue

                        seen_urls.add(url)

                        # Fallback image extraction from RSS feed
                        feed_image_url = None
                        if "media_content" in entry and entry.media_content:
                            feed_image_url = entry.media_content[0].get("url")
                        elif hasattr(entry, "links"):
                            for link in entry.links:
                                if link.get("type") and "image" in link.get("type"):
                                    feed_image_url = link.get("href")
                                    break

                        # Use newspaper3k to extract full content and image
                        content = ""
                        image_url = None
                        extracted_keywords = []
                        article_extractor = None
                        try:
                            article_extractor = NewspaperArticle(url, config=config)
                            article_extractor.download()

                            if article_extractor.download_state == 2:
                                article_extractor.parse()

                                try:
                                    article_extractor.nlp()
                                    extracted_keywords = article_extractor.keywords
                                except Exception as nlp_e:
                                    print(f"NLP extraction failed for {url}: {nlp_e}")

                                content = article_extractor.text
                                extracted_image_url = article_extractor.top_image or feed_image_url
                            else:
                                print(f"Failed to download article for {url}")
                                extracted_image_url = feed_image_url

                            if extracted_image_url:
                                try:
                                    import cloudinary.uploader
                                    upload_result = cloudinary.uploader.upload(
                                        extracted_image_url,
                                        public_id=f"news_{uuid.uuid4().hex[:12]}",
                                        fetch_format="auto",
                                        quality="auto"
                                    )
                                    image_url = upload_result.get("secure_url")
                                except Exception as cloudinary_e:
                                    print(f"Cloudinary upload failed for {extracted_image_url}: {cloudinary_e}")
                                    image_url = extracted_image_url
                        except Exception as e:
                            print(f"Failed to extract full content for {url}: {e}")

                        if not image_url:
                            print(f"Warning: Article saved without an image: {url}")

                        # Build description
                        description = ""
                        if article_extractor and hasattr(article_extractor, 'summary') and article_extractor.summary:
                            description = article_extractor.summary
                        else:
                            description_raw = html.unescape(entry.get("description", "") or "")
                            description = re.sub(r'<[^>]+>', '', description_raw).strip()
                            if description.endswith("[...]") or description.endswith("...") or description.endswith("…"):
                                if content and len(content) > 100:
                                    description = content[:200].rsplit(' ', 1)[0] + "..."

                        if not description and content:
                            description = content[:200].rsplit(' ', 1)[0] + "..."
                        elif not content:
                            content = description

                        # Parse date
                        published_at = datetime.utcnow()
                        if entry.get("published_parsed"):
                            try:
                                published_at = datetime(*entry.published_parsed[:6])
                            except:
                                pass

                        title = html.unescape(entry.get("title", ""))

                        base_slug = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip().lower()
                        base_slug = re.sub(r'[-\s]+', '-', base_slug)
                        unique_id = str(uuid.uuid4())[:8]
                        slug = f"{base_slug[:100]}-{unique_id}" if base_slug else unique_id

                        # --- Embed this article individually and save immediately ---
                        # This ensures a failure on one article never rolls back others.
                        embedding = None
                        try:
                            text_for_embedding = f"{title} {description}"
                            embedding = embedding_model.embed_one(text_for_embedding)
                            time.sleep(0.5)  # Light rate-limit guard between embed calls
                        except Exception as embed_e:
                            print(f"Embedding failed for {url}: {embed_e}")
                            # embedding stays None — article still saved, just won't cluster

                        new_article = models.Article(
                            title=title,
                            description=description,
                            content=content,
                            source_name=source_title,
                            author=entry.get("author"),
                            url=url,
                            image_url=image_url,
                            published_at=published_at,
                            category=category,
                            keywords=extracted_keywords,
                            is_verified=False,
                            slug=slug,
                            embedding=embedding
                        )

                        try:
                            db.add(new_article)
                            db.commit()
                            saved_count += 1
                            print(f"Saved article #{saved_count}: {title[:60]}")
                        except Exception as db_e:
                            db.rollback()
                            failed_count += 1
                            print(f"Failed to save article ({url}): {db_e}")

                except Exception as e:
                    print(f"Error parsing feed {feed_url}: {e}")

        print(f"Ingestion complete: {saved_count} saved, {failed_count} failed.")
    finally:
        db.close()

if __name__ == "__main__":
    process_and_store_articles()

