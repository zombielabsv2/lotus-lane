"""
Daimoku Daily — personalized Nichiren Buddhist wisdom email generator.

For each subscriber due for an email:
1. Pick a challenge category (rotating, not repeating recent ones)
2. Search the knowledge base for relevant passages
3. Use Claude Sonnet to generate a personalized email
4. Send via Resend API
5. Log in daimoku_email_log
"""

import json
import os
import random
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

# Path to knowledge base — in CI this is cloned alongside the repo
CHUNKS_PATH = os.environ.get(
    "CHUNKS_PATH",
    str(Path(__file__).parent.parent.parent / "nichiren-chatbot" / "data" / "processed" / "chunks.json"),
)

# Preferred collections (writings > dictionary)
PREFERRED_COLLECTIONS = [
    "The Writings of Nichiren Daishonin, Volume 1",
    "The Writings of Nichiren Daishonin, Volume 2",
    "The Wisdom for Creating Happiness and Peace",
    "Daisaku Ikeda Writings",
    "The Record of the Orally Transmitted Teachings",
    "Selected Lectures on the Gosho",
    "Learning from the Gosho",
    "The Basics of Nichiren Buddhism for the New Era of Worldwide Kosen-rufu",
    "Lectures on the Hoben and Juryo Chapters of the Lotus Sutra",
]

# Challenge keywords for searching the knowledge base
CHALLENGE_KEYWORDS = {
    "career": [
        "work", "vocation", "livelihood", "effort", "mission", "purpose",
        "persevere", "value creation", "contribute", "society", "ability",
        "employment", "calling", "talent", "diligence", "strive",
    ],
    "health": [
        "illness", "sick", "medicine", "healing", "body", "life force",
        "recovery", "vitality", "health", "suffering", "pain", "cure",
        "longevity", "strong", "physical", "mental",
    ],
    "relationships": [
        "relationship", "friendship", "love", "trust", "harmony",
        "compassion", "understanding", "bond", "heart", "sincerity",
        "together", "forgiveness", "empathy", "partner", "connection",
    ],
    "family": [
        "family", "parent", "child", "mother", "father", "home",
        "filial", "household", "children", "spouse", "husband", "wife",
        "siblings", "responsibility", "protection",
    ],
    "finances": [
        "wealth", "treasure", "fortune", "poverty", "prosperity",
        "benefit", "offerings", "material", "economic", "money",
        "livelihood", "abundance", "generosity",
    ],
    "self-doubt": [
        "doubt", "confidence", "courage", "fear", "hesitation",
        "buddha nature", "potential", "believe", "faith", "strength",
        "self", "worthy", "capable", "overcome", "determination",
    ],
    "grief": [
        "grief", "loss", "death", "mourning", "sorrow", "impermanence",
        "separation", "suffering", "tears", "passing", "departed",
        "comfort", "eternity", "life and death",
    ],
    "perseverance": [
        "persevere", "persist", "never give up", "endure", "patience",
        "winter", "spring", "obstacle", "struggle", "victory",
        "determination", "challenge", "hardship", "advance", "continue",
    ],
    # --- Apr 2026: narrow buckets 1:1 with /wisdom/ articles -----------------
    "burnout": [
        "burnout", "exhausted", "depleted", "hustle", "running on empty",
        "work", "tired", "rest", "recover", "breath",
    ],
    "toxic-workplace": [
        "toxic", "hostile", "boss", "coworker", "survive", "difficult people",
        "workplace", "bully", "wisdom", "courage",
    ],
    "sidelined": [
        "sidelined", "invisible", "unseen", "overlooked", "forgotten",
        "ignored", "passed over", "meeting", "dignity", "presence",
    ],
    "imposter": [
        "doubt", "fraud", "impostor", "worthy", "belong", "confidence",
        "buddha nature", "capable", "trust", "self",
    ],
    "relationship-conflict": [
        "relationship", "partner", "conflict", "falling apart", "distance",
        "strangers", "love", "heart", "understanding", "bond",
    ],
    "divorce": [
        "divorce", "marriage", "separation", "ending", "ended", "parting",
        "unraveling", "loss", "life and death", "impermanence",
    ],
    "parenting": [
        "parent", "child", "children", "mother", "father", "raising",
        "family", "exhausted parent", "home", "responsibility",
    ],
    "caregiving": [
        "caregiver", "caring for", "aging", "parent", "disabled", "sick",
        "tend", "burden", "compassion", "patience",
    ],
    "forgiveness": [
        "forgive", "forgiveness", "let go", "wounded", "hurt", "resentment",
        "grudge", "compassion", "heart",
    ],
    "money": [
        "money", "wealth", "treasure", "poverty", "prosperity", "debt",
        "bills", "financial", "livelihood", "abundance",
    ],
    "chronic-illness": [
        "illness", "chronic", "body", "pain", "diagnosis", "suffering",
        "recovery", "life force", "vitality", "healing",
    ],
    "depression": [
        "depression", "fog", "heavy", "dark", "bed", "hopeless",
        "mental", "life force", "hope", "winter",
    ],
    "anxiety": [
        "anxiety", "worry", "mind", "sleep", "3am", "overthinking",
        "panic", "fear", "calm", "courage",
    ],
    "loneliness": [
        "lonely", "alone", "isolation", "disconnected", "friendship",
        "connection", "heart", "together", "presence",
    ],
    "starting-over": [
        "start over", "begin again", "reset", "new chapter", "fresh",
        "rebuild", "courage", "persevere", "winter", "spring",
    ],
}

# ---------------------------------------------------------------------------
# Knowledge Base Search
# ---------------------------------------------------------------------------

_chunks_cache = None

# Path to Ikeda quotes library
IKEDA_QUOTES_PATH = Path(__file__).parent.parent / "ikeda" / "quotes.json"

# ---------------------------------------------------------------------------
# Welcome Sequence — Challenge-to-Theme Mapping
# ---------------------------------------------------------------------------

