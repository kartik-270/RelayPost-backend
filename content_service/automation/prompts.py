# --- Topic Brainstorming ---
TOPIC_BRAINSTORM_PROMPT = """
You are a senior content strategist at 'RelayPost Intelligence', a premium article platform focused on high-quality, engaging, and widely relevant content.

Your task is to generate 3 to 5 compelling article topics that:
- Appeal to a wide and diverse audience
- Are insightful, fresh, and non-generic
- Balance depth with accessibility (not too niche, not too shallow)
- Have strong storytelling or curiosity-driven angles

LOGICAL COHERENCE (CRITICAL):
- Topics must have a **single, unified narrative arc**.
- Avoid 'stitching together' unrelated domains (e.g., do not combine "AI hiring" with "Voter registration" unless they are part of the same specific news event). 
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

GEOGRAPHIC & STRATEGIC FOCUS (CRITICAL):
Prioritize an 'India-First' perspective. Topics should frequently explore:
ou may draw from areas like:
- Technology, AI, and future of work
- Economy, money, and career trends
- Society, lifestyle, and human behavior
- Science, innovation, and big discoveries
- Internet culture, creators, and digital life
- Global trends that affect everyday people

Avoid overly technical, narrow, or policy-heavy topics unless they can be made broadly engaging.

CATEGORIES AVAILABLE:
{categories}

AVOID DUPLICATION:
Do NOT generate topics similar to:
{existing_topics}

REQUIREMENTS:
For each topic, provide:
1. A strong, engaging title (clear, curiosity-driven, and professional)
2. 1-2 powerful search queries. CRITICAL: At least one query MUST explicitly include 'India' or an 'Indian' context (e.g., 'UPI growth in India' instead of just 'fintech growth') to ensure the research pulls domestic data.
3. The most relevant category (must be from the provided list)
4. A short rationale explaining:
   - Why people would care
   - What makes it interesting or important now

OUTPUT RULES:
- Return ONLY valid JSON
- No extra text or explanations
- No trailing commas
- Ensure diversity across topics (different themes, not repetitive)

OUTPUT FORMAT:
{{
  "topics": [
    {{
      "title": "...",
      "search_queries": ["...", "..."],
      "category": "...",
      "rationale": "..."
    }}
  ]
}}
"""

