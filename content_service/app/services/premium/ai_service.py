"""
Premium AI service for content_service.
Handles: article summary, Ask AI (single article), cross-article summary (Pro),
         research mode (Pro), weekly intelligence report (Plus+).

All functions are gated via auth_deps.check_and_track_usage before invocation.
Model: gemma-4-26b-a4b-it (configurable via GEMINI_MODEL env var).
"""
import os
import json
from typing import Optional, List
import google.generativeai as genai
from .prompts import (
    get_summary_prompt,
    get_ask_ai_prompt,
    get_cross_article_summary_prompt,
    get_research_report_prompt,
    get_weekly_report_prompt
)

GEMINI_API_KEY = os.environ.get("PREMIUM_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL_NAME", "gemma-4-26b-a4b-it")

if GEMINI_API_KEY:
    GEMINI_API_KEY = GEMINI_API_KEY.split("#")[0].strip()
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL)
else:
    _model = None



import re

def extract_json(text: str) -> dict:
    """Helper to parse JSON even if surrounded by markdown code blocks or text."""
    try:
        return json.loads(text.strip())
    except Exception:
        pass

    # Try to find a markdown json block first
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Brace counting to find all complete JSON object candidates
    brace_count = 0
    start_idx = -1
    json_candidates = []
    
    for i, char in enumerate(text):
        if char == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx != -1:
                json_candidates.append(text[start_idx:i+1])
                start_idx = -1
                
    # Parse the candidates from last to first (since the final answer is usually at the end)
    for candidate in reversed(json_candidates):
        try:
            return json.loads(candidate)
        except Exception:
            pass

    raise ValueError("No valid JSON found in response")


def _call_gemini(prompt: str, max_tokens: int = 1024, response_mime_type: Optional[str] = None) -> str:
    if not _model:
        raise RuntimeError("Gemini API not configured")
    
    config_args = {"max_output_tokens": max_tokens}
    if response_mime_type:
        config_args["response_mime_type"] = response_mime_type

    # Try 1: Call with requested config
    try:
        response = _model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(**config_args)
        )
        text = response.text if response.text else None
        if not text:
            raise ValueError("Empty response from model")
        return text
    except Exception as e:
        print(f"[GEMINI ERROR] Attempt 1 failed with model {GEMINI_MODEL}: {e}.")
        
        # Try 2: Retry without JSON mode (plain text)
        if response_mime_type == "application/json":
            print(f"[GEMINI RETRY] Retrying model {GEMINI_MODEL} without response_mime_type...")
            try:
                plain_config = {"max_output_tokens": max_tokens}
                response = _model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(**plain_config)
                )
                text = response.text if response.text else None
                if not text:
                    raise ValueError("Empty response from model on retry")
                print(f"[GEMINI RETRY SUCCESS] Model {GEMINI_MODEL} plain-text response length: {len(text)}")
                return text
            except Exception as retry_err:
                print(f"[GEMINI RETRY FAIL] Retry on model {GEMINI_MODEL} also failed: {retry_err}")

        # Try 3: Fallback to gemini-1.5-flash
        print("Falling back to gemini-3.1-flash-lite...")
        try:
            fallback_model = genai.GenerativeModel("gemini-3.1-flash-lite")
            response = fallback_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(**config_args)
            )
            text = response.text if response.text else None
            if not text:
                raise ValueError("Empty response from fallback model")
            print(f"[GEMINI FALLBACK SUCCESS] Fallback model gemini-1.5-flash response length: {len(text)}")
            return text
        except Exception as fallback_err:
            print(f"[GEMINI FALLBACK FAIL] Fallback also failed: {fallback_err}")
            if response_mime_type == "application/json":
                return json.dumps({
                    "error": str(fallback_err),
                    "answer": "The AI service is temporarily offline. Please try again shortly.",
                    "summary": "AI summary temporarily unavailable.",
                    "takeaways": ["Service temporarily offline. Please try again later."],
                    "why_matters": "AI service offline."
                })
            raise RuntimeError(f"Gemini call failed: {e}. Fallback failed: {fallback_err}")


