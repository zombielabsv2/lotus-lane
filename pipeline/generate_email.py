"""
Daimoku Daily — personalized Nichiren Buddhist wisdom email generator.

For each subscriber due for an email:
1. Pick a challenge category (rotating, not repeating recent ones)
2. Search the knowledge base for relevant passages
3. Use Claude Sonnet to generate a personalized email
4. Send via Gmail SMTP
5. Log in daimoku_email_log
"""

import json
import os
import random
import re
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

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
}

# ---------------------------------------------------------------------------
# Knowledge Base Search
# ---------------------------------------------------------------------------

_chunks_cache = None


def load_chunks():
    """Load and cache the knowledge base chunks."""
    global _chunks_cache
    if _chunks_cache is not None:
        return _chunks_cache

    chunks_path = Path(CHUNKS_PATH)
    if not chunks_path.exists():
        print(f"  [WARN] Chunks file not found at {chunks_path}")
        _chunks_cache = []
        return _chunks_cache

    with open(chunks_path, "r", encoding="utf-8") as f:
        all_chunks = json.load(f)

    # Filter to preferred collections and minimum quality
    _chunks_cache = [
        c for c in all_chunks
        if c.get("metadata", {}).get("collection_name", "") in PREFERRED_COLLECTIONS
        and c.get("token_count", 0) >= 80
    ]

    print(f"  [KB] Loaded {len(_chunks_cache)} quality chunks from {len(all_chunks)} total")
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
        passage_texts.append(f"[{collection} — {source}]\n{text}")

    passages_block = "\n\n---\n\n".join(passage_texts)

    challenge_labels = {
        "career": "career and work struggles",
        "health": "health challenges",
        "relationships": "relationship difficulties",
        "family": "family struggles",
        "finances": "financial stress",
        "self-doubt": "self-doubt and lack of confidence",
        "grief": "grief and loss",
        "perseverance": "feeling like giving up",
    }
    challenge_desc = challenge_labels.get(challenge, challenge)

    situation_line = ""
    if situation:
        situation_line = f"\nTheir specific situation: {situation}\n"

    prompt = f"""You are a warm, wise Buddhist mentor writing a personal email to {name}, who is going through {challenge_desc}.{situation_line}

Below are relevant passages from Nichiren Daishonin's writings and Buddhist commentaries. Use ONE of these as the basis for your email. Choose the most relevant and encouraging one.

PASSAGES:
{passages_block}

Write a personal email with these sections:

1. SUBJECT LINE: Warm, specific to their challenge. Not clickbait. Under 60 chars. Do not use the word "Daimoku" in the subject.

2. OPENING (2-3 sentences): Acknowledge their struggle with genuine empathy. Use their name. Don't be preachy or distant.

3. NICHIREN PASSAGE: Quote the most relevant passage (the actual words, not a summary). Keep it under 100 words. Include the source title.

4. MODERN INTERPRETATION (3-4 sentences): What does this passage mean for {name}'s situation today? Be specific, practical, and grounded. Not abstract philosophy.

5. PRACTICE SUGGESTION: One concrete action they can do today. Be specific (e.g., "Chant for 10 minutes focusing on..." not "try to practice more").

6. CLOSING (1-2 sentences): Warm encouragement. End with strength, not pity.

IMPORTANT RULES:
- Write like a caring friend, not a religious authority
- Be specific to their challenge, not generic
- Keep total email under 300 words
- The Nichiren passage must be an actual quote from the passages provided (do not invent quotes)
- Use the person's name naturally (not in every paragraph)

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

    # Call Claude Sonnet API
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()

    # Parse response
    content_text = result["content"][0]["text"].strip()

    # Extract JSON from response (handle markdown code blocks)
    if content_text.startswith("```"):
        content_text = re.sub(r"^```(?:json)?\s*", "", content_text)
        content_text = re.sub(r"\s*```$", "", content_text)

    email_data = json.loads(content_text)

    # Build HTML body
    html_body = build_html_email(email_data, name)

    return {
        "subject": email_data["subject"],
        "html_body": html_body,
        "quote": email_data.get("quote", ""),
        "source": email_data.get("quote_source", ""),
    }


def build_html_email(data: dict, name: str) -> str:
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
              — {data['quote_source']}
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
            Sent with care from <a href="https://zombielabsv2.github.io/lotus-lane/" style="color:#c0392b; text-decoration:none;">The Lotus Lane</a>
          </p>
          <p style="margin:8px 0 0; font-size:11px; color:#bbb;">
            You received this because you signed up for Daimoku Daily.
            <br>No longer want these? Simply reply with "unsubscribe".
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
    """Send an email via Gmail SMTP."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print(f"  [SKIP] Gmail creds not set — would send to {to_email}")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"Daimoku Daily <{GMAIL_ADDRESS}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    # Plain text fallback
    plain_text = re.sub(r"<[^>]+>", "", html_body)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        return True
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


def main():
    """Main entry point — process all due subscribers."""
    print(f"=== Daimoku Daily — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")

    # Validate configuration
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_KEY:
        missing.append("SUPABASE_SERVICE_KEY")
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not GMAIL_ADDRESS:
        missing.append("GMAIL_ADDRESS")
    if not GMAIL_APP_PASSWORD:
        missing.append("GMAIL_APP_PASSWORD")

    if missing:
        print(f"  [FATAL] Missing environment variables: {', '.join(missing)}")
        return

    # Get due subscribers
    due = get_due_subscribers()
    print(f"\nDue subscribers: {len(due)}")

    if not due:
        print("No subscribers due for email today.")
        return

    # Process each subscriber
    sent_count = 0
    fail_count = 0

    for sub in due:
        try:
            success = process_subscriber(sub)
            if success:
                sent_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"  [ERROR] Unhandled error for {sub.get('email', '?')}: {e}")
            fail_count += 1

    print(f"\n=== Done: {sent_count} sent, {fail_count} failed ===")


if __name__ == "__main__":
    main()