CHALLENGE_THEME_MAP = {
    # Legacy broad keys (retired from signup Apr 2026, still on existing rows)
    "career": ["action", "victory"],
    "health": ["health", "perseverance"],
    "relationships": ["compassion", "friendship"],
    "family": ["compassion", "gratitude"],
    "finances": ["perseverance", "action"],
    "self-doubt": ["courage", "human-revolution"],
    "grief": ["life-and-death", "hope"],
    "perseverance": ["perseverance", "victory"],
    # Apr 2026: narrow buckets
    "burnout": ["perseverance", "health"],
    "toxic-workplace": ["courage", "wisdom"],
    "sidelined": ["courage", "human-revolution"],
    "imposter": ["courage", "human-revolution"],
    "relationship-conflict": ["compassion", "dialogue"],
    "divorce": ["life-and-death", "hope"],
    "parenting": ["compassion", "education"],
    "caregiving": ["compassion", "perseverance"],
    "forgiveness": ["compassion", "wisdom"],
    "money": ["perseverance", "action"],
    "chronic-illness": ["health", "life-and-death"],
    "depression": ["health", "hope"],
    "anxiety": ["courage", "hope"],
    "loneliness": ["friendship", "compassion"],
    "starting-over": ["perseverance", "courage"],
}

CHALLENGE_LABELS = {
    # Legacy broad keys (retired from signup Apr 2026, still on existing rows)
    "career": "career and work",
    "health": "health",
    "relationships": "relationships",
    "family": "family",
    "finances": "finances",
    "self-doubt": "self-doubt",
    "grief": "grief and loss",
    "perseverance": "perseverance",
    # Apr 2026: narrow buckets
    "burnout": "burning out at work",
    "toxic-workplace": "a toxic workplace",
    "sidelined": "feeling invisible at work",
    "imposter": "feeling like a fraud",
    "relationship-conflict": "a relationship falling apart",
    "divorce": "a marriage ending",
    "parenting": "parenting that is breaking you",
    "caregiving": "caring for someone who can't care for themselves",
    "forgiveness": "the struggle to forgive",
    "money": "money worries",
    "chronic-illness": "a body that is failing you",
    "depression": "depression that won't lift",
    "anxiety": "a mind that won't stop",
    "loneliness": "loneliness even in a crowd",
    "starting-over": "starting over",
}

# When a narrow-bucket subscriber hits the welcome-email step 2 (chanting tips),
# fall back to the closest legacy bucket so the tip text remains relevant.
LEGACY_CHANTING_FALLBACK = {
    "burnout": "career",
    "toxic-workplace": "career",
    "sidelined": "career",
    "imposter": "self-doubt",
    "relationship-conflict": "relationships",
    "divorce": "relationships",
    "parenting": "family",
    "caregiving": "family",
    "forgiveness": "relationships",
    "money": "finances",
    "chronic-illness": "health",
    "depression": "health",
    "anxiety": "self-doubt",
    "loneliness": "relationships",
    "starting-over": "perseverance",
}

FREQUENCY_LABELS = {
    "daily": "tomorrow morning",
    "thrice_weekly": "on the next Mon, Wed, or Fri",
    "weekly": "next Monday",
}


