import re
import random
from collections import Counter, deque
from sqlalchemy.orm import Session

from app.crud import crud
from app.models import models

ALL_CATEGORIES = [
    "Health & Medicine",
    "Science & Nature",
    "Economics & Money",
    "Society & Culture",
    "Environment & Energy",
    "Food & Agriculture",
    "Sports",
    "History & Ideas",
    "Business & Work",
    "Psychology & Behavior",
    "Arts, Design & Media",
    "Travel & Geography",
    "Technology & Innovation",
]

TITLE_STRUCTURES = [
    {
        "id": "question",
        "instruction": "Write the title as a genuine, curiosity-provoking question that makes the reader feel they urgently need the answer.",
        "example": "Why Do We Always Wake Up Tired at 3 AM?",
    },
    {
        "id": "contrarian_claim",
        "instruction": "Write the title as a bold, counterintuitive statement that challenges conventional wisdom. Make the reader think 'wait, really?'",
        "example": "Electric Cars Are Getting Heavier, and City Bridges Aren't Ready",
    },
    {
        "id": "narrative_hook",
        "instruction": "Write the title as a specific human story or place-based narrative. It should read like the opening line of a documentary.",
        "example": "How a Small Swedish Town Solved Winter Heating Without Burning Oil",
    },
    {
        "id": "explanatory",
        "instruction": "Write the title as a clear 'here's why X works the way it does' explanation. Promise insight into something the reader encounters but doesn't understand.",
        "example": "The Real Reason Shipping Containers All Look the Same",
    },
    {
        "id": "cultural_story",
        "instruction": "Write the title around a surprising cultural, historical, or human-interest angle. It should feel like discovering a hidden world.",
        "example": "The Archivists Racing to Save Extinct Regional Cheeses",
    },
    {
        "id": "data_verdict",
        "instruction": "Write the title as a decisive analytical verdict backed by data or a trend shift. It should feel like a strategic intelligence briefing, not a listicle.",
        "example": "Reusable Rockets Just Smashed the Orbital Price Floor",
    },
]

# Words too common or short to be meaningful for cooldown
STOP_WORDS = frozenset({
    "the", "of", "a", "an", "in", "to", "for", "and", "is", "why",
    "how", "what", "your", "are", "its", "has", "was", "be", "by",
    "or", "on", "at", "it", "no", "not", "from", "with", "as", "but",
    "you", "new", "now", "just", "all", "into", "been", "than", "more",
    "most", "can", "will", "one", "way", "our", "get", "that", "this",
    "end", "era", "age", "big", "top", "yet", "too", "out", "over",
    "next", "last", "back", "being", "about", "every", "beyond", "stop",
})

# Regex patterns to detect formulaic title structures
KNOWN_TITLE_PATTERNS = [
    (re.compile(r"^The \w+ Protocol", re.IGNORECASE), "The [X] Protocol"),
    (re.compile(r"^The Great \w+", re.IGNORECASE), "The Great [X]"),
    (re.compile(r"^The \w+ Blueprint", re.IGNORECASE), "The [X] Blueprint"),
    (re.compile(r"^The \w+ Pivot", re.IGNORECASE), "The [X] Pivot"),
    (re.compile(r"^The \w+ Audit", re.IGNORECASE), "The [X] Audit"),
    (re.compile(r"^The Death of", re.IGNORECASE), "The Death of [X]"),
    (re.compile(r"^The Architecture of", re.IGNORECASE), "The Architecture of [X]"),
    (re.compile(r"^The \w+ Reset", re.IGNORECASE), "The [X] Reset"),
    (re.compile(r"^The \w+ Shift", re.IGNORECASE), "The [X] Shift"),
    (re.compile(r"^The \w+ Paradox", re.IGNORECASE), "The [X] Paradox"),
    (re.compile(r"^The \w+ Trap", re.IGNORECASE), "The [X] Trap"),
    (re.compile(r"^The End of", re.IGNORECASE), "The End of [X]"),
]


