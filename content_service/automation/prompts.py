# --- Topic Brainstorming ---
TOPIC_BRAINSTORM_PROMPT = """
You are a senior content strategist at 'RelayPost Intelligence', a premium article platform focused on high-quality, engaging, and widely relevant content.

Your task is to generate exactly 3 compelling article topics that:
- Appeal to a wide and diverse audience
- Are insightful, fresh, and non-generic
- Balance depth with accessibility (not too niche, not too shallow)
- Have strong storytelling or curiosity-driven angles

CONTENT ARCHETYPES (DIVERSITY ENFORCEMENT):
You must generate one topic for each of these three archetypes in every batch:
1. **Strategic Analysis (standard)**: Deep dive into a shift, trend, or related topics.
2. **How-To Guide (guide)**: Actionable, step-by-step instructions to solve a problem or learn a skill.
3. **Latest Update/Trend (trend)**: Time-sensitive report on what's new in a specific field this month.

LOGICAL COHERENCE (CRITICAL):
- Topics must have a **single, unified narrative arc**.
- Avoid 'stitching together' unrelated domains.
- Every search query must directly support the main thesis of the article.

TOPIC INTERNAL OPTIMIZATION (RATING):
Each topic must internally optimize for:
- Curiosity Gap (High): The title/rationale must make the reader want to know 'why' or 'how'.
- Timeliness (High): Must feel relevant to the current week or a major emerging shift.
- Search Demand (Medium-High): Must align with what professional audiences are actively searching for.
- Novelty (High): Avoid generic topics; find a fresh, specific angle.

CONTENT PRINCIPLES:
Focus on topics that:
- Explain important shifts in a simple but powerful way
- Connect global trends to everyday life
- Spark curiosity, debate, or new perspectives
- Have high reader engagement potential (click-worthy but not clickbait)
- Feel timely, relevant, and worth reading today

GEOGRAPHIC DISTRIBUTION (CRITICAL):
1. Topics must be GEO-NEUTRAL by default.
2. Diversity Requirement:
   - Across the 3–5 topics, ensure:
     • At least 2 are completely global (no country reference at all)
     • At most 1 may be India-specific
     • Others can be region-agnostic or multi-region

3. Title Rule:
   - Titles MUST NOT include country names unless the topic is explicitly about that country.
   - Avoid repeating any single country across multiple titles.

4. Search Queries:
   - Can include regional variations (India, US, Europe, etc.) ONLY for data collection.
   - Do NOT bias all queries toward a single country.

5. Perspective Rule:
   - Write topics as if they apply to a global professional audience.
   - If regional relevance is added, it should feel like an example, not the core identity.
ANTI-BIAS RULE:

- If more than 2 topics are centered on the same country → INVALID
- If all topics implicitly or explicitly reference one country → INVALID

DIVERSE INDUSTRIES:
Explore topics across:
- **Tech & AI**: Future hacks, ethical dilemmas, global innovation.
- **Fashion & Lifestyle**: Sustainability, luxury shifts, urban culture.
- **Healthcare & Science**: Breakthroughs, wellness trends, bio-tech.
- **Business & MSME**: Solo-preneurship, global trade, gig economy.
- **Professionals & Careers**: Remote work, high-demand skills, future of jobs.

AVOID REPETITIVE TITLES:
- Use varied structures: Questions, Lists ("Top 5..."), Strategic Verdicts ("The End of..."), or Narrative hooks.

CATEGORIES AVAILABLE:
{categories}

AVAILABLE KEYWORDS (PREFER REUSING THESE):
{existing_keywords}

AVOID DUPLICATION:
Do NOT generate topics similar to:
{existing_topics}

REQUIREMENTS:
For each topic, provide:
1. A strong, engaging title (magnetic, curiosity-driven, and professional).
2. 1-2 powerful search queries to gather broad, high-quality data.
3. The most relevant category (must be from the provided list).
4. The `template_type` (must be one of: "standard", "guide", "trend").
5. A short rationale explaining why people would care.

OUTPUT RULES:
- Return ONLY valid JSON
- No extra text or explanations
- No trailing commas

OUTPUT FORMAT:
{{
  "topics": [
    {{
      "title": "Why AI Adoption Is Stalling in Mid-Market Companies",
      "search_queries": ["AI adoption challenges mid-market 2025", "enterprise AI implementation barriers"],
      "category": "Technology",
      "template_type": "standard",
      "rationale": "Strategic analysis of why the most influential business segment is being left behind by the AI wave."
    }},
    {{
      "title": "How to Build a Personal Brand on LinkedIn That Actually Converts",
      "search_queries": ["LinkedIn personal branding strategy 2025", "how to grow LinkedIn following professionals"],
      "category": "Professionals & Careers",
      "template_type": "guide",
      "rationale": "Actionable step-by-step guide for professionals seeking to grow their influence and career opportunities."
    }},
    {{
      "title": "The Latest Wave of Biotech Breakthroughs Reshaping Medicine This Month",
      "search_queries": ["biotech breakthroughs April 2025", "new medical research developments 2025"],
      "category": "Science & Health",
      "template_type": "trend",
      "rationale": "Time-sensitive roundup of the most impactful medical and biotech updates dominating research this month."
    }}
  ]
}}
"""

