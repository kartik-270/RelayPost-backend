import os
import html
import feedparser
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import models
from database import SessionLocal
from newspaper import Article as NewspaperArticle, Config as NewspaperConfig

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
    :param page: Which "page" of results to fetch (1-indexed). Each page fetches `page_size` entries per feed.
    :param page_size: Number of entries per feed per page (default 10).
    """
    db = SessionLocal()
    seen_urls = set()
    
    start_index = (page - 1) * page_size
    end_index = start_index + page_size

    # Configure newspaper parser with a browser-like user agent to bypass WAF / Cloudflare blocks
    config = NewspaperConfig()
    config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    config.request_timeout = 15
    
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
                        
                        # Use newspaper3k to extract full content and image
                        content = ""
                        image_url = None
                        try:
                            article_extractor = NewspaperArticle(url, config=config)
                            article_extractor.download()
                            article_extractor.parse()
                            content = article_extractor.text
                            extracted_image_url = article_extractor.top_image
                            
                            if extracted_image_url:
                                try:
                                    import cloudinary.uploader
                                    import uuid
                                    upload_result = cloudinary.uploader.upload(
                                        extracted_image_url,
                                        public_id=f"news_{uuid.uuid4().hex[:12]}",
                                        fetch_format="auto",
                                        quality="auto"
                                    )
                                    image_url = upload_result.get("secure_url")
                                except Exception as cloudinary_e:
                                    print(f"Cloudinary upload failed for {extracted_image_url}: {cloudinary_e}")
                                    image_url = None
                        except Exception as e:
                            print(f"Failed to extract full content for {url}: {e}")
                        
                        if not image_url:
                            print(f"Skipping article due to missing or failed image upload: {url}")
                            continue
                        
                        # Use feed description if extraction fails or as description
                        # Decode HTML entities in description too
                        description = html.unescape(entry.get("description", "") or "")
                        if not description and content:
                            description = content[:200] + "..."
                        elif not content:
                            content = description
                            
                        # Parse date
                        published_at = datetime.utcnow()
                        if entry.get("published_parsed"):
                            try:
                                published_at = datetime(*entry.published_parsed[:6])
                            except:
                                pass
                                
                        # Decode HTML entities in title (e.g. &#8217; -> ')
                        title = html.unescape(entry.get("title", ""))
                        
                        import re
                        import uuid
                        # Generate a URL-friendly slug
                        base_slug = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip().lower()
                        base_slug = re.sub(r'[-\s]+', '-', base_slug)
                        unique_id = str(uuid.uuid4())[:8]
                        slug = f"{base_slug[:100]}-{unique_id}" if base_slug else unique_id
                                
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
                            keywords=[],
                            is_verified=False,
                            slug=slug
                        )
                        
                        db.add(new_article)
                except Exception as e:
                    print(f"Error parsing feed {feed_url}: {e}")
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Database error during ingestion: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    process_and_store_articles()
