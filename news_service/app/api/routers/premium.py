"""
Premium routes for news_service.
Features:
  - /news/{id}/ai-summary  — AI summary of a news article (Free: 5/mo, Plus: 40/24h, Pro: unlimited)
  - /news/{id}/ask-ai      — Ask AI about a news article (Free: 5/mo, Plus: 25/24h, Pro: unlimited)
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import google.generativeai as genai

from app.core.auth_deps import TokenData, check_and_track_usage, track_usage

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL_NAME", "gemma-4-26b-a4b-it")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL)
else:
    _model = None


def _call_gemini(prompt: str, max_tokens: int = 512) -> str:
    if not _model:
        raise RuntimeError("Gemini API not configured")
    response = _model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens)
    )
    return response.text


router = APIRouter(prefix="/api/news/premium", tags=["News Premium"])


class AskAIRequest(BaseModel):
    question: str


@router.post("/{news_id}/ai-summary")
async def news_ai_summary(
    news_id: int,
    current_user: TokenData = Depends(check_and_track_usage("news_ai_summary")),
):
    """
    AI summary of a live news article fetched by ID.
    Pulls article from news_service DB or live feed.
    Free: 5/month | Plus: 40/24h | Pro: unlimited
    """
    # Import here to avoid circular imports
    from routers.news import get_news_article_by_id
    article = await get_news_article_by_id(news_id)
    if not article:
        raise HTTPException(status_code=404, detail="News article not found")

    title = article.get("title", "")
    description = article.get("description", "") or article.get("content", "")

    tier = current_user.tier
    if tier in ("plus", "pro"):
        prompt = f"""You are a news analyst. Summarize this news article for an informed reader.

Title: {title}
Content: {description[:3000]}

Provide:
1. A 2-3 sentence executive summary
2. 3-4 key facts as bullet points
3. Why this matters in one sentence"""
    else:
        prompt = f"""Summarize this news article in 2 sentences.
Title: {title}
Content: {description[:1500]}
Summary:"""

    try:
        summary = _call_gemini(prompt, max_tokens=600 if tier == "free" else 1000)
        track_usage(current_user.user_id, "news_ai_summary", tier)
        return {
            "news_id": news_id,
            "title": title,
            "summary": summary,
            "tier": tier,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")


@router.post("/{news_id}/ask-ai")
async def news_ask_ai(
    news_id: int,
    payload: AskAIRequest,
    current_user: TokenData = Depends(check_and_track_usage("ask_ai")),
):
    """
    Ask AI a question about a news article.
    Free: 5/month | Plus: 25/24h | Pro: unlimited
    """
    from routers.news import get_news_article_by_id
    article = await get_news_article_by_id(news_id)
    if not article:
        raise HTTPException(status_code=404, detail="News article not found")

    title = article.get("title", "")
    description = article.get("description", "") or ""

    prompt = f"""Answer the question below about this news article. Be concise and accurate.

Title: {title}
Article: {description[:2000]}

Question: {payload.question}
Answer:"""

    try:
        answer = _call_gemini(prompt, max_tokens=500)
        track_usage(current_user.user_id, "ask_ai", current_user.tier)
        return {
            "news_id": news_id,
            "question": payload.question,
            "answer": answer,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")
