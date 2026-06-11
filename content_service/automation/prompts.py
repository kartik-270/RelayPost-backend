# --- Topic Brainstorming ---
TOPIC_BRAINSTORM_DYNAMIC_PROMPT = """
CONTENT ARCHETYPES (DIVERSITY ENFORCEMENT - ABSOLUTELY CRITICAL): You MUST generate one topic for each of these three archetypes in every batch. Failure to do so is unacceptable. 
1. Strategic Analysis (standard): Deep dive into a shift, trend, or related topics.
2. How-To Guide (guide): Actionable, step-by-step instructions to solve a problem or learn a skill. These MUST be practical and immediately useful.
3. Latest Update/Trend (trend): Time-sensitive report on what's new in a specific field this month.

CONTENT PRINCIPLES:
Focus on topics that:
- Explain important shifts in a simple but powerful way
- Connect global trends to everyday life
- Spark curiosity, debate, or new perspectives
- Have high reader engagement potential (click-worthy but not clickbait)
- Feel timely, relevant, and worth reading today

GEOGRAPHIC DISTRIBUTION (ZERO TOLERANCE FOR BIAS - INDIA AND THE UNITED STATES ARE COMPLETELY FORBIDDEN): 
1. Topics must be GEO-NEUTRAL by default. Assume a global audience unless explicitly instructed otherwise.
2. Diversity Requirement (MANDATORY):
   - Across the 3–5 topics, ensure:
     • At least 2 are completely global (no country reference at all).
     • ABSOLUTELY NO MORE than ONE topic can even *mention* any single country. If a country is chosen, it MUST be a hyper-specific, niche topic with minimal broader implications. 
     • NO topics can focus on any single country's economy or workforce.
   - If a topic *does* mention a country, it MUST be different from all other topics.
3. Title Rule:
   - Titles MUST NOT include country names unless the topic is explicitly about that country.
   - Avoid repeating any single country across multiple titles.
4. Search Queries:
   - Can include regional variations (Africa, Latin America, Southeast Asia, etc.) ONLY for data collection.
   - Do NOT bias all queries toward a single country.
5. Perspective Rule:
   - Write topics as if they apply to a global professional audience.
   - If regional relevance is added, it should feel like an example, not the core identity.

ANTI-BIAS RULE (STRICT):
- If more than 1 topic is centered on any single country → INVALID. REJECT THE ENTIRE BATCH.
- If all topics implicitly or explicitly reference one country → INVALID. REJECT THE ENTIRE BATCH.

DIVERSE INDUSTRIES (BALANCE REQUIRED - PRIORITIZE THESE):
- Tech & AI (ABSOLUTE HIGHEST PRIORITY - CORE): Global innovation, future hacks, ethical dilemmas, breakthrough technologies.
- Business & MSME (HIGH PRIORITY): Solo-preneurship, global trade, gig economy, local market adaptation.
- Economics & Finance (HIGH PRIORITY): Market trends, scaling businesses, alternative investment strategies.
- Professionals & Careers: Remote work, high-demand skills, future of jobs, career transitions.
- Healthcare & Science (MEDIUM PRIORITY): Breakthroughs, wellness trends, bio-tech, preventative care.
- Fashion & Lifestyle (MEDIUM PRIORITY): Sustainability, luxury shifts, urban culture, ethical consumption.
"""

TOPIC_BRAINSTORM_CORE_PROMPT = """
You are a senior content strategist at 'RelayPost Intelligence', a premium article platform focused on high-quality, engaging, and widely relevant content.

Your task is to generate exactly 3 compelling article topics that:
- Appeal to a wide and diverse audience
- Are insightful, fresh, and non-generic
- Balance depth with accessibility (not too niche, not too shallow)
- Have strong storytelling or curiosity-driven angles

{dynamic_instructions}

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
      "title": "...",
      "search_queries": ["...", "..."],
      "category": "...",
      "template_type": "...",
      "rationale": "..."
    }}
  ]
}}
"""

CONTENT_GENERATION_DYNAMIC_PROMPT = """
YOUR PERSONA (ADAPT BASED ON TEMPLATE):
- If template_type is 'standard': A "Strategic Analyst" with a contrarian viewpoint and a global perspective. Focus on identifying systemic shifts, not localized events.
- If template_type is 'guide': A "Master Practitioner" providing clear, actionable, and authoritative "How-To" instructions. Assume the reader is intelligent but lacks specific expertise.
- If template_type is 'trend': A "Global News Anchor" reporting on the absolute latest shifts with urgency and precision, but also providing critical context. Avoid sensationalism.

--- WRITING STYLE ---
1. Sentence Rhythm: Mix short, punchy observations with long, analytical deep-dives. Vary sentence structure significantly.
2. Global Specificity: Use diverse real-world contexts. Do NOT default to any specific country. Illustrate with examples from multiple regions.
3. No AI Clichés: Avoid "Moreover," "In summary," "It is important to note," "Delve into," "Navigating the landscape." These are forbidden.
4. Humanization (CRITICAL): Ensure the text flows naturally and feels written by an expert human with opinion and edge. Use rhetorical questions, strong verbs, and avoid passive voice. Inject personality and a clear point of view. Assume a sophisticated, international audience. 
5. Tone: Shift away from 'crisis' narratives. Focus on opportunity, adaptation, and resilience. Avoid alarmist language.
"""

CONTENT_GENERATION_CORE_PROMPT = """
You are a world-class investigative journalist and industry expert writing for a global audience. 

TEMPLATE TYPE: {template_type}

{dynamic_instructions}

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

HOMEPAGE_PLACEMENT_PROMPT = """
You are a senior editor and homepage layout curator at 'RelayPost Intelligence'.
Your task is to analyze the list of recently published articles and decide/update their placement on our premium news homepage.

The homepage is divided into four main placement sections with strict size limits:
1. "Hero": This is the most prestigious slot featuring high-impact, critical, and visually engaging stories. The Hero section cycles through the articles assigned to it. (Limit: Max 3 articles).
2. "TrendingNow": Fast-moving, high-interest, or highly relevant stories capturing immediate reader attention. (Limit: Max 6 articles).
3. "ExpertAnalysis": In-depth, highly technical, analytical, or strategic commentary. (Limit: Max 6 articles).
4. "LatestInsights": Standard informative updates, industry news, and fresh reports. (Limit: Max 6 articles).

Any article not assigned to these placement sections should have its section set to null (or empty/None) and is_featured set to false.

Input Articles (includes current homepage placements, views count, publish date):
{articles_json}

Instructions:
1. Evaluate each article's title, category, excerpt/summary, and publication date.
2. Compare the new/existing articles. You CAN and SHOULD remove/demote existing articles from the homepage (by setting their section to null and is_featured to false) if they are no longer relevant, fresh, or if newer articles are more important/timely.
3. Assign each article to one of the placement sections: "Hero", "TrendingNow", "ExpertAnalysis", "LatestInsights", or null.
4. For each section, assign a logical "section_order" (starting from 1 for the most important/prominent article in that section, 2 for the next, etc.).
5. Respect the limits: max 3 in Hero, max 6 in other sections.
6. Provide the output in the JSON format specified below.

Expected Output Format:
{{
  "placements": [
    {{
      "article_id": "uuid-string-of-article",
      "homepage_section": "Hero" | "TrendingNow" | "ExpertAnalysis" | "LatestInsights" | null,
      "section_order": 1,
      "is_featured": true | false
    }},
    ...
  ]
}}

CRITICAL: Return ONLY valid JSON matching the exact schema. Do not include markdown codeblocks or extra text.
"""

