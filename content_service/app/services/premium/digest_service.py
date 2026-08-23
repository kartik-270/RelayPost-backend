"""
digest_service.py — Weekly Digest Generation

Handles:
  - Collecting top articles from DB for the week (with fallback to all-time best)
  - Collecting top news from news_service HTTP API
  - AI generation via Gemini (structured sections)
  - Persisting WeeklyDigest record (idempotent)
  - Re-ranking for user personalisation (Plus/Pro)

Tier gating: Only Plus and Pro users receive the digest in-app.
All users receive the email but can opt out.
"""

import os
import uuid
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models.models import Article, ArticleStatus, WeeklyDigest, DigestOptOut
from app.services.premium.ai_service import _call_gemini

NEWS_SERVICE_URL = os.environ.get("NEWS_SERVICE_URL", "http://news_service:8002")
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth_service:8000")
FRONTEND_URL     = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")[0].strip()
INTERNAL_SECRET  = os.environ.get("INTERNAL_SECRET", "")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _current_week_label() -> str:
    """Returns ISO week label like '2026-W28'."""
    now = datetime.now(timezone.utc)
    return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"


def _week_bounds() -> tuple[datetime, datetime]:
    """Returns (week_start, week_end) for the current ISO week (Mon–Sun)."""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end   = week_start + timedelta(days=7)
    return week_start, week_end


# ─────────────────────────────────────────────────────────────────────────────
# Data collection
# ─────────────────────────────────────────────────────────────────────────────

def collect_top_articles(db: Session, week_start: datetime, week_end: datetime, limit: int = 8) -> list[dict]:
    """
    Fetch top articles for this week, ranked by views_count DESC.
    Falls back to top all-time published articles if fewer than 4 exist this week.
    """
    # This week's articles
    weekly = (
        db.query(Article)
        .filter(
            Article.status == ArticleStatus.PUBLISHED,
            Article.published_at >= week_start,
            Article.published_at < week_end,
            Article.deleted_at == None,
        )
        .order_by(desc(Article.views_count))
        .limit(limit)
        .all()
    )

    # Fall back to all-time if not enough
    if len(weekly) < 4:
        all_time = (
            db.query(Article)
            .filter(
                Article.status == ArticleStatus.PUBLISHED,
                Article.deleted_at == None,
            )
            .order_by(desc(Article.views_count))
            .limit(limit - len(weekly))
            .all()
        )
        # Merge, deduplicate
        seen = {a.id for a in weekly}
        for a in all_time:
            if a.id not in seen:
                weekly.append(a)
                seen.add(a.id)

    result = []
    for a in weekly[:limit]:
        result.append({
            "id":          str(a.id),
            "title":       a.title,
            "slug":        a.slug,
            "category":    a.category_name or "General",
            "excerpt":     (a.excerpt or a.ai_summary or "")[:300],
            "hero_image":  a.hero_image or "",
            "views_count": a.views_count or 0,
        })
    return result


async def collect_top_news(limit: int = 8) -> list[dict]:
    """Fetch live top news from news_service and pick top stories per category."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{NEWS_SERVICE_URL}/api/news/live?limit=40")
            if resp.status_code != 200:
                return []
            data = resp.json()
            articles = data.get("articles", data) if isinstance(data, dict) else data
    except Exception as e:
        print(f"[DIGEST] Failed to fetch news: {e}")
        return []

    # Deduplicate by category — pick top 1-2 per category
    seen_cats: dict[str, int] = {}
    result = []
    for item in articles:
        cat = (item.get("category") or "General").strip()
        if seen_cats.get(cat, 0) >= 2:
            continue
        seen_cats[cat] = seen_cats.get(cat, 0) + 1
        result.append({
            "id":           item.get("id"),
            "title":        item.get("title", ""),
            "slug":         item.get("slug", ""),
            "source":       item.get("source", ""),
            "category":     cat,
            "image_url":    item.get("image_url") or item.get("hero_image") or "",
            "published_at": item.get("published_at", ""),
        })
        if len(result) >= limit:
            break
    return result


# ─────────────────────────────────────────────────────────────────────────────
# AI Generation
# ─────────────────────────────────────────────────────────────────────────────

def _build_digest_prompt(top_articles: list[dict], top_news: list[dict], week_label: str) -> str:
    articles_text = "\n".join(
        f"• [{a['category']}] {a['title']} — {a['excerpt'][:150]}"
        for a in top_articles
    ) or "No articles available."

    news_text = "\n".join(
        f"• [{n['category']}] {n['title']} (via {n['source']})"
        for n in top_news
    ) or "No news available."

    return f"""You are the Chief Editorial Intelligence Officer of RelayPost, a premium news intelligence platform.
Produce the weekly editorial digest for {week_label} as a JSON object.

## ARTICLES PUBLISHED THIS WEEK
{articles_text}

## TOP NEWS HEADLINES THIS WEEK
{news_text}

