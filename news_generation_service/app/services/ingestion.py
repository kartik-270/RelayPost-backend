import os
import html
import socket
import signal
import contextlib
import gc
# Set a global timeout to prevent any networking library (feedparser, cloudinary, etc.) from hanging forever
socket.setdefaulttimeout(10)
import feedparser
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import models
from app.core.database import SessionLocal
from newspaper import Article as NewspaperArticle, Config as NewspaperConfig
import nltk

import ctypes

# Batch size for memory-safe processing.
BATCH_SIZE = 10

def trim_memory():
    gc.collect()
    try:
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except Exception:
        pass

@contextlib.contextmanager
def time_limit(seconds: int):
    """
    Context manager that raises TimeoutError if the block takes longer than
    `seconds`. Uses SIGALRM on POSIX (Linux/Mac). Safe to use only in the
    main thread of each subprocess (run_all.py runs as __main__).
    """
    def _handler(signum, frame):
        raise TimeoutError(f"Operation exceeded {seconds}s hard limit")

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

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
    Each article uses its own short-lived DB session (open→write→close immediately),
    so NO database connection is ever held open during external network calls
    (newspaper download, Cloudinary upload, Gemini embedding).
    """
    seen_urls = set()
    saved_count = 0
    failed_count = 0

    start_index = (page - 1) * page_size
    end_index = start_index + page_size

    # Configure newspaper parser with a browser-like user agent to bypass WAF / Cloudflare blocks.
    # Use a short timeout so slow sites fail fast and don't stall the pipeline.
    config = NewspaperConfig()
    config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    config.request_timeout = 6

    embedding_model = get_embedding_model()

    import re
    import uuid
    import time

    try:
        import random
        # 1. Fetch all feeds upfront
        feed_data_list = []
        for category, feeds in RSS_FEEDS.items():
            for feed_url in feeds:
                print(f"Fetching feed (page={page}): {feed_url}", flush=True)
                try:
                    parsed_feed = feedparser.parse(feed_url)
                    source_title = parsed_feed.feed.get("title", "Unknown Source")
                    entries = parsed_feed.entries[start_index:end_index]
                    if entries:
                        feed_data_list.append((category, feed_url, source_title, entries))
                except Exception as e:
                    print(f"Error fetching feed {feed_url}: {e}")

        # Shuffle feeds so starting category is random each time
        random.shuffle(feed_data_list)

        # 2. Interleave the entries (round-robin)
        interleaved_queue = []
        max_entries = max([len(t[3]) for t in feed_data_list]) if feed_data_list else 0
        for i in range(max_entries):
            for category, feed_url, source_title, entries in feed_data_list:
                if i < len(entries):
                    interleaved_queue.append((category, feed_url, source_title, entries[i]))

        # Clear feed_data_list and force garbage collection before processing
        del feed_data_list
        trim_memory()

        print(f"Successfully fetched {len(interleaved_queue)} articles across all feeds. Processing in round-robin order...", flush=True)

        # 3. Batch-deduplicate against the DB in a SINGLE query instead of
        #    one session per article (eliminates 210 round-trips to PostgreSQL).
        all_candidate_urls = [
            entry.get("link")
            for _, _, _, entry in interleaved_queue
            if entry.get("link")
        ]
        db_dedup = SessionLocal()
        try:
            existing_rows = db_dedup.execute(
                text("SELECT url FROM articles WHERE url = ANY(:urls)"),
                {"urls": all_candidate_urls}
            ).fetchall()
            existing_urls_in_db = {row[0] for row in existing_rows}
        except Exception as dedup_e:
            print(f"Batch dedup query failed: {dedup_e}")
            existing_urls_in_db = set()
        finally:
            db_dedup.close()

        seen_urls.update(existing_urls_in_db)

        # 4. Process articles in memory-safe batches of BATCH_SIZE.
        total = len(interleaved_queue)
        num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_num in range(num_batches):
            batch_start = batch_num * BATCH_SIZE
            batch_end   = batch_start + BATCH_SIZE
            batch       = interleaved_queue[batch_start:batch_end]

            print(
                f"\n── Batch {batch_num + 1}/{num_batches} "
                f"(articles {batch_start + 1}–{min(batch_end, total)} of {total}) ──",
                flush=True
            )

            for category, feed_url, source_title, entry in batch:

                try:
                    url = entry.get("link")
                    if not url or not entry.get("title"):
                        continue

                    if url in seen_urls:
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

                    # Use newspaper3k to extract full content and image.
                    content = ""
                    image_url = None
                    extracted_keywords = []
                    extracted_image_url = feed_image_url
                    article_summary = ""
                    article_extractor = None
                    try:
                        with time_limit(12):  # Hard 12-second ceiling for download+parse
                            article_extractor = NewspaperArticle(url, config=config)
                            article_extractor.download()

                            if article_extractor.download_state == 2:
                                article_extractor.parse()
                                extracted_keywords = []
                                content = article_extractor.text
                                extracted_image_url = article_extractor.top_image or feed_image_url
                                if hasattr(article_extractor, 'summary'):
                                    article_summary = article_extractor.summary
                                # ── Memory: strip large HTML/DOM blobs immediately
                                article_extractor.html = ""
                                article_extractor.clean_top_node = None
                                article_extractor.top_node = None
                            else:
                                print(f"Failed to download article for {url}")

                        if extracted_image_url:
                            try:
                                import cloudinary.uploader
                                with time_limit(10):  # Hard 10-second ceiling for Cloudinary upload
                                    upload_result = cloudinary.uploader.upload(
                                        extracted_image_url,
                                        public_id=f"news_{uuid.uuid4().hex[:12]}",
                                        fetch_format="auto",
                                        quality="auto"
                                    )
                                image_url = upload_result.get("secure_url")
                            except Exception as cloudinary_e:
                                image_url = extracted_image_url
                    except Exception as e:
                        print(f"Failed to extract full content for {url}: {e}")
                    finally:
                        del article_extractor
                        article_extractor = None

                    if not image_url:
                        print(f"Warning: Article saved without an image: {url}")

                    # Build description
                    description = article_summary
                    if not description:
                        description_raw = html.unescape(entry.get("description", "") or "")
                        description = re.sub(r'<[^>]+>', '', description_raw).strip()
                        if description.endswith("[...]") or description.endswith("...") or description.endswith("\u2026"):
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

                    # --- Embed this article individually ---
                    embedding = None
                    try:
                        text_for_embedding = f"{title} {description}"
                        embedding = embedding_model.embed_one(text_for_embedding)
                        time.sleep(0.3)  # Light rate-limit guard between embed calls
                    except Exception as embed_e:
                        print(f"Embedding failed for {url}: {embed_e}")

                    # Brief session to save the article to DB immediately
                    db_write = SessionLocal()
                    try:
                        from sqlalchemy.dialects.postgresql import insert as pg_insert
                        stmt = pg_insert(models.Article).values(
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
                        ).on_conflict_do_nothing(index_elements=['url'])

                        result = db_write.execute(stmt)
                        db_write.commit()
                        if result.rowcount:
                            saved_count += 1
                            print(f"Saved article #{saved_count}: {title[:60]}")
                        else:
                            print(f"Skipped duplicate (race condition prevented): {url}")
                    except Exception as db_e:
                        db_write.rollback()
                        failed_count += 1
                        print(f"Failed to save article ({url}): {db_e}")
                    finally:
                        db_write.close()

                except Exception as e:
                    print(f"Error processing article from feed {feed_url}: {e}")

            # ── End of batch: force GC and glibc malloc_trim to reclaim memory
            trim_memory()
            if batch_num < num_batches - 1:
                print(
                    f"Batch {batch_num + 1} complete "
                    f"({saved_count} saved so far). Memory trimmed. Starting next batch...",
                    flush=True
                )
                time.sleep(0.5)

        print(f"\nIngestion complete: {saved_count} saved, {failed_count} failed across batches.", flush=True)
    except Exception as outer_e:
        print(f"Unhandled error in ingestion pipeline: {outer_e}")


if __name__ == "__main__":
    process_and_store_articles()
