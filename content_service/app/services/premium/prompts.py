"""
Centralized prompt templates for the AI Service.
"""

def get_summary_prompt(title: str, content_text: str, tier: str) -> str:
    """Returns the structured prompt for article summaries based on the tier."""
    if tier in ("plus", "pro"):
        return f"""You are a strict JSON generator. Summarize this article for an informed reader.

Article Title: {title}
Content:
{content_text[:4000]}

CRITICAL RULES:
1. Do NOT write any introduction, thoughts, checklists, self-evaluation, metadata, notes, or explanation.
2. Start your response directly with the JSON object. Do NOT include markdown code block wrappers (like ```json).
3. Output ONLY a valid JSON object matching this schema format:
- summary: A 2-3 sentence executive summary.
- takeaways: A list of 3 key takeaways.
- why_matters: Why this matters in one sentence.

Example Output:
{{
  "summary": "This is the summary.",
  "takeaways": [
    "Takeaway 1",
    "Takeaway 2",
    "Takeaway 3"
  ],
  "why_matters": "This matters because..."
}}

JSON:"""
    else:
        return f"""You are a strict JSON generator. Summarize this article for a general reader.

Article Title: {title}
Content:
{content_text[:2000]}

CRITICAL RULES:
1. Do NOT write any introduction, thoughts, checklists, self-evaluation, metadata, notes, or explanation.
2. Start your response directly with the JSON object. Do NOT include markdown code block wrappers (like ```json).
3. Output ONLY a valid JSON object matching this schema format:
- summary: A concise 2-3 sentence summary.

Example Output:
{{
  "summary": "This is the summary."
}}

JSON:"""


def get_ask_ai_prompt(title: str, content_text: str, question: str) -> str:
    """Returns the structured prompt for the Ask AI feature."""
    return f"""You are a strict JSON generator. Answer the following question about the article below.
Be accurate, cite the article text where possible, and be concise.

Article Title: {title}
Article Content: {content_text[:3000]}

Question: {question}

CRITICAL RULES:
1. If the question is outside the scope of the article, or if the article does not contain any information related to the question, you MUST set the JSON answer field exactly to "the question should be related to the article". Do not answer questions that are unrelated to the article content.
2. Do NOT write any introduction, thoughts, checklists, self-evaluation, metadata, notes, or explanation.
3. Start your response directly with the JSON object. Do NOT include markdown code block wrappers (like ```json).
4. Output ONLY a valid JSON object matching this schema format:
- answer: Your response string.

Example Output:
{{
  "answer": "This is the exact answer text and absolutely nothing else."
}}

JSON:"""


def get_cross_article_summary_prompt(articles_text: str, focus: str, num_articles: int) -> str:
    """Returns the prompt for synthesizing multiple articles."""
    return f"""You are a senior research analyst. Synthesize the following {num_articles} articles into a unified intelligence briefing.{focus}

{articles_text}

Provide:
1. A 3-5 sentence synthesis of the key theme across all articles
2. Areas of consensus and disagreement between sources
3. The most significant development or insight
4. What to watch next

Be analytical, not just descriptive. Cite article numbers where relevant."""


def get_research_report_prompt(topic: str, sources_text: str, num_sources: int) -> str:
    """Returns the prompt for generating a comprehensive research report."""
    return f"""You are a senior research analyst producing an executive intelligence report.

Topic: {topic}

Source Material ({num_sources} articles):
{sources_text}

Generate a comprehensive research report with these exact sections:

## Executive Summary
(3-4 sentences)

## Background & Context
(What led to this topic becoming significant)

## Key Developments
(Chronological timeline of the most important events, cite sources)

## Stakeholder Analysis
(Who are the key players and what are their positions)

## Expert Perspectives
(Different viewpoints and expert opinions represented in the sources)

## Implications & Impact
(Short-term and long-term implications)

## Key Questions & Unknowns
(What remains unclear or unresolved)

## Sources Referenced
(List the source titles used, numbered)

Be analytical, balanced, and grounded in the provided sources. Do not fabricate information."""


def get_weekly_report_prompt(topic_cluster: str, week_label: str, articles_text: str) -> str:
    """Returns the prompt for the weekly intelligence digest."""
    return f"""You are a senior intelligence analyst producing a weekly briefing.

Topic Area: {topic_cluster}
Period: {week_label}

Articles covered:
{articles_text}

Generate a "Weekly Intelligence Report" with:

## Week in Review
(2-3 sentence overview of the week's most significant developments)

## Top Stories
(The 3-5 most important stories and why they matter)

## Emerging Trends
(Patterns and signals emerging this week)

## What to Watch
(3 things to monitor in the coming week)

## Key Stat of the Week
(One compelling number or data point from the coverage)

Write for a busy professional who wants depth without noise. Be direct and insightful."""