# ─────────────────────────────────────────────────────────────────────────────
# ROUND-ROBIN QUEUE
# ─────────────────────────────────────────────────────────────────────────────

class RoundRobinQueue:
    def __init__(self, db: Session, state_key: str, all_items: list):
        self.db = db
        self.state_key = state_key
        self.all_items = all_items
        self._load()

    def _load(self):
        """Load queue from DB, or initialize fresh if empty/missing."""
        stored = crud.get_automation_state(self.db, self.state_key)
        if stored and isinstance(stored, list) and len(stored) > 0:
            self.queue = deque(stored)
        else:
            self._reshuffle()

    def _reshuffle(self):
        """Shuffle all items into a fresh queue."""
        items = list(self.all_items)
        random.shuffle(items)
        self.queue = deque(items)

    def _save(self):
        """Persist current queue state to DB."""
        crud.set_automation_state(self.db, self.state_key, list(self.queue))

    def pop_batch(self, n: int = 3) -> list:
        """
        Pop n items. If fewer than n remain, reshuffle and refill first.
        Returns exactly n items (guaranteed distinct within the batch).
        """
        if len(self.queue) < n:
            self._reshuffle()

        batch = []
        for _ in range(n):
            batch.append(self.queue.popleft())

        self._save()
        return batch

class RollingCooldown:

    def __init__(self, recent_titles: list, window: int = 30,
                 word_threshold: int = 4, pattern_threshold: int = 2):
        self.titles = recent_titles[-window:]
        self.word_threshold = word_threshold
        self.pattern_threshold = pattern_threshold

    def compute(self) -> tuple:
        """Returns (cooled_words: list[str], cooled_patterns: list[str])."""
        cooled_words = self._compute_word_cooldowns()
        cooled_patterns = self._compute_pattern_cooldowns()
        return cooled_words, cooled_patterns

    def _compute_word_cooldowns(self) -> list:
        """Find words appearing >= threshold times across recent titles."""
        word_counts = Counter()
        for title in self.titles:
            # Extract unique words per title (so one title can't inflate counts)
            words = set(re.findall(r'\b[A-Za-z]{3,}\b', title.lower()))
            words -= STOP_WORDS
            word_counts.update(words)

        return [word for word, count in word_counts.most_common()
                if count >= self.word_threshold]

    def _compute_pattern_cooldowns(self) -> list:
        """Find title patterns matching >= threshold times."""
        cooled = []
        for regex, label in KNOWN_TITLE_PATTERNS:
            matches = sum(1 for t in self.titles if regex.match(t))
            if matches >= self.pattern_threshold:
                cooled.append(label)
        return cooled


def compute_diversity_score(titles: list, categories: list) -> float:

    if not titles:
        return 10.0

    # 1. Pattern repetition score (0-10)
    total_pattern_matches = 0
    for regex, _ in KNOWN_TITLE_PATTERNS:
        total_pattern_matches += sum(1 for t in titles if regex.match(t))
    pattern_ratio = total_pattern_matches / len(titles) if titles else 0
    # If 80%+ titles match known patterns, score = 0. If 0% match, score = 10.
    pattern_score = max(0, 10 - (pattern_ratio * 12.5))

    # 2. Word repetition score (0-10)
    word_counts = Counter()
    for title in titles:
        words = set(re.findall(r'\b[A-Za-z]{3,}\b', title.lower()))
        words -= STOP_WORDS
        word_counts.update(words)

    if word_counts:
        # Count how many words appear in 10%+ of titles
        high_freq_words = sum(1 for _, c in word_counts.items()
                              if c >= max(4, len(titles) * 0.1))
        # More than 20 high-freq words = score 0
        word_score = max(0, 10 - (high_freq_words / 2))
    else:
        word_score = 10.0

    # 3. Category concentration score (0-10) via Gini-like measure
    if categories:
        cat_counts = Counter(categories)
        n_cats = len(ALL_CATEGORIES)
        expected = len(categories) / n_cats if n_cats > 0 else 1
        deviations = sum(abs(cat_counts.get(c, 0) - expected)
                         for c in ALL_CATEGORIES)
        max_deviation = len(categories) * 2  # theoretical max
        gini_ratio = deviations / max_deviation if max_deviation > 0 else 0
        category_score = max(0, 10 - (gini_ratio * 10))
    else:
        category_score = 10.0

    # Weighted average
    final = (pattern_score * 0.4) + (word_score * 0.3) + (category_score * 0.3)
    return round(min(10.0, max(0.0, final)), 1)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CONTROLLER