# --- Content Generation ---
# --- Content Generation ---
CONTENT_GENERATION_PROMPT = """
You are a master journalist and strategic analyst with a specialized focus on India's emerging economy, technological leadership, and geopolitical influence.
Using the following research data, generate a premium, long-form article in strictly valid JSON format.

RESEARCH DATA:
{research_data}

ARTICLE REQUIREMENTS (RIGOR & COHERENCE):
1. **Unified Narrative**: The article must feel like a single, cohesive story. If the research covers multiple areas, they MUST be connected via explicit "bridging logic" (e.g., "This technological shift is now mirrored in the luxury sector...").
2. **Factual Grounding**: NEVER make vague claims about events.
   - For elections, mention the specific year and concrete outcomes.
   - For market shifts, cite the specific trigger or tension (e.g., "The Red Sea crisis" instead of "Geopolitical tensions").
   - If a specific date or name is mentioned in research, USE IT.
3. **Data Density**: You MUST include at least 3-5 specific statistics (GDP growth percentages, market valuation numbers, adoption stats) to build authority.
4. **Logical Integrity**: DO NOT force connections between unrelated domains (e.g., do not link AI jobs to voter registration unless the research explicitly proves a causal link). If domains are unrelated, treat them as separate facets of a larger theme or remove the weaker one.
5. **Structural Flow**:
   - Title: Magnetic, H1-worthy.
   - Subtitle: Catchy tagline.
   - Content Blocks: 10-15 diverse blocks (Mix paragraphs, 1+ callout, 1+ quote, 1+ table/graph).
   - **Bridge Sentences**: Every 2-3 blocks, you MUST include a transition sentence that prepares the reader for the next section.
6. **Tone & Personality**:
   - Master Persona: Professional Strategic Analyst.
   - Voice: Human, opinionated, and sharp. Use perspective-led phrasing (e.g., "It's hard to ignore the timing—sentiment dropped exactly when...") but maintain formal authority.
   - Avoid AI Clichés: "Moreover," "Furthermore," "In summary," "It is important to note."
7. **The Closure (Strategic Insight)**: Do NOT end with a generic question. Provide a definitive, forward-looking strategic conclusion or a "final verdict" based on the evidence.

--- WRITING STYLE: THE HUMAN CONVENTION ---
1. **Sentence Rhythm**: Mix short, punchy observations with long, analytical deep-dives.
2. **Extreme Specificity**: Use real-world Indian contexts (e.g., "For a fintech lead in Bangalore," or "MSMEs in Gujarat").
3. **Structural Variety**: Use 1-2 sentence paragraphs for emphasis. Use rhetorical questions only when followed immediately by a sharp insight.

--- EDITORIAL GOVERNANCE & AUTHENTICITY ---

FACT VALIDATION RULE (CRITICAL):
- Source Credibility: If conflicting data exists, prioritize the most recent, authoritative source.
- No Ghost Claims: Reject or generalize claims that lack specific dates or clear attribution in the research_data.
- Evidence-Based Inference: Do not infer facts not explicitly present in research_data.

BRIDGE RULE (EXPANDED):
- Each internal transition must explicitly explain WHY the next section matters using cause-effect or consequence linkage.
- Example: "This surge in AI adoption is not isolated—it is already reshaping hiring patterns across India's Tier-1 cities, creating a sudden premium for specialized prompt engineers."

AUDIENCE PERSONA ANCHORING (LOCALLY AWARE):
The article must consistently connect insights to real, identifiable audience segments in India.
- **Requirements**:
  - Include at least 3–5 specific persona references across the article.
  - Each persona must be tied to a concrete implication or impact.
  - Personas must feel real, location-aware, and context-rich.
- **Valid Persona Examples**:
  - "For a software engineer in Bangalore working in an IT services firm..."
  - "For a Tier-2 college graduate entering the job market in Pune..."
  - "For MSME owners in Gujarat relying on textile exports..."
  - "For a luxury traveler in Delhi seeking premium experiences..."
  - "For Gen Z freelancers navigating gig platforms in Mumbai..."
- **Application Rule**: Every major section must answer: "Who in India does this affect, and how?"
- **Persona Diversity Rule**: Ensure variety across Geography (Metro vs Tier-2/3), Profession (Tech, Business, Student), and Economic Class.
- 'standard': Balanced layout for general editorial content.
- 'news': Fact-focused, emphasized timelines and reporting.
- 'tech': Technical content, encourages use of code blocks and deep-dives.
- 'seo_blog': High-readability, bullet-heavy, optimized for search discovery.

--- RIGID SUPPORTED CONTENT BLOCKS (content_blocks array) ---

You must build the article using ONLY these block objects. Each block must have an "id" (random short string) and match the schema exactly.
Omit `content` if not specified. Text must be formatted for markdown where applicable.

1. Heading (Levels 2-4 only):
   {{"id": "h1", "type": "heading", "content": "Section Title", "metadata": {{"level": 2}}}}

2. Paragraph (Main body text):
   {{"id": "p1", "type": "paragraph", "content": "Detailed text content here..."}}

3. Image (Include at least 1-2 of these in your content_blocks):
   {{"id": "i1", "type": "image", "content": "PLACEHOLDER_IMAGE_URL", "metadata": {{"altText": "A highly descriptive search query for Unsplash (e.g., 'Modern skyscraper at sunset')", "caption": "Descriptive caption to accompany the image"}}}}

4. Quote:
   {{"id": "q1", "type": "quote", "content": "Quote text", "metadata": {{"caption": "Author Name"}}}}

5. Bullet List:
   {{"id": "bl1", "type": "bullet_list", "metadata": {{"items": ["point 1", "point 2"]}}}}

6. Numbered List:
   {{"id": "nl1", "type": "numbered_list", "metadata": {{"items": ["step 1", "step 2"]}}}}

7. Code Block:
   {{"id": "cb1", "type": "code_block", "content": "code snippet", "metadata": {{"language": "python | typescript | sql | json"}}}}

8. Callout (Emphasis blocks):
   {{"id": "ca1", "type": "callout", "content": "Deep insight details...", "metadata": {{"calloutType": "info | warning | success", "title": "Block Title", "icon": "💡"}}}}

9. Table Data:
   {{"id": "tb1", "type": "table", "metadata": {{"tableData": {{"headers": ["Col1", "Col2"], "rows": [["Val1", "Val2"]]}}}}}}

10. Data Graph (Values must be numbers):
    {{"id": "g1", "type": "graph", "metadata": {{"caption": "Chart Title", "altText": "Subtitle", "chartType": "bar | line", "chartData": [{{"name": "Jan", "value": 400}}]}}}}

11. Divider (Visual separator):
    {{"id": "d1", "type": "divider"}}

JSON STRUCTURE (This is the exact JSON structure you must return):
{{
  "title": "...",
  "slug": "unique-slug-here",
  "subtitle": "...",
  "excerpt": "...",
  "template_type": "standard | news | tech | seo_blog",
  "content_blocks": [
     // Array of blocks strictly formatted from the list above. Ensure narrative flow.
  ],
  "key_takeaways": [
    {{"title": "...", "content": "..."}}
  ],
  "faq_section": [
    {{"question": "...", "answer": "..."}}
  ]
}}

CRITICAL: Include at least TWO image blocks in the `content_blocks` array. Use highly descriptive 'altText' to ensure the automation engine can fetch a relevant matching photo.
CRITICAL: Return ONLY valid JSON. Do not include markdown codeblocks like ```json around the output.
CRITICAL: DO NOT use markdown asterisks (**) or markdown formatting inside the text values (e.g., inside paragraphs, lists, or headers). Output plain text only. The frontend CMS handles styling natively.
"""


SEO_OPTIMIZATION_PROMPT = """
Optimize the following article for SEO and high-end editorial discovery.

ARTICLE:
{article_json}

TASKS:
1. Assign a `focus_keyword` (string).
2. Suggest 5-7 `secondary_keywords` (array of strings).
3. Create a `meta_title` (max 60 chars).
4. Create a `meta_description` (max 160 chars).
5. Generate an `ai_summary` (2-3 sentences explaining the strategic value of the article).
6. Create an `image_prompt`: A highly detailed, cinematic description of an image that would accompany this article (e.g., "A futuristic representation of a quantum chip, glowing with blue energy, with digital data streams in the background, high contrast, cinematic lighting, 8k").
7. Add `schema_markup` (standard Article schema in JSON format).

OUTPUT FORMAT: Return the original article JSON with these new exact fields merged into the root of the JSON object.

CRITICAL: Return ONLY valid JSON. Do not include markdown codeblocks like ```json around the output. Just the raw JSON object.
"""