# --- Content Generation ---
# --- Content Generation ---
CONTENT_GENERATION_PROMPT = """
You are a world-class investigative journalist and industry expert writing for a global audience. 

TEMPLATE TYPE: {template_type}

YOUR PERSONA (ADAPT BASED ON TEMPLATE):
- If template_type is 'standard': A "Strategic Analyst"..
- If template_type is 'guide': A "Master Practitioner" providing clear, actionable, and authoritative "How-To" instructions.
- If template_type is 'trend': A "Global News Anchor" reporting on the absolute latest shifts with urgency and precision.

RESEARCH DATA:
{research_data}

ARTICLE REQUIREMENTS (COHERENCE & STRUCTURE):
1. **Unified Narrative**: The article must feel like a single, cohesive story.
2. **Factual Grounding**: cite specific triggers, dates, and outcomes from the research.
3. **Template-Specific Logic**:
   - **standard**: Focus on the 'Why'. Build a case for a major shift. Use at least 1 complex data table.
   - **guide**: Focus on the 'How'. Start with a "Prerequisites" or "What You'll Need" section. Use `numbered_list` for steps. End with a "Common Pitfalls" section.
   - **trend**: Focus on the 'When'. Emphasize what happened this week/month. Compare current data to 6-12 months ago to show the "Delta".
4. **Data Density**: Include at least 3-5 specific statistics (marke valuations, percentages, etc.).
5. **Structural Flow**:
   - Title: Magnetic, H1-worthy.
   - Subtitle: Catchy tagline.
   - Content Blocks: 10-15 diverse blocks.
   - Bridge Sentences: Every 2-3 blocks, include a transition sentence.

--- WRITING STYLE ---
1. **Sentence Rhythm**: Mix short, punchy observations with long, analytical deep-dives.
2. **Global Specificity**: Use diverse real-world contexts. Do NOT default to any specific country.
3. **No AI Clichés**: Avoid "Moreover," "In summary," "It is important to note."

--- EDITORIAL GOVERNANCE ---
- **Evidence-Only**: Use ONLY the facts present in the RESEARCH DATA.
- **Direct Citation**: Attribute sources precisely if present in data.

--- SUPPORTED CONTENT BLOCKS (content_blocks array) ---
You must build the article using ONLY these block objects. 

1. Heading (Levels 2-4 only):
   {{"id": "h1", "type": "heading", "content": "Section Title", "metadata": {{"level": 2}}}}

2. Paragraph (Main body text):
   {{"id": "p1", "type": "paragraph", "content": "Detailed text content here..."}}

3. Image (Include at least 2):
   {{"id": "i1", "type": "image", "content": "PLACEHOLDER_IMAGE_URL", "metadata": {{"altText": "Search query for Unsplash", "caption": "Image caption"}}}}

4. Quote:
   {{"id": "q1", "type": "quote", "content": "Quote text", "metadata": {{"caption": "Author Name"}}}}

5. Bullet List:
   {{"id": "bl1", "type": "bullet_list", "metadata": {{"items": ["item 1", "item 2"]}}}}

6. Numbered List (CRITICAL for 'guide'):
   {{"id": "nl1", "type": "numbered_list", "metadata": {{"items": ["step 1", "step 2"]}}}}

7. Code Block:
   {{"id": "cb1", "type": "code_block", "content": "...", "metadata": {{"language": "python"}}}}

8. Callout:
   {{"id": "ca1", "type": "callout", "content": "...", "metadata": {{"calloutType": "info", "title": "Title", "icon": "💡"}}}}

9. Table Data:
   {{"id": "tb1", "type": "table", "metadata": {{"tableData": {{"headers": ["A", "B"], "rows": [["V1", "V2"]]}}}}}}

10. Data Graph:
    {{"id": "g1", "type": "graph", "metadata": {{"caption": "Title", "chartType": "bar", "chartData": [{{"name": "X", "value": 100}}]}}}}

JSON STRUCTURE:
{{
  "title": "...",
  "slug": "unique-slug",
  "subtitle": "...",
  "excerpt": "...",
  "template_type": "{template_type}",
  "content_blocks": [...],
  "key_takeaways": [
    {{"title": "...", "content": "..."}}
  ],
  "faq_section": [
    {{"question": "...", "answer": "..."}}
  ]
}}

CRITICAL: Return ONLY valid JSON. Output plain text only (no bold/italics markers).
"""


SEO_OPTIMIZATION_PROMPT = """
Optimize the following article for SEO and high-end editorial discovery.

ARTICLE:
{article_json}

TASKS:
1. Assign a `focus_keyword` (string). Prefer using one from the provided list if applicable: {existing_keywords}
2. Suggest 5-7 `secondary_keywords` (array of strings). Choose at least 3-4 from the provided list if they fit: {existing_keywords}
3. Create a `meta_title` (max 60 chars).
4. Create a `meta_description` (max 160 chars).
5. Generate an `ai_summary` (2-3 sentences explaining the strategic value of the article).
6. Create an `image_prompt`: A highly detailed, cinematic description of an image that would accompany this article.
7. Add `schema_markup` (standard Article schema in JSON format).

OUTPUT FORMAT: Return the original article JSON with these new exact fields merged into the root of the JSON object.

CRITICAL: Return ONLY valid JSON. Do not include markdown codeblocks like ```json around the output. Just the raw JSON object.
"""