# ─────────────────────────────────────────────────────────────────────────────

class DiversityController:
    """
    Orchestrates all diversity controls for a single pipeline run.
    
    Usage in engine.py:
        controller = DiversityController(db)
        assignments = controller.get_batch_assignments(batch_size=3)
        cooldown_text = controller.get_cooldown_text()
    """

    def __init__(self, db: Session):
        self.db = db

        # Resolve actual categories from DB, fallback to ALL_CATEGORIES
        db_categories = [c.name for c in crud.get_categories(db)]
        self.categories = db_categories if db_categories else list(ALL_CATEGORIES)

        self.category_queue = RoundRobinQueue(
            db, "category_queue", self.categories
        )
        self.structure_queue = RoundRobinQueue(
            db, "title_structure_queue",
            [s["id"] for s in TITLE_STRUCTURES]
        )

        # Archetype rotation: standard, guide, trend
        self.archetype_queue = RoundRobinQueue(
            db, "archetype_queue",
            ["standard", "guide", "trend"]
        )

    def get_batch_assignments(self, batch_size: int = 3) -> list:
        """
        Returns a list of dicts, one per topic slot:
        [
            {
                "category": "Food & Agriculture",
                "template_type": "guide",
                "title_structure": {
                    "id": "narrative_hook",
                    "instruction": "...",
                    "example": "..."
                }
            },
            ...
        ]
        """
        categories = self.category_queue.pop_batch(batch_size)
        structure_ids = self.structure_queue.pop_batch(batch_size)
        archetypes = self.archetype_queue.pop_batch(batch_size)

        # Map structure IDs to full structure dicts
        structure_map = {s["id"]: s for s in TITLE_STRUCTURES}

        assignments = []
        for i in range(batch_size):
            assignments.append({
                "category": categories[i],
                "template_type": archetypes[i],
                "title_structure": structure_map.get(
                    structure_ids[i], TITLE_STRUCTURES[0]
                ),
            })

        return assignments

    def get_cooldown_text(self, window: int = 30) -> tuple:

        recent_articles = (
            self.db.query(models.Article.title)
            .order_by(models.Article.created_at.desc())
            .limit(window)
            .all()
        )
        recent_titles = [a.title for a in recent_articles if a.title]

        cooldown = RollingCooldown(recent_titles, window=window)
        cooled_words, cooled_patterns = cooldown.compute()

        words_text = ", ".join(cooled_words[:20]) if cooled_words else "None"
        patterns_text = ", ".join(cooled_patterns) if cooled_patterns else "None"

        return words_text, patterns_text

    def format_assignments_for_prompt(self, assignments: list) -> str:
        """
        Format batch assignments as clear, mandatory instructions for the LLM.
        """
        lines = []
        for i, a in enumerate(assignments, 1):
            struct = a["title_structure"]
            lines.append(
                f"Topic {i}:\n"
                f"  - MUST be category: {a['category']}\n"
                f"  - MUST use template_type: {a['template_type']}\n"
                f"  - MUST use title structure: {struct['id']}\n"
                f"    Instruction: {struct['instruction']}\n"
                f"    Example: \"{struct['example']}\""
            )
        return "\n\n".join(lines)