def get_structured_response(prompt: str, expected_key: str, fallback_message: str, max_tokens: int = 1024) -> dict:
    """
    Generic handler for generating and parsing structured JSON responses from the AI.
    """
    try:
        res_text = _call_gemini(prompt, max_tokens=max_tokens, response_mime_type="application/json")
        print(f"[STRUCTURED_AI DEBUG] Raw response text:\n{res_text}")
        data = extract_json(res_text)
        print(f"[STRUCTURED_AI DEBUG] Parsed JSON: {data}")
        
        # If fallback error JSON was returned
        if "error" in data and expected_key in data:
            return data

        value = data.get(expected_key, "")
        # Fallback if model returned placeholder or empty string
        if not value or str(value).strip() in ("", "...", "Your detailed, cited response to the user's question."):
            cleaned_text = res_text.split("Schema:")[0].split("schema:")[0].strip()
            data[expected_key] = cleaned_text if cleaned_text else res_text

        return data
    except Exception as e:
        print(f"[STRUCTURED_AI ERROR] Error processing structured response: {e}")
        # Return raw text as best-effort fallback wrapped in dict
        cleaned_text = res_text.split("Schema:")[0].split("schema:")[0].strip() if 'res_text' in locals() else ""
        return {expected_key: cleaned_text if cleaned_text else fallback_message}


# ── Article AI Summary ────────────────────────────────────────────────────────

def generate_article_summary(
    title: str,
    content_text: str,
    tier: str = "free",
) -> str:
    """
    Generate a concise AI summary for a single article.
    Free: brief (3 sentence max), Plus/Pro: structured with key points.
    """
    prompt = get_summary_prompt(title, content_text, tier)
    data = get_structured_response(
        prompt=prompt, 
        expected_key="summary", 
        fallback_message="Failed to generate AI summary. Please try again shortly."
    )
    
    if "error" in data and "summary" in data:
        return data["summary"]

    summary = data.get("summary", "")

    if tier in ("plus", "pro") and "takeaways" in data:
        takeaways = "\n".join(f"• {t}" for t in data.get("takeaways", []))
        why_matters = data.get("why_matters", "")
        formatted_summary = f"{summary}\n\nKey Takeaways:\n{takeaways}\n\nWhy It Matters:\n{why_matters}"
        return formatted_summary.strip()
    
    return summary


# ── Ask AI (single article Q&A) ───────────────────────────────────────────────

def ask_ai_about_article(
    title: str,
    content_text: str,
    question: str,
    tier: str = "free",
) -> str:
    """
    Answer a user's question about a specific article.
    """
    prompt = get_ask_ai_prompt(title, content_text, question)
    data = get_structured_response(
        prompt=prompt, 
        expected_key="answer", 
        fallback_message="I'm sorry, the AI service is temporarily experiencing issues. Please try again shortly."
    )
    return data.get("answer", "")


# ── Cross-Article Summary (Pro only) ─────────────────────────────────────────

def cross_article_summary(
    articles: List[dict],
    synthesis_query: Optional[str] = None,
) -> str:
    """
    Synthesize multiple articles into a unified insight.
    Pro tier only.
    """
    articles_text = "\n\n".join(
        f"Article {i+1}: {a.get('title', '')}\n{a.get('content_snippet', a.get('excerpt', ''))[:500]}"
        for i, a in enumerate(articles[:20])
    )
    focus = f"\nFocus specifically on: {synthesis_query}" if synthesis_query else ""
    prompt = get_cross_article_summary_prompt(articles_text, focus, len(articles))
    return _call_gemini(prompt, max_tokens=1500)


# ── Research Mode (Pro only) ──────────────────────────────────────────────────

def generate_research_report(
    topic: str,
    background_articles: List[dict],
    news_articles: Optional[List[dict]] = None,
) -> dict:
    """
    Generate a structured multi-section research report on a topic.
    Combines content articles + news articles for maximum context.
    Pro tier only — soft cap of 30/month.
    """
    all_sources = background_articles + (news_articles or [])
    sources_text = "\n\n".join(
        f"[{i+1}] {a.get('title', '')} ({a.get('source', 'RelayPost')}, {a.get('published_at', 'recent')})\n{a.get('content_snippet', '')[:400]}"
        for i, a in enumerate(all_sources[:25])
    )
    prompt = get_research_report_prompt(topic, sources_text, len(all_sources))
    report_text = _call_gemini(prompt, max_tokens=3000)

    return {
        "topic": topic,
        "report": report_text,
        "source_count": len(all_sources),
    }


# ── Weekly Intelligence Report (Plus+) ───────────────────────────────────────

def generate_weekly_report(
    topic_cluster: str,
    articles: List[dict],
    week_label: str = "This Week",
) -> dict:
    """
    Generate a weekly intelligence digest for a topic cluster.
    Cached per topic_cluster per week — not per-user computation.
    Plus and Pro tiers.
    """
    articles_text = "\n\n".join(
        f"• {a.get('title', '')} — {a.get('excerpt', '')[:200]}"
        for a in articles[:15]
    )
    prompt = get_weekly_report_prompt(topic_cluster, week_label, articles_text)
    report_text = _call_gemini(prompt, max_tokens=2000)

    return {
        "topic_cluster": topic_cluster,
        "week_label": week_label,
        "report": report_text,
        "article_count": len(articles),
    }