def _load_ikeda_as_chunks():
    """Load Ikeda quotes library and convert to chunk format for unified search."""
    if not IKEDA_QUOTES_PATH.exists():
        return []

    with open(IKEDA_QUOTES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = []
    for theme in data.get("themes", []):
        for quote in theme.get("quotes", []):
            chunks.append({
                "text": quote["text"],
                "token_count": len(quote["text"].split()),
                "metadata": {
                    "collection_name": "Daisaku Ikeda Writings",
                    "title": quote.get("source", "Daisaku Ikeda"),
                    "theme": theme["id"],
                    "theme_name": theme["name"],
                },
            })
    return chunks


def load_chunks():
    """Load and cache the knowledge base chunks (Nichiren writings + Ikeda quotes)."""
    global _chunks_cache
    if _chunks_cache is not None:
        return _chunks_cache

    chunks_path = Path(CHUNKS_PATH)
    if not chunks_path.exists():
        print(f"  [WARN] Chunks file not found at {chunks_path}")
        _chunks_cache = []
    else:
        with open(chunks_path, "r", encoding="utf-8") as f:
            all_chunks = json.load(f)

        # Filter to preferred collections and minimum quality
        _chunks_cache = [
            c for c in all_chunks
            if c.get("metadata", {}).get("collection_name", "") in PREFERRED_COLLECTIONS
            and c.get("token_count", 0) >= 80
        ]
        print(f"  [KB] Loaded {len(_chunks_cache)} quality chunks from {len(all_chunks)} total")

    # Add Ikeda quotes to the pool
    ikeda_chunks = _load_ikeda_as_chunks()
    if ikeda_chunks:
        _chunks_cache.extend(ikeda_chunks)
        print(f"  [KB] Added {len(ikeda_chunks)} Ikeda quotes to knowledge base")

    return _chunks_cache


def search_chunks(challenge: str, limit: int = 10) -> list[dict]:
    """
    Simple keyword search for relevant passages.
    Returns top chunks matching the challenge keywords.
    """
    chunks = load_chunks()
    keywords = CHALLENGE_KEYWORDS.get(challenge, [challenge])

    scored = []
    for chunk in chunks:
        text_lower = chunk["text"].lower()
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            # Bonus for Nichiren's own writings
            coll = chunk.get("metadata", {}).get("collection_name", "")
            if "Writings of Nichiren" in coll:
                score += 2
            elif "Ikeda" in coll or "Wisdom" in coll:
                score += 1
            scored.append((score, chunk))

    scored.sort(key=lambda x: -x[0])

    # Return top chunks, with some randomness to avoid always picking the same ones
    top = scored[:30]
    if len(top) > limit:
        selected = random.sample(top, limit)
    else:
        selected = top

    return [c for _, c in selected]


# ---------------------------------------------------------------------------
# Supabase Helpers
# ---------------------------------------------------------------------------

def supabase_get(endpoint: str, params: dict = None) -> list:
    """GET from Supabase REST API."""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{endpoint}",
        headers=headers,
        params=params or {},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def supabase_post(endpoint: str, data: dict) -> dict:
    """POST to Supabase REST API."""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{endpoint}",
        headers=headers,
        json=data,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def supabase_patch(endpoint: str, params: dict, data: dict) -> None:
    """PATCH on Supabase REST API."""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{endpoint}",
        headers=headers,
        params=params,
        json=data,
        timeout=30,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Subscriber Management
# ---------------------------------------------------------------------------

def get_due_subscribers() -> list[dict]:
    """
    Get all active subscribers who are due for an email today.

    Frequency rules:
    - daily: every day
    - thrice_weekly: Mon, Wed, Fri (weekday 0, 2, 4)
    - weekly: Monday only (weekday 0)
    """
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Monday

    subscribers = supabase_get("daimoku_subscribers", {
        "active": "eq.true",
        "confirmed": "eq.true",
        "select": "*",
    })

    due = []
    for sub in subscribers:
        freq = sub.get("frequency", "weekly")

        # Check if today matches the frequency
        if freq == "daily":
            pass  # always due
        elif freq == "thrice_weekly":
            if weekday not in (0, 2, 4):
                continue
        elif freq == "weekly":
            if weekday != 0:
                continue

        # Check if already sent today
        last_sent = sub.get("last_sent_at")
        if last_sent:
            last_sent_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
            if last_sent_dt.date() == now.date():
                continue

        due.append(sub)

    return due


def get_recent_categories(subscriber_id: str, limit: int = 5) -> list[str]:
    """Get recently sent challenge categories for a subscriber to avoid repetition."""
    logs = supabase_get("daimoku_email_log", {
        "subscriber_id": f"eq.{subscriber_id}",
        "select": "challenge_category",
        "order": "sent_at.desc",
        "limit": str(limit),
    })
    return [log["challenge_category"] for log in logs if log.get("challenge_category")]


def pick_challenge(subscriber: dict) -> str:
    """
    Pick a challenge category for this subscriber.
    Rotates through their challenges, avoiding recent repeats.
    """
    challenges = subscriber.get("challenges", [])
    if not challenges:
        return "perseverance"  # fallback

    recent = get_recent_categories(subscriber["id"])

    # Prefer challenges not recently sent
    unsent = [c for c in challenges if c not in recent]
    if unsent:
        return random.choice(unsent)

    # All have been sent recently — pick least recent
    return challenges[0] if challenges else "perseverance"


# ---------------------------------------------------------------------------
# Welcome Sequence (Template-based — no Claude API)
# ---------------------------------------------------------------------------

_ikeda_quotes_cache = None


def _load_ikeda_quotes() -> dict:
    """Load and cache Ikeda quotes keyed by theme ID."""
    global _ikeda_quotes_cache
    if _ikeda_quotes_cache is not None:
        return _ikeda_quotes_cache

    if not IKEDA_QUOTES_PATH.exists():
        _ikeda_quotes_cache = {}
        return _ikeda_quotes_cache

    with open(IKEDA_QUOTES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    _ikeda_quotes_cache = {}
    for theme in data.get("themes", []):
        _ikeda_quotes_cache[theme["id"]] = theme.get("quotes", [])
    return _ikeda_quotes_cache


def _pick_ikeda_quote(theme_ids: list[str]) -> dict:
    """Pick a random Ikeda quote from the given theme IDs."""
    quotes_by_theme = _load_ikeda_quotes()
    pool = []
    for tid in theme_ids:
        pool.extend(quotes_by_theme.get(tid, []))
    if not pool:
        # Fallback: perseverance quotes
        pool = quotes_by_theme.get("perseverance", [])
    if not pool:
        return {"text": "Winter always turns to spring.", "source": "Nichiren Daishonin"}
    return random.choice(pool)


def get_welcome_due_subscribers() -> list[dict]:
    """
    Find subscribers who haven't completed the 3-email welcome sequence.

    Logic:
    - welcome_1: due immediately (no welcome_1 log entry exists)
    - welcome_2: due if welcome_1 was sent >= 1 day ago, and no welcome_2 log
    - welcome_3: due if welcome_2 was sent >= 1 day ago, and no welcome_3 log
    """
    subscribers = supabase_get("daimoku_subscribers", {
        "active": "eq.true",
        "confirmed": "eq.true",
        "select": "*",
    })

    due = []
    now = datetime.now(timezone.utc)

    for sub in subscribers:
        sub_id = sub["id"]

        # Get all welcome log entries for this subscriber
        welcome_logs = supabase_get("daimoku_email_log", {
            "subscriber_id": f"eq.{sub_id}",
            "challenge_category": "like.welcome_%",
            "select": "challenge_category,sent_at,status",
            "order": "sent_at.asc",
        })

        # Build a set of completed welcome steps
        completed = set()
        step_times = {}
        for log in welcome_logs:
            cat = log.get("challenge_category", "")
            if cat in ("welcome_1", "welcome_2", "welcome_3") and log.get("status") == "sent":
                completed.add(cat)
                step_times[cat] = datetime.fromisoformat(
                    log["sent_at"].replace("Z", "+00:00")
                )

        # Determine next step
        if "welcome_1" not in completed:
            due.append({**sub, "_welcome_step": 1})
        elif "welcome_2" not in completed:
            # Check if welcome_1 was sent >= 1 day ago
            w1_time = step_times.get("welcome_1")
            if w1_time and (now - w1_time) >= timedelta(days=1):
                due.append({**sub, "_welcome_step": 2})
        elif "welcome_3" not in completed:
            # Check if welcome_2 was sent >= 1 day ago
            w2_time = step_times.get("welcome_2")
            if w2_time and (now - w2_time) >= timedelta(days=1):
                due.append({**sub, "_welcome_step": 3})
        # else: welcome sequence complete — skip

    return due


def _build_welcome_html(subject: str, body_sections: list[dict], subscriber_email: str = "") -> str:
    """
    Build a welcome email HTML using the same template style as regular emails.

    body_sections is a list of dicts with keys:
      - type: 'text' | 'quote' | 'highlight' | 'practice'
      - content: str
      - source: str (for quotes only)
    """
    sections_html = ""
    for section in body_sections:
        stype = section.get("type", "text")
        content = section["content"]

        if stype == "text":
            sections_html += f"""
        <tr><td style="padding:16px 30px 0;">
          <p style="margin:0; font-size:15px; line-height:1.7; color:#333;">
            {content}
          </p>
        </td></tr>"""
        elif stype == "quote":
            source = section.get("source", "")
            sections_html += f"""
        <tr><td style="padding:20px 30px;">
          <div style="background:#fdf8f0; border-left:4px solid #c0392b; padding:16px 20px; border-radius:0 8px 8px 0;">
            <p style="margin:0; font-size:14px; line-height:1.7; color:#444; font-style:italic;">
              "{content}"
            </p>
            <p style="margin:8px 0 0; font-size:12px; color:#999;">
              - {source}
            </p>
          </div>
        </td></tr>"""
        elif stype == "highlight":
            sections_html += f"""
        <tr><td style="padding:16px 30px;">
          <div style="background:#f0f4fd; border-radius:8px; padding:16px 20px;">
            <p style="margin:0; font-size:14px; line-height:1.7; color:#333;">
              {content}
            </p>
          </div>
        </td></tr>"""
        elif stype == "practice":
            sections_html += f"""
        <tr><td style="padding:16px 30px;">
          <div style="background:#f0fdf4; border-radius:8px; padding:16px 20px;">
            <p style="margin:0; font-size:13px; font-weight:600; color:#15803d; text-transform:uppercase; letter-spacing:0.05em;">
              Try This
            </p>
            <p style="margin:8px 0 0; font-size:14px; line-height:1.6; color:#333;">
              {content}
            </p>
          </div>
        </td></tr>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#faf9f6; font-family:'Segoe UI',system-ui,-apple-system,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#faf9f6; padding:20px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:white; border-radius:12px; overflow:hidden; box-shadow:0 2px 16px rgba(0,0,0,0.06);">

        <!-- Header -->
        <tr><td style="background:#c0392b; padding:20px 30px; text-align:center;">
          <h1 style="margin:0; color:white; font-size:20px; font-weight:300; letter-spacing:0.1em;">
            The <strong>Lotus</strong> Lane
          </h1>
          <p style="margin:4px 0 0; color:rgba(255,255,255,0.8); font-size:12px; font-style:italic;">
            Daimoku Daily
          </p>
        </td></tr>

        <!-- Body sections -->
        {sections_html}

        <!-- Footer -->
        <tr><td style="background:#f5f2ed; padding:20px 30px; text-align:center;">
          <p style="margin:0; font-size:12px; color:#999;">
            Sent with care from <a href="https://thelotuslane.in/" style="color:#c0392b; text-decoration:none;">The Lotus Lane</a>
          </p>
          <p style="margin:8px 0 0; font-size:11px; color:#bbb;">
            You received this because you signed up for Daimoku Daily.
            <br>No longer want these? <a href="mailto:unsubscribe@rxjapps.in?subject=unsubscribe&body=Please%20unsubscribe%20{subscriber_email}" style="color:#999; text-decoration:underline;">Unsubscribe</a>
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_welcome_1(subscriber: dict) -> dict:
    """
    Welcome Email 1 (Day 0): "Welcome to Daimoku Daily"
    Sent immediately on signup.
    """
    name = subscriber.get("name", "friend")
    challenges = subscriber.get("challenges", ["perseverance"])
    frequency = subscriber.get("frequency", "weekly")
    primary_challenge = challenges[0]

    # Human-readable challenge list
    challenge_names = [CHALLENGE_LABELS.get(c, c) for c in challenges]
    if len(challenge_names) == 1:
        challenges_text = challenge_names[0]
    elif len(challenge_names) == 2:
        challenges_text = f"{challenge_names[0]} and {challenge_names[1]}"
    else:
        challenges_text = f"{', '.join(challenge_names[:-1])}, and {challenge_names[-1]}"

    # Pick a relevant Ikeda quote based on primary challenge
    themes = CHALLENGE_THEME_MAP.get(primary_challenge, ["perseverance"])
    quote = _pick_ikeda_quote(themes)
    next_email = FREQUENCY_LABELS.get(frequency, "soon")

    subject = f"Welcome, {name}"

    sections = [
        {
            "type": "text",
            "content": (
                f"Hi {name},<br><br>"
                f"Welcome. You told us you're going through "
                f"<strong>{challenges_text}</strong>, and we want you to know: you're not alone in this, "
                f"and you've taken a real step by showing up."
            ),
        },
        {
            "type": "text",
            "content": (
                "We're going to send you short, personal emails with wisdom passages chosen "
                "for what you're going through, along with a practical way to apply each one today."
            ),
        },
        {
            "type": "text",
            "content": "Here's something to carry with you today:",
        },
        {
            "type": "quote",
            "content": quote["text"],
            "source": f"Daisaku Ikeda, {quote.get('source', '')}",
        },
        {
            "type": "highlight",
            "content": (
                f"<strong>What to expect:</strong> Each email has one passage, "
                f"a grounded interpretation for your situation, and one small practice to try. "
                f"Your first regular email arrives <strong>{next_email}</strong>."
            ),
        },
        {
            "type": "text",
            "content": (
                "Until then - take a deep breath. You have more strength than you know.<br><br>"
                "With warmth,<br>The Lotus Lane"
            ),
        },
    ]

    html_body = _build_welcome_html(subject, sections, subscriber_email=subscriber.get("email", ""))
    return {"subject": subject, "html_body": html_body, "quote": quote["text"], "source": quote.get("source", "")}


def _build_welcome_2(subscriber: dict) -> dict:
    """
    Welcome Email 2 (Day 1): "The Heart of Practice"
    Practical guidance on chanting, tied to their challenge.
    """
    name = subscriber.get("name", "friend")
    challenges = subscriber.get("challenges", ["perseverance"])
    primary_challenge = challenges[0]
    challenge_label = CHALLENGE_LABELS.get(primary_challenge, primary_challenge)

    # A passage about the power of sincere practice
    nichiren_quote = (
        "The blessings contained in a single moment of faith are immeasurable and boundless. "
        "Practice sincerely, and what you need will appear in your heart."
    )
    nichiren_source = "On Attaining Buddhahood in This Lifetime (13th century)"

    # Challenge-specific chanting guidance
    chanting_tips = {
        "career": (
            "When chanting about your career, try visualizing yourself at your most capable and confident. "
            "Don't chant to escape your situation - chant to bring out the wisdom and courage to transform it. "
            "Ask yourself: 'What would I do if I truly believed in my abilities?'"
        ),
        "health": (
            "When chanting for your health, focus on activating your life force - that deep inner vitality "
            "that exists beyond illness. Don't chant in fear. Chant with the determination: 'My life force "
            "is stronger than any illness. I will win over this.'"
        ),
        "relationships": (
            "When chanting about relationships, start by chanting for the other person's happiness - "
            "genuinely, without conditions. This shifts something deep inside you. "
            "Then chant for the wisdom to see what you need to change in yourself."
        ),
        "family": (
            "When chanting about family, resist the urge to chant for others to change. Instead, chant "
            "to transform your own heart first. The ancient wisdom teaches: when you change, your environment changes. "
            "Your family will feel the shift."
        ),
        "finances": (
            "When chanting about finances, focus not on a specific dollar amount but on opening the way forward. "
            "Chant to see opportunities clearly, to make wise decisions, and to develop the life condition "
            "where you naturally attract abundance through value creation."
        ),
        "self-doubt": (
            "When chanting through self-doubt, speak to your Buddha nature directly. Say in your heart: "
            "'I am a Buddha. My potential is limitless.' This isn't wishful thinking - it's the deepest truth "
            "of your existence. Chant until you feel that conviction rise in your chest."
        ),
        "grief": (
            "When chanting through grief, let the tears come. This practice can hold all of your pain. "
            "Chant for the person you've lost - for their peace and happiness wherever they are. "
            "In this tradition, the bonds of love transcend life and death."
        ),
        "perseverance": (
            "When you feel like giving up, chant with extra determination in those exact moments. "
            "The darkest hour is just before dawn. Chant with the resolve: 'I will not be defeated. "
            "I will break through this.' That fighting spirit IS your Buddha nature."
        ),
    }

    tip_key = LEGACY_CHANTING_FALLBACK.get(primary_challenge, primary_challenge)
    tip = chanting_tips.get(tip_key, chanting_tips["perseverance"])

    subject = f"{name}, the heart of practice"

    sections = [
        {
            "type": "text",
            "content": (
                f"Hi {name},<br><br>"
                f"Yesterday we welcomed you. Today, let's talk about one of the most powerful tools you have: "
                f"your voice. Chanting isn't a ritual - "
                f"it's a direct conversation with the deepest part of your own life."
            ),
        },
        {
            "type": "quote",
            "content": nichiren_quote,
            "source": nichiren_source,
        },
        {
            "type": "text",
            "content": (
                "What this means is simple but real: when you chant sincerely, you're not asking "
                "some external force for help. You're activating the wisdom, courage, and compassion "
                "that already exist within your own life."
            ),
        },
        {
            "type": "practice",
            "content": tip,
        },
        {
            "type": "text",
            "content": (
                "Even 5 minutes of sincere practice can shift your entire day. Try it this morning - "
                "and notice how you feel afterward.<br><br>"
                "Warmly,<br>The Lotus Lane"
            ),
        },
    ]

    html_body = _build_welcome_html(subject, sections, subscriber_email=subscriber.get("email", ""))
    return {"subject": subject, "html_body": html_body, "quote": nichiren_quote, "source": nichiren_source}


def _build_welcome_3(subscriber: dict) -> dict:
    """
    Welcome Email 3 (Day 2): "You Are Not Alone"
    Encouragement about community + transition to regular emails.
    """
    name = subscriber.get("name", "friend")
    challenges = subscriber.get("challenges", ["perseverance"])
    frequency = subscriber.get("frequency", "weekly")

    freq_text = {
        "daily": "daily",
        "thrice_weekly": "three-times-a-week",
        "weekly": "weekly",
    }.get(frequency, "regular")

    # Pick an Ikeda quote about perseverance/community
    quote = _pick_ikeda_quote(["perseverance", "friendship", "hope"])

    # Human-readable challenge list
    challenge_names = [CHALLENGE_LABELS.get(c, c) for c in challenges]
    if len(challenge_names) == 1:
        challenges_text = challenge_names[0]
    elif len(challenge_names) == 2:
        challenges_text = f"{challenge_names[0]} and {challenge_names[1]}"
    else:
        challenges_text = f"{', '.join(challenge_names[:-1])}, and {challenge_names[-1]}"

    subject = f"{name}, you are not alone"

    sections = [
        {
            "type": "text",
            "content": (
                f"Hi {name},<br><br>"
                f"Here's something worth remembering: thousands of people around the world "
                f"are going through the same challenges you are - {challenges_text}. "
                f"Every single one of them has sat where you're sitting, wondering if things will get better."
            ),
        },
        {
            "type": "text",
            "content": "They do. Not because circumstances magically change, but because <em>you</em> change.",
        },
        {
            "type": "quote",
            "content": quote["text"],
            "source": f"Daisaku Ikeda, {quote.get('source', '')}",
        },
        {
            "type": "highlight",
            "content": (
                f"From here on, you'll get <strong>{freq_text} emails</strong> chosen for what you're going through. "
                f"Each one pulls from wisdom writings and experienced teachers, "
                f"picked for your specific situation."
            ),
        },
        {
            "type": "text",
            "content": (
                "You've already shown courage by signing up and showing up for three days. "
                "That's not a small thing - that's real resilience.<br><br>"
                "We're rooting for you.<br><br>"
                "With care,<br>The Lotus Lane"
            ),
        },
    ]

    html_body = _build_welcome_html(subject, sections, subscriber_email=subscriber.get("email", ""))
    return {"subject": subject, "html_body": html_body, "quote": quote["text"], "source": quote.get("source", "")}


WELCOME_BUILDERS = {
    1: _build_welcome_1,
    2: _build_welcome_2,
    3: _build_welcome_3,
}


def process_welcome_subscriber(subscriber: dict) -> bool:
    """Process a single welcome email for a subscriber."""
    name = subscriber.get("name", "friend")
    email = subscriber.get("email", "")
    sub_id = subscriber["id"]
    step = subscriber.get("_welcome_step", 1)

    print(f"\n--- Welcome {step}/3: {name} ({email}) ---")

    builder = WELCOME_BUILDERS.get(step)
    if not builder:
        print(f"  [ERROR] Invalid welcome step: {step}")
        return False

    try:
        email_content = builder(subscriber)
    except Exception as e:
        print(f"  [ERROR] Failed to build welcome email: {e}")
        supabase_post("daimoku_email_log", {
            "subscriber_id": sub_id,
            "challenge_category": f"welcome_{step}",
            "status": "generation_failed",
            "subject": str(e)[:200],
        })
        return False

    print(f"  Subject: {email_content['subject']}")

    # Send
    sent = send_email(email, email_content["subject"], email_content["html_body"])

    # Log
    status = "sent" if sent else "send_failed"
    supabase_post("daimoku_email_log", {
        "subscriber_id": sub_id,
        "subject": email_content["subject"],
        "challenge_category": f"welcome_{step}",
        "nichiren_quote": email_content.get("quote", "")[:500],
        "source": email_content.get("source", "")[:200],
        "status": status,
    })

    print(f"  Status: {status}")
    return sent


# ---------------------------------------------------------------------------
# Email Content Generation (Claude Sonnet)
# ---------------------------------------------------------------------------

def generate_email_content(subscriber: dict, challenge: str, passages: list[dict]) -> dict:
    """
    Use Claude Sonnet API to generate a personalized email.
    Returns dict with: subject, html_body, quote, source
    """
    name = subscriber.get("name", "friend")
    situation = subscriber.get("situation_text", "")

    # Build passage context
    passage_texts = []
    for p in passages[:5]:  # top 5 passages
        meta = p.get("metadata", {})
        source = meta.get("title", "")
        collection = meta.get("collection_name", "")
        text = p["text"][:500]  # truncate long passages
        passage_texts.append(f"[{collection} - {source}]\n{text}")

    passages_block = "\n\n---\n\n".join(passage_texts)

    challenge_labels = {
        # Legacy broad keys
        "career": "career and work struggles",
        "health": "health challenges",
        "relationships": "relationship difficulties",
        "family": "family struggles",
        "finances": "financial stress",
        "self-doubt": "self-doubt and lack of confidence",
        "grief": "grief and loss",
        "perseverance": "feeling like giving up",
        # Narrow buckets (Apr 2026)
        "burnout": "burnout at work",
        "toxic-workplace": "surviving a toxic workplace",
        "sidelined": "feeling invisible and overlooked at work",
        "imposter": "feeling like a fraud, like they don't belong",
        "relationship-conflict": "a relationship that is falling apart",
        "divorce": "a marriage that is ending",
        "parenting": "parenting that is breaking them",
        "caregiving": "caring for someone who cannot care for themselves",
        "forgiveness": "the struggle to forgive someone who hurt them",
        "money": "money worries and financial stress",
        "chronic-illness": "living with a body that is failing them",
        "depression": "depression that will not lift",
        "anxiety": "anxiety and a mind that will not stop, especially at night",
        "loneliness": "loneliness even in a crowd",
        "starting-over": "starting over after a life change",
    }
    challenge_desc = challenge_labels.get(challenge, challenge)

    situation_line = ""
    if situation:
        situation_line = f"\nTheir specific situation: {situation}\n"

    prompt = f"""You are a warm, grounded mentor writing a personal email to {name}, who is going through {challenge_desc}.{situation_line}

Below are wisdom passages relevant to their situation. Use ONE of these as the basis for your email. Choose the most relevant and encouraging one.

PASSAGES:
{passages_block}

Write a personal email with these sections:

1. SUBJECT LINE: Warm, specific to their challenge. Not clickbait. Under 60 chars. Avoid religious or tradition-specific words.

2. OPENING (2-3 sentences): Acknowledge their struggle with genuine empathy. Use their name. Don't be preachy or distant. No religious framing.

3. WISDOM PASSAGE: Quote the most relevant passage (the actual words, not a summary). Keep it under 100 words. Include the source title and author exactly as given (attribution is fine).

4. MODERN INTERPRETATION (3-4 sentences): What does this passage mean for {name}'s situation today? Be specific, practical, and grounded. Plain language, not abstract philosophy.

5. PRACTICE SUGGESTION: One concrete action they can do today. Be specific (e.g., "Spend 10 minutes writing about..." or "Take a 15-minute walk and notice..." not "try to practice more").

6. CLOSING (1-2 sentences): Warm encouragement. End with strength, not pity.

IMPORTANT RULES:
- Write like a caring friend, not a religious authority
- Do NOT use tradition-specific jargon in the email body: no "Buddhist", "Nichiren Daishonin", "Gohonzon", "daimoku", "Nam-myoho-renge-kyo", "Bodhisattva", "SGI", "Ikeda Sensei", "practitioner"
- Quote source attributions CAN include the author name (e.g., "Daisaku Ikeda, Discussions on Youth") — that's proper citation
- Be specific to their challenge, not generic
- Keep total email under 300 words
- The passage must be an actual quote from the passages provided (do not invent quotes)
- Use the person's name naturally (not in every paragraph)
- NEVER use em dashes. Use regular dashes (-) instead.
- NEVER use these words: journey, transformative, profound, empower, delve, navigate, embrace, tapestry, nuanced, holistic, foster, leverage, curated, robust, pivotal, paramount, testament, unwavering, seamless, comprehensive, beacon, cornerstone

Return your response in this exact JSON format:
{{
  "subject": "...",
  "opening": "...",
  "quote": "...",
  "quote_source": "...",
  "interpretation": "...",
  "practice": "...",
  "closing": "..."
}}

Return ONLY the JSON, no other text."""

    # Call Claude Sonnet API — with exponential backoff on 429 rate limits
    max_retries = 5
    for attempt in range(max_retries):
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        if resp.status_code == 429:
            # Check Retry-After header first; fall back to exponential backoff
            retry_after = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-requests")
            if retry_after:
                try:
                    wait = int(retry_after)
                except ValueError:
                    wait = min(2 ** attempt * 10, 120)
            else:
                wait = min(2 ** attempt * 10, 120)  # 10s, 20s, 40s, 80s, 120s
            print(f"  [RATE LIMITED] Claude API 429 — waiting {wait}s before retry {attempt + 1}/{max_retries}...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break
    else:
        # All retries exhausted — re-raise the last response error
        resp.raise_for_status()
    result = resp.json()

    # Log to Supabase api_usage_log
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent.parent))
        from usage_logger import log_usage as _log_usage
        usage = result.get("usage", {})
        _log_usage(
            app="lotus_lane", action="daimoku_email", model="claude-sonnet-4-6",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
    except Exception:
        pass  # Don't break email generation if usage logging fails

    # Parse response
    content_text = result["content"][0]["text"].strip()

    # Extract JSON from response (handle markdown code blocks)
    if content_text.startswith("```"):
        content_text = re.sub(r"^```(?:json)?\s*", "", content_text)
        content_text = re.sub(r"\s*```$", "", content_text)

    email_data = json.loads(content_text)

    # Build HTML body
    html_body = build_html_email(email_data, name, subscriber_email=subscriber.get("email", ""))

    return {
        "subject": email_data["subject"],
        "html_body": html_body,
        "quote": email_data.get("quote", ""),
        "source": email_data.get("quote_source", ""),
    }


def build_html_email(data: dict, name: str, subscriber_email: str = "") -> str:
    """Build a beautiful HTML email from the generated content."""
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#faf9f6; font-family:'Segoe UI',system-ui,-apple-system,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#faf9f6; padding:20px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:white; border-radius:12px; overflow:hidden; box-shadow:0 2px 16px rgba(0,0,0,0.06);">

        <!-- Header -->
        <tr><td style="background:#c0392b; padding:20px 30px; text-align:center;">
          <h1 style="margin:0; color:white; font-size:20px; font-weight:300; letter-spacing:0.1em;">
            The <strong>Lotus</strong> Lane
          </h1>
          <p style="margin:4px 0 0; color:rgba(255,255,255,0.8); font-size:12px; font-style:italic;">
            Daimoku Daily
          </p>
        </td></tr>

        <!-- Opening -->
        <tr><td style="padding:30px 30px 0;">
          <p style="margin:0; font-size:15px; line-height:1.7; color:#333;">
            {data['opening']}
          </p>
        </td></tr>

        <!-- Nichiren Quote -->
        <tr><td style="padding:20px 30px;">
          <div style="background:#fdf8f0; border-left:4px solid #c0392b; padding:16px 20px; border-radius:0 8px 8px 0;">
            <p style="margin:0; font-size:14px; line-height:1.7; color:#444; font-style:italic;">
              "{data['quote']}"
            </p>
            <p style="margin:8px 0 0; font-size:12px; color:#999;">
              - {data['quote_source']}
            </p>
          </div>
        </td></tr>

        <!-- Interpretation -->
        <tr><td style="padding:0 30px;">
          <p style="margin:0; font-size:15px; line-height:1.7; color:#333;">
            {data['interpretation']}
          </p>
        </td></tr>

        <!-- Practice Suggestion -->
        <tr><td style="padding:20px 30px;">
          <div style="background:#f0fdf4; border-radius:8px; padding:16px 20px;">
            <p style="margin:0; font-size:13px; font-weight:600; color:#15803d; text-transform:uppercase; letter-spacing:0.05em;">
              Today's Practice
            </p>
            <p style="margin:8px 0 0; font-size:14px; line-height:1.6; color:#333;">
              {data['practice']}
            </p>
          </div>
        </td></tr>

        <!-- Closing -->
        <tr><td style="padding:0 30px 30px;">
          <p style="margin:0; font-size:15px; line-height:1.7; color:#333;">
            {data['closing']}
          </p>
        </td></tr>

        <!-- Footer -->
        <tr><td style="background:#f5f2ed; padding:20px 30px; text-align:center;">
          <p style="margin:0; font-size:12px; color:#999;">
            Sent with care from <a href="https://thelotuslane.in/" style="color:#c0392b; text-decoration:none;">The Lotus Lane</a>
          </p>
          <p style="margin:8px 0 0; font-size:11px; color:#bbb;">
            You received this because you signed up for Daimoku Daily.
            <br>No longer want these? <a href="mailto:unsubscribe@rxjapps.in?subject=unsubscribe&body=Please%20unsubscribe%20{subscriber_email}" style="color:#999; text-decoration:underline;">Unsubscribe</a>
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Email Sending
# ---------------------------------------------------------------------------

def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via Resend API."""
    if not RESEND_API_KEY:
        print(f"  [SKIP] RESEND_API_KEY not set — would send to {to_email}")
        return False

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": "Daily Wisdom <daimoku@rxjapps.in>",
                "to": [to_email],
                "subject": subject,
                "html": html_body,
                "headers": {
                    "List-Unsubscribe": "<mailto:unsubscribe@rxjapps.in>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            },
            timeout=30,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"  [ERROR] Failed to send to {to_email}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def process_subscriber(subscriber: dict) -> bool:
    """Process a single subscriber: pick challenge, generate email, send, log."""
    name = subscriber.get("name", "friend")
    email = subscriber.get("email", "")
    sub_id = subscriber["id"]

    print(f"\n--- Processing: {name} ({email}) ---")

    # 1. Pick challenge category
    challenge = pick_challenge(subscriber)
    print(f"  Challenge: {challenge}")

    # 2. Search knowledge base
    passages = search_chunks(challenge, limit=10)
    if not passages:
        print(f"  [WARN] No passages found for '{challenge}' — using fallback")
        passages = search_chunks("perseverance", limit=10)

    print(f"  Found {len(passages)} relevant passages")

    # 3. Generate email content via Claude
    try:
        email_content = generate_email_content(subscriber, challenge, passages)
    except Exception as e:
        print(f"  [ERROR] Failed to generate email: {e}")
        # Log failure
        supabase_post("daimoku_email_log", {
            "subscriber_id": sub_id,
            "challenge_category": challenge,
            "status": "generation_failed",
            "subject": str(e)[:200],
        })
        return False

    print(f"  Subject: {email_content['subject']}")

    # 4. Send email
    sent = send_email(email, email_content["subject"], email_content["html_body"])

    # 5. Log result
    status = "sent" if sent else "send_failed"
    supabase_post("daimoku_email_log", {
        "subscriber_id": sub_id,
        "subject": email_content["subject"],
        "challenge_category": challenge,
        "nichiren_quote": email_content.get("quote", "")[:500],
        "source": email_content.get("source", "")[:200],
        "status": status,
    })

    # 6. Update last_sent_at
    if sent:
        supabase_patch(
            "daimoku_subscribers",
            {"id": f"eq.{sub_id}"},
            {"last_sent_at": datetime.now(timezone.utc).isoformat()},
        )

    print(f"  Status: {status}")
    return sent


def send_welcome_single(email: str, dry_run: bool = False) -> bool:
    """
    Send welcome_1 to a single subscriber by email. Idempotent — skips if
    welcome_1 already logged. Used by the on-signup trigger workflow so the
    user gets an acknowledgement within ~60s instead of waiting for the
    daily cron.
    """
    email_norm = (email or "").strip().lower()
    if not email_norm:
        print("  [ERROR] No email provided")
        return False

    rows = supabase_get("daimoku_subscribers", {
        "email": f"eq.{email_norm}",
        "active": "eq.true",
        "confirmed": "eq.true",
        "select": "*",
        "limit": "1",
    })
    if not rows:
        print(f"  [SKIP] No confirmed active subscriber for {email_norm}")
        return False
    sub = rows[0]

    existing = supabase_get("daimoku_email_log", {
        "subscriber_id": f"eq.{sub['id']}",
        "challenge_category": "eq.welcome_1",
        "status": "eq.sent",
        "select": "id",
        "limit": "1",
    })
    if existing:
        print(f"  [SKIP] welcome_1 already sent to {email_norm}")
        return False

    sub["_welcome_step"] = 1
    if dry_run:
        content = WELCOME_BUILDERS[1](sub)
        print(f"  [DRY RUN] welcome_1 for {sub.get('name')} ({email_norm}): {content['subject']}")
        return True
    return process_welcome_subscriber(sub)


def main():
    """
    Main entry point.

    Flags:
      --welcome              Process welcome sequence only
      --regular              Process regular daily emails only (legacy default behavior)
      --welcome-single EMAIL Send welcome_1 to a single subscriber (on-signup trigger)
      --force                Send to all active subscribers (ignores frequency/schedule)
      --dry-run              Show what would be sent without sending or logging

    No flags = both welcome + regular (default for cron).
    """
    import sys

    print(f"=== Daimoku Daily — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")

    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv
    only_welcome = "--welcome" in sys.argv and "--regular" not in sys.argv
    only_regular = "--regular" in sys.argv and "--welcome" not in sys.argv

    if "--welcome-single" in sys.argv:
        idx = sys.argv.index("--welcome-single")
        if idx + 1 >= len(sys.argv):
            print("  [FATAL] --welcome-single requires an email argument")
            return
        target_email = sys.argv[idx + 1]

        missing = []
        if not SUPABASE_URL:
            missing.append("SUPABASE_URL")
        if not SUPABASE_SERVICE_KEY:
            missing.append("SUPABASE_SERVICE_KEY")
        if not dry_run and not RESEND_API_KEY:
            missing.append("RESEND_API_KEY")
        if missing:
            print(f"  [FATAL] Missing environment variables: {', '.join(missing)}")
            return

        ok = send_welcome_single(target_email, dry_run=dry_run)
        print(f"\n=== Done: welcome_single {'sent' if ok else 'skipped/failed'} ===")
        return
    # No flags or both flags = run both
    run_welcome = not only_regular
    run_regular = not only_welcome

    # Validate configuration
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_KEY:
        missing.append("SUPABASE_SERVICE_KEY")
    if not dry_run:
        if not RESEND_API_KEY:
            missing.append("RESEND_API_KEY")
        if run_regular and not ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")

    if missing:
        print(f"  [FATAL] Missing environment variables: {', '.join(missing)}")
        return

    total_sent = 0
    total_fail = 0

    # -------------------------------------------------------
    # Phase 1: Welcome Sequence (runs first)
    # -------------------------------------------------------
    if run_welcome:
        print("\n--- Welcome Sequence ---")
        try:
            welcome_due = get_welcome_due_subscribers()
            print(f"Welcome emails due: {len(welcome_due)}")

            for sub in welcome_due:
                step = sub.get("_welcome_step", 1)
                if dry_run:
                    email_content = WELCOME_BUILDERS[step](sub)
                    print(f"\n  [DRY RUN] Welcome {step}/3 for {sub.get('name', '?')} ({sub.get('email', '?')})")
                    print(f"    Subject: {email_content['subject']}")
                    print(f"    Quote: {email_content.get('quote', '')[:80]}...")
                    total_sent += 1
                else:
                    try:
                        success = process_welcome_subscriber(sub)
                        if success:
                            total_sent += 1
                        else:
                            total_fail += 1
                    except Exception as e:
                        print(f"  [ERROR] Welcome error for {sub.get('email', '?')}: {e}")
                        total_fail += 1
        except Exception as e:
            print(f"  [ERROR] Failed to fetch welcome subscribers: {e}")

    # -------------------------------------------------------
    # Phase 2: Regular Daily Emails
    # -------------------------------------------------------
    if run_regular:
        print("\n--- Regular Daily Emails ---")

        if force:
            due = supabase_get("daimoku_subscribers", {"active": "eq.true", "confirmed": "eq.true", "select": "*"})
            print(f"[FORCE] All confirmed active subscribers: {len(due)}")
        else:
            due = get_due_subscribers()
            print(f"Due subscribers: {len(due)}")

        if not due:
            print("No subscribers due for regular email today.")
        else:
            for sub in due:
                if dry_run:
                    challenge = pick_challenge(sub)
                    print(f"\n  [DRY RUN] Regular email for {sub.get('name', '?')} ({sub.get('email', '?')})")
                    print(f"    Challenge: {challenge}")
                    total_sent += 1
                else:
                    try:
                        success = process_subscriber(sub)
                        if success:
                            total_sent += 1
                        else:
                            total_fail += 1
                    except Exception as e:
                        print(f"  [ERROR] Unhandled error for {sub.get('email', '?')}: {e}")
                        total_fail += 1

    print(f"\n=== Done: {total_sent} sent, {total_fail} failed ===")


if __name__ == "__main__":
    main()