Write a high-quality, editorial intelligence briefing. Return ONLY valid JSON (no markdown, no extra text):
{{
  "executive_summary": "3-4 sentences. A compelling, direct overview of the week's most significant developments across politics, business, technology and society. Written for a busy executive.",
  "major_themes": "3-5 bullet points (use '• ' prefix). The dominant narratives and themes across all coverage this week, with brief analysis of why they matter.",
  "emerging_signals": "2-3 bullet points (use '• ' prefix). Weak signals and early trends that may become significant in the coming weeks. Be forward-looking.",
  "editors_note": "1-2 sentences. A personal, authoritative editorial voice. An insight or provocative observation that ties the week together.",
  "stat_of_week": "One striking number or data point from the week's coverage with brief context (e.g. '47% — the jump in EV adoption in Q2, signalling a tipping point in consumer preference').",
  "what_to_watch": [
    {{"title": "Short label", "description": "One sentence on what to watch next week and why."}},
    {{"title": "Short label", "description": "One sentence."}},
    {{"title": "Short label", "description": "One sentence."}}
  ]
}}"""


def generate_digest_ai(top_articles: list[dict], top_news: list[dict], week_label: str) -> dict:
    """Call Gemini and parse the structured digest sections."""
    prompt = _build_digest_prompt(top_articles, top_news, week_label)
    try:
        raw = _call_gemini(prompt, max_tokens=2000, response_mime_type="application/json")
        import json, re
        # Strip markdown code blocks if present
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        return data
    except Exception as e:
        print(f"[DIGEST AI] JSON parse failed, retrying plain: {e}")
        try:
            raw = _call_gemini(prompt, max_tokens=2000)
            import json, re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e2:
            print(f"[DIGEST AI] Both attempts failed: {e2}")
            raise RuntimeError(f"AI digest generation failed: {e2}")
    
    raise RuntimeError("AI digest generation failed unexpectedly.")


# ─────────────────────────────────────────────────────────────────────────────
# Personalization
# ─────────────────────────────────────────────────────────────────────────────

def personalize_digest(digest: "WeeklyDigest", user_top_categories: list[str]) -> dict:
    """
    Re-rank top_articles for a specific user based on their preferred categories.
    Returns a dict suitable for the API response with reordered articles.
    """
    if not user_top_categories:
        return _digest_to_dict(digest)

    articles = list(digest.top_articles)

    def score(a: dict) -> int:
        cat = (a.get("category") or "").lower()
        for rank, pref in enumerate(user_top_categories):
            if pref.lower() in cat or cat in pref.lower():
                return len(user_top_categories) - rank
        return 0

    articles.sort(key=score, reverse=True)
    result = _digest_to_dict(digest)
    result["top_articles"] = articles
    return result


def _digest_to_dict(digest: "WeeklyDigest") -> dict:
    return {
        "id":                str(digest.id),
        "week_label":        digest.week_label,
        "week_start":        digest.week_start.isoformat() if digest.week_start else None,
        "week_end":          digest.week_end.isoformat() if digest.week_end else None,
        "published_at":      digest.published_at.isoformat() if digest.published_at else None,
        "executive_summary": digest.executive_summary,
        "major_themes":      digest.major_themes,
        "emerging_signals":  digest.emerging_signals,
        "editors_note":      digest.editors_note,
        "stat_of_week":      digest.stat_of_week,
        "top_articles":      digest.top_articles or [],
        "top_news":          digest.top_news or [],
        "what_to_watch":     digest.what_to_watch or [],
        "article_count":     digest.article_count,
        "news_count":        digest.news_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def publish_weekly_digest(db: Session) -> Optional["WeeklyDigest"]:
    """
    Full pipeline — idempotent.
    Returns the digest object (existing or newly created).
    """
    week_label = _current_week_label()
    week_start, week_end = _week_bounds()

    # Idempotency — skip if already published this week
    existing = db.query(WeeklyDigest).filter(WeeklyDigest.week_label == week_label).first()
    if existing and existing.generation_status == "done":
        print(f"[DIGEST] Already published for {week_label} — skipping.")
        return existing

    # Mark as generating (in case another instance tries to run concurrently)
    if existing:
        existing.generation_status = "generating"
        db.commit()
        digest = existing
    else:
        digest = WeeklyDigest(
            week_label=week_label,
            week_start=week_start,
            week_end=week_end,
            generation_status="generating",
        )
        db.add(digest)
        db.commit()
        db.refresh(digest)

    try:
        print(f"[DIGEST] Collecting data for {week_label}...")
        top_articles = collect_top_articles(db, week_start, week_end)
        top_news     = await collect_top_news()

        print(f"[DIGEST] Generating AI sections ({len(top_articles)} articles, {len(top_news)} news)...")
        ai_data = generate_digest_ai(top_articles, top_news, week_label)

        # Persist
        digest.top_articles       = top_articles
        digest.top_news           = top_news
        digest.article_count      = len(top_articles)
        digest.news_count         = len(top_news)
        digest.executive_summary  = ai_data.get("executive_summary", "")
        digest.major_themes       = ai_data.get("major_themes", "")
        digest.emerging_signals   = ai_data.get("emerging_signals", "")
        digest.editors_note       = ai_data.get("editors_note", "")
        digest.stat_of_week       = ai_data.get("stat_of_week", "")
        digest.what_to_watch      = ai_data.get("what_to_watch", [])
        digest.generation_status  = "done"
        db.commit()
        db.refresh(digest)
        print(f"[DIGEST] Successfully published digest for {week_label}.")
        return digest

    except Exception as e:
        digest.generation_status = "failed"
        db.commit()
        print(f"[DIGEST] FAILED for {week_label}: {e}")
        raise
