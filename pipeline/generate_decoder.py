#!/usr/bin/env python3
"""
Gosho Decoder — Static page generator for Nichiren Buddhist writings.

Reads chunks from the Nichiren chatbot knowledge base, sends them to Claude
for plain-English explanation, and generates SEO-optimized static HTML pages.

Usage:
    python pipeline/generate_decoder.py                  # Generate top 50 writings
    python pipeline/generate_decoder.py --limit 10       # Generate top 10 only
    python pipeline/generate_decoder.py --slug opening-of-the-eyes  # One specific writing
    python pipeline/generate_decoder.py --index-only     # Regenerate index.html only
    python pipeline/generate_decoder.py --force           # Regenerate even if cached
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ----- Paths -----
PROJECT_ROOT = Path(__file__).parent.parent
DECODER_DIR = PROJECT_ROOT / "decoder"
CACHE_DIR = DECODER_DIR / "cache"
CHUNKS_PATH = Path.home() / "nichiren-chatbot" / "data" / "processed" / "chunks.json"

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ----- Constants -----
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
INPUT_COST_PER_M = 3.0   # Sonnet input $/M tokens
OUTPUT_COST_PER_M = 15.0  # Sonnet output $/M tokens

# Themes for tagging
THEME_KEYWORDS = {
    "faith": ["faith", "believe", "devotion", "practice", "daimoku", "nam-myoho-renge-kyo", "gongyo"],
    "perseverance": ["persevere", "never give up", "endure", "hardship", "difficulty", "struggle", "obstacle"],
    "courage": ["courage", "brave", "fearless", "lion", "roar", "fight", "stand up"],
    "karma": ["karma", "cause and effect", "destiny", "retribution", "past lives", "consequences"],
    "compassion": ["compassion", "mercy", "kindness", "benefit others", "bodhisattva", "save"],
    "wisdom": ["wisdom", "enlighten", "understand", "truth", "insight", "awaken"],
    "mentor-disciple": ["mentor", "disciple", "teacher", "master", "follow", "guidance"],
    "prayer": ["prayer", "pray", "wish", "determination", "ichinen", "resolve"],
    "protection": ["protect", "guardian", "heavenly gods", "shoten zenjin", "benefit"],
    "human revolution": ["human revolution", "change", "transform", "inner", "revolution", "growth"],
    "correct teaching": ["correct teaching", "true law", "slander", "heresy", "refute", "shakubuku"],
    "lotus sutra": ["lotus sutra", "mystic law", "wonderful law", "myoho-renge-kyo"],
    "women": ["woman", "women", "daughter", "wife", "mother", "female", "dragon king"],
    "illness": ["illness", "sick", "disease", "medicine", "heal", "cure", "health"],
    "death": ["death", "die", "afterlife", "eagle peak", "deceased", "passing"],
}


def slugify(title: str) -> str:
    """Convert a writing title to a URL-friendly slug."""
    # Clean up title artifacts (line breaks embedded in scraped titles)
    title = re.sub(r'\s+', ' ', title).strip()
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug).strip('-')
    slug = re.sub(r'-+', '-', slug)
    # Truncate to reasonable length
    if len(slug) > 80:
        slug = slug[:80].rsplit('-', 1)[0]
    return slug


def clean_title(title: str) -> str:
    """Clean up title artifacts from scraping (extra spaces, concatenated words).

    The scraper sometimes stripped line breaks joining words together, e.g.:
    "theLotus" "Teachingsof" "Existencesregardingthe"
    We fix with a multi-pass approach: first camelCase, then targeted replacements.
    """
    title = re.sub(r'\s+', ' ', title).strip()

    # Pass 1: Split camelCase joins (lowercase immediately followed by Uppercase)
    title = re.sub(r'([a-z])([A-Z])', r'\1 \2', title)

    # Pass 2: Fix long prepositions stuck to surrounding words
    for word in ['regarding', 'through', 'after', 'before', 'during', 'between', 'concerning']:
        # Sandwiched between words: "Existencesregardingthe"
        title = re.sub(rf'([A-Za-z])({word})([A-Za-z])', rf'\1 \2 \3', title, flags=re.IGNORECASE)
        # Stuck to preceding word before space: "Periodafter " -> "Period after "
        title = re.sub(rf'([A-Za-z])({word})(?=\s)', rf'\1 \2', title, flags=re.IGNORECASE)
        # Stuck to following word after space: " throughLotus" -> " through Lotus"
        title = re.sub(rf'(?<=\s)({word})([A-Za-z])', rf'\1 \2', title, flags=re.IGNORECASE)

    # Pass 3: Fix compound joins like "Daimokuofthe", "Faithandthe", "Periodsofthe"
    # Strategy: look for known preposition+article combos stuck to words
    for combo in ['ofthe', 'andthe', 'forthe', 'bythe', 'inthe', 'onthe', 'tothe',
                  'ofan', 'andan', 'foran', 'ofa', 'anda', 'fora']:
        prep = combo[:2] if len(combo) == 5 else combo[:3] if combo.startswith(('for', 'and')) else combo.split('the')[0] if 'the' in combo else combo[:2]
        # Simpler: just split the known combos
        if combo.endswith('the'):
            parts = (combo[:-3], 'the')
        elif combo.endswith('an'):
            parts = (combo[:-2], 'an')
        elif combo.endswith('a') and not combo.endswith('an'):
            parts = (combo[:-1], 'a')
        else:
            continue
        title = title.replace(combo, f'{parts[0]} {parts[1]}')
        title = title.replace(combo.capitalize(), f'{parts[0].capitalize()} {parts[1]}')

    # Pass 4: Fix standalone prepositions stuck to following capital letter
    title = re.sub(r'(?<=\s)(the|of|for|and|by|in|on|to|or|as|at|a|an)([A-Z])', r'\1 \2', title)

    # Pass 5: Fix word ending + preposition before space: "Teachingsof " -> "Teachings of "
    # Use word boundary: must be preceded by 3+ char word to avoid breaking short words
    title = re.sub(r'(\w{3,})(of|and|for)(?=\s)', r'\1 \2', title)

    # Clean double/triple spaces
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def load_chunks():
    """Load all chunks from the knowledge base."""
    print(f"Loading chunks from {CHUNKS_PATH}...")
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def find_top_writings(chunks, limit=50):
    """Find the top N WND writings by chunk count (proxy for length/importance)."""
    wnd_chunks = [c for c in chunks if c["metadata"]["collection"] in ("wnd-1", "wnd-2")]

    # Count chunks per document
    doc_info = {}
    for c in wnd_chunks:
        doc_id = c["metadata"]["doc_id"]
        if doc_id not in doc_info:
            doc_info[doc_id] = {
                "doc_id": doc_id,
                "title": clean_title(c["metadata"]["title"]),
                "collection": c["metadata"]["collection"],
                "url": c["metadata"]["url"],
                "background": c["metadata"].get("background", ""),
                "recipient": c["metadata"].get("recipient", ""),
                "chunk_count": 0,
                "chunks": [],
            }
        doc_info[doc_id]["chunk_count"] += 1
        doc_info[doc_id]["chunks"].append(c)

    # Sort by chunk count (descending) and take top N
    sorted_docs = sorted(doc_info.values(), key=lambda x: x["chunk_count"], reverse=True)
    return sorted_docs[:limit]


def detect_themes(text: str) -> list:
    """Detect themes from text based on keyword matching."""
    text_lower = text.lower()
    found = []
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                found.append(theme)
                break
    return found


def build_claude_prompt(writing):
    """Build the prompt for Claude to analyze a writing."""
    title = writing["title"]
    background = writing.get("background", "")

    # Concatenate chunk texts, sorted by chunk_index
    sorted_chunks = sorted(writing["chunks"], key=lambda c: c["chunk_index"])
    full_text = "\n\n".join(c["text"] for c in sorted_chunks)

    # Truncate if extremely long (keep first ~80k chars to stay within context)
    if len(full_text) > 80000:
        full_text = full_text[:80000] + "\n\n[Text truncated for length]"

    prompt = f"""You are a scholar of Nichiren Buddhism who explains Gosho (Nichiren's writings) in plain, modern English for people new to Buddhism. Your tone is warm, clear, and practical — like a wise friend explaining something meaningful over coffee.

Analyze this writing from Nichiren Daishonin and produce a structured explanation.

WRITING TITLE: {title}

BACKGROUND FROM EDITOR:
{background if background else "(No editorial background available)"}

FULL TEXT OF THE WRITING:
{full_text}

Please provide your analysis in the following JSON format (and ONLY valid JSON, no markdown fencing):
{{
  "background": {{
    "recipient": "Who Nichiren wrote this to (name and brief description)",
    "date_period": "When it was written (year, era, circumstances)",
    "context": "Why he wrote it — what was happening in the recipient's life or in society",
    "significance": "Why this writing is considered important in Nichiren Buddhism"
  }},
  "key_passages": [
    {{
      "quote": "An exact or near-exact quote from the text (2-4 sentences)",
      "explanation": "What this passage means in plain English (3-5 sentences)"
    }}
  ],
  "core_message": "A 3-5 paragraph plain-English explanation of the writing's central teaching. What is Nichiren trying to tell the reader? What principle of life or Buddhism is he illuminating? Write this for someone who has never read Buddhist scripture before.",
  "modern_application": "A 2-3 paragraph section on how this teaching applies to everyday life today. Give specific, relatable examples. How would someone apply this wisdom to their career, relationships, health struggles, or personal growth? Be concrete and practical.",
  "related_themes": ["theme1", "theme2", "theme3"]
}}

Pick 3-5 of the most powerful and meaningful passages as key_passages. For related_themes, choose from: faith, perseverance, courage, karma, compassion, wisdom, mentor-disciple, prayer, protection, human revolution, correct teaching, lotus sutra, women, illness, death."""

    return prompt


def call_claude(prompt: str) -> tuple:
    """Call Claude API and return (response_dict, input_tokens, output_tokens)."""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }

    max_retries = 5
    for attempt in range(max_retries):
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
            timeout=120,
        )
        if resp.status_code == 429:
            wait = min(2 ** attempt * 10, 120)  # 10s, 20s, 40s, 80s, 120s
            print(f"    [RATE LIMITED] Waiting {wait}s before retry {attempt+1}/{max_retries}...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break
    else:
        # All retries exhausted
        resp.raise_for_status()
    data = resp.json()

    text = data["content"][0]["text"]
    input_tokens = data["usage"]["input_tokens"]
    output_tokens = data["usage"]["output_tokens"]

    # Parse JSON from response (handle potential markdown fencing and trailing text)
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```\s*$', '', text)

    # Try direct parse first
    try:
        result = json.loads(text)
        return result, input_tokens, output_tokens
    except json.JSONDecodeError:
        pass

    # Find the outermost JSON object by brace matching
    start = text.index('{')
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                result = json.loads(text[start:i+1])
                return result, input_tokens, output_tokens

    raise ValueError("Could not find valid JSON object in Claude response")


def find_related_writings(current_doc_id, current_themes, all_writings):
    """Find related writings based on shared themes."""
    related = []
    for w in all_writings:
        if w["doc_id"] == current_doc_id:
            continue
        # Detect themes from background and chunk text sample
        sample_text = w.get("background", "") + " " + " ".join(
            c["text"][:200] for c in w["chunks"][:3]
        )
        w_themes = detect_themes(sample_text)
        overlap = set(current_themes) & set(w_themes)
        if overlap:
            related.append({
                "title": w["title"],
                "slug": slugify(w["title"]),
                "shared_themes": list(overlap),
                "overlap_count": len(overlap),
            })
    # Sort by overlap count and return top 5
    related.sort(key=lambda x: x["overlap_count"], reverse=True)
    return related[:5]


def generate_writing_html(writing, analysis, related_writings):
    """Generate the HTML page for a single decoded writing."""
    title = writing["title"]
    slug = slugify(title)
    url = writing["url"]
    collection_name = "WND Volume 1" if writing["collection"] == "wnd-1" else "WND Volume 2"

    bg = analysis["background"]
    key_passages = analysis["key_passages"]
    core_message = analysis["core_message"]
    modern_app = analysis.get("modern_application", "")
    themes = analysis.get("related_themes", [])

    # Build key passages HTML
    passages_html = ""
    for i, p in enumerate(key_passages):
        passages_html += f"""
        <div class="passage">
          <blockquote>"{p['quote']}"</blockquote>
          <p class="passage-explanation">{p['explanation']}</p>
        </div>"""

    # Build themes HTML
    themes_html = "".join(f'<span class="theme-tag">{t.replace("-", " ").title()}</span>' for t in themes)

    # Build related writings HTML
    related_html = ""
    if related_writings:
        related_items = ""
        for r in related_writings:
            shared = ", ".join(t.replace("-", " ").title() for t in r["shared_themes"])
            related_items += f"""
            <li><a href="{r['slug']}.html">{r['title']}</a> <span class="related-themes">({shared})</span></li>"""
        related_html = f"""
        <section class="related-writings">
          <h2>Related Writings</h2>
          <ul>{related_items}
          </ul>
        </section>"""

    # Meta description
    meta_desc = core_message[:155].replace('"', '&quot;')
    if len(core_message) > 155:
        meta_desc = meta_desc[:meta_desc.rfind(' ')] + "..."

    # Convert core message paragraphs
    core_paragraphs = "\n".join(f"        <p>{para.strip()}</p>" for para in core_message.split("\n") if para.strip())

    # Convert modern application paragraphs
    modern_paragraphs = "\n".join(f"        <p>{para.strip()}</p>" for para in modern_app.split("\n") if para.strip())

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Explained in Plain English | Gosho Decoder</title>
  <meta name="description" content="{meta_desc}">
  <meta property="og:title" content="{title} — Plain English Explanation">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:type" content="article">
  <link rel="canonical" href="https://thelotuslane.in/decoder/{slug}.html">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: #faf9f6;
      color: #2d2d2d;
      min-height: 100vh;
      line-height: 1.7;
    }}

    header {{
      text-align: center;
      padding: 1.2rem 1rem 0.8rem;
      border-bottom: 2px solid #e8e4de;
    }}

    header h1 {{
      font-size: 1.4rem;
      font-weight: 300;
      letter-spacing: 0.15em;
      color: #4a4a4a;
    }}

    header h1 a {{
      text-decoration: none;
      color: inherit;
    }}

    header h1 span {{
      font-weight: 600;
      color: #c0392b;
    }}

    header p.tagline {{
      font-size: 0.8rem;
      color: #999;
      margin-top: 0.15rem;
      font-style: italic;
    }}

    nav.breadcrumb {{
      max-width: 780px;
      margin: 1rem auto 0;
      padding: 0 1.5rem;
      font-size: 0.82rem;
      color: #999;
    }}

    nav.breadcrumb a {{
      color: #c0392b;
      text-decoration: none;
    }}

    nav.breadcrumb a:hover {{
      text-decoration: underline;
    }}

    main {{
      max-width: 780px;
      margin: 0 auto;
      padding: 1.5rem 1.5rem 3rem;
    }}

    .writing-header {{
      margin-bottom: 2rem;
    }}

    .writing-header h1 {{
      font-size: 2rem;
      font-weight: 700;
      color: #2d2d2d;
      line-height: 1.3;
      margin-bottom: 0.5rem;
    }}

    .writing-meta {{
      font-size: 0.85rem;
      color: #888;
      margin-bottom: 1rem;
    }}

    .writing-meta a {{
      color: #c0392b;
      text-decoration: none;
    }}

    .theme-tags {{
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
    }}

    .theme-tag {{
      font-size: 0.72rem;
      padding: 0.2rem 0.7rem;
      background: #f0ede8;
      border-radius: 999px;
      color: #666;
    }}

    section {{
      margin-bottom: 2.5rem;
    }}

    section h2 {{
      font-size: 1.35rem;
      font-weight: 600;
      color: #333;
      margin-bottom: 1rem;
      padding-bottom: 0.4rem;
      border-bottom: 2px solid #e8e4de;
    }}

    .background-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }}

    .bg-item {{
      background: #fff;
      border: 1px solid #e8e4de;
      border-radius: 8px;
      padding: 1rem;
    }}

    .bg-item h3 {{
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #999;
      margin-bottom: 0.4rem;
    }}

    .bg-item p {{
      font-size: 0.92rem;
      color: #444;
    }}

    .passage {{
      margin-bottom: 1.8rem;
    }}

    .passage blockquote {{
      padding: 1rem 1.2rem;
      background: #fdf8f0;
      border-left: 3px solid #c0392b;
      font-style: italic;
      font-size: 0.95rem;
      color: #444;
      margin-bottom: 0.6rem;
      line-height: 1.6;
    }}

    .passage-explanation {{
      font-size: 0.92rem;
      color: #555;
      padding-left: 1.2rem;
    }}

    .core-message p, .modern-application p {{
      margin-bottom: 1rem;
      font-size: 0.95rem;
    }}

    .source-link {{
      display: inline-block;
      margin-top: 0.5rem;
      padding: 0.6rem 1.2rem;
      background: #c0392b;
      color: white;
      text-decoration: none;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 500;
      transition: background 0.2s;
    }}

    .source-link:hover {{
      background: #a93226;
    }}

    .related-writings ul {{
      list-style: none;
      padding: 0;
    }}

    .related-writings li {{
      padding: 0.6rem 0;
      border-bottom: 1px solid #f0ede8;
    }}

    .related-writings li:last-child {{
      border-bottom: none;
    }}

    .related-writings a {{
      color: #c0392b;
      text-decoration: none;
      font-weight: 500;
    }}

    .related-writings a:hover {{
      text-decoration: underline;
    }}

    .related-themes {{
      font-size: 0.78rem;
      color: #999;
    }}

    .back-link {{
      display: inline-block;
      margin-top: 2rem;
      font-size: 0.88rem;
      color: #c0392b;
      text-decoration: none;
    }}

    .back-link:hover {{
      text-decoration: underline;
    }}

    footer {{
      text-align: center;
      padding: 1.5rem 1rem;
      font-size: 0.75rem;
      color: #bbb;
      border-top: 1px solid #e8e4de;
    }}

    footer a {{
      color: #c0392b;
      text-decoration: none;
    }}

    @media (max-width: 600px) {{
      main {{ padding: 1rem; }}
      .writing-header h1 {{ font-size: 1.5rem; }}
      .background-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1><a href="https://thelotuslane.in/">The <span>Lotus</span> Lane</a></h1>
    <p class="tagline">Gosho Decoder — Buddhist wisdom in plain English</p>
  </header>

  <nav class="breadcrumb">
    <a href="https://thelotuslane.in/">Home</a> &rsaquo;
    <a href="index.html">Gosho Decoder</a> &rsaquo;
    {title}
  </nav>

  <main>
    <div class="writing-header">
      <h1>{title}</h1>
      <div class="writing-meta">{collection_name} &middot; <a href="{url}" target="_blank" rel="noopener">Read on Nichiren Library &rarr;</a></div>
      <div class="theme-tags">{themes_html}</div>
    </div>

    <section class="background">
      <h2>Background</h2>
      <div class="background-grid">
        <div class="bg-item">
          <h3>Written To</h3>
          <p>{bg['recipient']}</p>
        </div>
        <div class="bg-item">
          <h3>When</h3>
          <p>{bg['date_period']}</p>
        </div>
        <div class="bg-item" style="grid-column: 1 / -1;">
          <h3>Why It Was Written</h3>
          <p>{bg['context']}</p>
        </div>
        <div class="bg-item" style="grid-column: 1 / -1;">
          <h3>Significance</h3>
          <p>{bg['significance']}</p>
        </div>
      </div>
    </section>

    <section class="key-passages">
      <h2>Key Passages</h2>
      {passages_html}
    </section>

    <section class="core-message">
      <h2>What This Writing Is Really Saying</h2>
{core_paragraphs}
    </section>

    <section class="modern-application">
      <h2>How This Applies to Your Life Today</h2>
{modern_paragraphs}
    </section>

    <section class="source">
      <h2>Read the Full Writing</h2>
      <p>This is a simplified explanation. For the complete text, visit the Nichiren Library.</p>
      <a href="{url}" target="_blank" rel="noopener" class="source-link">Read Full Text on Nichiren Library &rarr;</a>
    </section>

    {related_html}

    <a href="index.html" class="back-link">&larr; Back to all decoded writings</a>
  </main>

  <footer>
    <p>Gosho Decoder is part of <a href="https://thelotuslane.in/">The Lotus Lane</a> &mdash; Buddhist wisdom for everyday life</p>
    <p style="margin-top:0.3rem;">Explanations generated with AI assistance. Source texts &copy; Soka Gakkai. <a href="{url}" target="_blank" rel="noopener">Read originals at Nichiren Library</a>.</p>
  </footer>

  <script data-goatcounter="https://zombielabs.goatcounter.com/count"
          async src="//gc.zgo.at/count.js"></script>
</body>
</html>"""
    return html


def generate_index_html(writings_data):
    """Generate the index page listing all decoded writings."""
    # Collect all themes across writings
    all_themes = set()
    for w in writings_data:
        for t in w.get("themes", []):
            all_themes.add(t)
    all_themes = sorted(all_themes)

    # Theme filter buttons
    theme_buttons = '<button class="tag-btn active" onclick="filterByTheme(null)">All</button>\n'
    for t in all_themes:
        label = t.replace("-", " ").title()
        theme_buttons += f'      <button class="tag-btn" data-theme="{t}" onclick="filterByTheme(\'{t}\')">{label}</button>\n'

    # Writing cards
    cards_html = ""
    for w in writings_data:
        themes_data = " ".join(w.get("themes", []))
        themes_tags = "".join(
            f'<span class="card-tag">{t.replace("-", " ").title()}</span>'
            for t in w.get("themes", [])
        )
        collection_label = "WND Vol. 1" if w["collection"] == "wnd-1" else "WND Vol. 2"
        snippet = w.get("snippet", "")

        cards_html += f"""
      <a href="{w['slug']}.html" class="writing-card" data-themes="{themes_data}" data-title="{w['title'].lower()}">
        <div class="card-collection">{collection_label}</div>
        <h3>{w['title']}</h3>
        <p class="card-snippet">{snippet}</p>
        <div class="card-tags">{themes_tags}</div>
      </a>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gosho Decoder — Nichiren's Writings Explained in Plain English | The Lotus Lane</title>
  <meta name="description" content="Plain-English explanations of Nichiren Daishonin's most important writings (Gosho). Understand the key passages, core messages, and how they apply to modern life.">
  <meta property="og:title" content="Gosho Decoder — Nichiren's Writings in Plain English">
  <meta property="og:description" content="Plain-English explanations of the most important Gosho. Key passages, core teachings, and modern applications.">
  <meta property="og:type" content="website">
  <link rel="canonical" href="https://thelotuslane.in/decoder/index.html">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: #faf9f6;
      color: #2d2d2d;
      min-height: 100vh;
    }}

    header {{
      text-align: center;
      padding: 1.5rem 1rem 0.8rem;
      border-bottom: 2px solid #e8e4de;
    }}

    header h1 {{
      font-size: 1.8rem;
      font-weight: 300;
      letter-spacing: 0.15em;
      color: #4a4a4a;
    }}

    header h1 a {{
      text-decoration: none;
      color: inherit;
    }}

    header h1 span {{
      font-weight: 600;
      color: #c0392b;
    }}

    header p.tagline {{
      font-size: 0.85rem;
      color: #999;
      margin-top: 0.2rem;
      font-style: italic;
    }}

    .hero {{
      max-width: 800px;
      margin: 2rem auto 1.5rem;
      padding: 0 1.5rem;
      text-align: center;
    }}

    .hero h2 {{
      font-size: 1.6rem;
      font-weight: 600;
      color: #333;
      margin-bottom: 0.6rem;
    }}

    .hero p {{
      font-size: 0.95rem;
      color: #666;
      line-height: 1.6;
    }}

    .search-bar {{
      max-width: 600px;
      margin: 1.5rem auto 0.5rem;
      padding: 0 1.5rem;
    }}

    .search-bar input {{
      width: 100%;
      padding: 0.7rem 1rem;
      border: 1px solid #d4cfc7;
      border-radius: 8px;
      font-size: 0.95rem;
      background: white;
      outline: none;
      transition: border-color 0.2s;
    }}

    .search-bar input:focus {{
      border-color: #c0392b;
    }}

    .filter-bar {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.4rem;
      flex-wrap: wrap;
      padding: 0.8rem 1.5rem;
      max-width: 900px;
      margin: 0 auto;
    }}

    .filter-bar label {{
      font-size: 0.8rem;
      color: #999;
      font-weight: 500;
    }}

    .tag-btn {{
      padding: 0.25rem 0.7rem;
      border: 1px solid #d4cfc7;
      border-radius: 999px;
      background: white;
      font-size: 0.75rem;
      color: #666;
      cursor: pointer;
      transition: all 0.2s;
    }}

    .tag-btn:hover {{ border-color: #c0392b; color: #c0392b; }}
    .tag-btn.active {{ background: #c0392b; color: white; border-color: #c0392b; }}

    .count-label {{
      text-align: center;
      font-size: 0.82rem;
      color: #999;
      margin: 0.8rem 0;
    }}

    .writings-grid {{
      max-width: 900px;
      margin: 0 auto;
      padding: 0 1.5rem 3rem;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }}

    .writing-card {{
      display: block;
      background: white;
      border: 1px solid #e8e4de;
      border-radius: 8px;
      padding: 1.2rem;
      text-decoration: none;
      color: inherit;
      transition: all 0.2s;
    }}

    .writing-card:hover {{
      border-color: #c0392b;
      box-shadow: 0 2px 12px rgba(192, 57, 43, 0.08);
      transform: translateY(-1px);
    }}

    .writing-card.hidden {{
      display: none;
    }}

    .card-collection {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #999;
      margin-bottom: 0.3rem;
    }}

    .writing-card h3 {{
      font-size: 1rem;
      font-weight: 600;
      color: #333;
      margin-bottom: 0.4rem;
      line-height: 1.3;
    }}

    .card-snippet {{
      font-size: 0.82rem;
      color: #777;
      line-height: 1.5;
      margin-bottom: 0.6rem;
    }}

    .card-tags {{
      display: flex;
      gap: 0.3rem;
      flex-wrap: wrap;
    }}

    .card-tag {{
      font-size: 0.68rem;
      padding: 0.15rem 0.5rem;
      background: #f0ede8;
      border-radius: 999px;
      color: #777;
    }}

    footer {{
      text-align: center;
      padding: 1.5rem 1rem;
      font-size: 0.75rem;
      color: #bbb;
      border-top: 1px solid #e8e4de;
    }}

    footer a {{ color: #c0392b; text-decoration: none; }}

    @media (max-width: 600px) {{
      header h1 {{ font-size: 1.4rem; }}
      .hero h2 {{ font-size: 1.3rem; }}
      .writings-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1><a href="https://thelotuslane.in/">The <span>Lotus</span> Lane</a></h1>
    <p class="tagline">Gosho Decoder — Buddhist wisdom in plain English</p>
  </header>

  <div class="hero">
    <h2>Nichiren's Writings, Decoded</h2>
    <p>Plain-English explanations of the most important Gosho (writings of Nichiren Daishonin). Each page breaks down the background, key passages, core message, and how it applies to your life today.</p>
  </div>

  <div class="search-bar">
    <input type="text" id="searchInput" placeholder="Search writings by title..." oninput="filterCards()">
  </div>

  <div class="filter-bar">
    <label>Themes:</label>
    {theme_buttons}
  </div>

  <div class="count-label" id="countLabel">{len(writings_data)} writings decoded</div>

  <div class="writings-grid" id="writingsGrid">
    {cards_html}
  </div>

  <footer>
    <p>Gosho Decoder is part of <a href="https://thelotuslane.in/">The Lotus Lane</a> &mdash; Buddhist wisdom for everyday life</p>
    <p style="margin-top:0.3rem;">Explanations generated with AI assistance. Source texts &copy; Soka Gakkai. <a href="https://www.nichirenlibrary.org" target="_blank" rel="noopener">Nichiren Library</a>.</p>
  </footer>

  <script data-goatcounter="https://zombielabs.goatcounter.com/count"
          async src="//gc.zgo.at/count.js"></script>

  <script>
    let activeTheme = null;

    function filterByTheme(theme) {{
      activeTheme = theme;
      document.querySelectorAll('.tag-btn').forEach(btn => {{
        btn.classList.toggle('active',
          theme === null ? btn.textContent === 'All' : btn.dataset.theme === theme);
      }});
      filterCards();
    }}

    function filterCards() {{
      const query = document.getElementById('searchInput').value.toLowerCase().trim();
      const cards = document.querySelectorAll('.writing-card');
      let visible = 0;

      cards.forEach(card => {{
        const title = card.dataset.title || '';
        const themes = card.dataset.themes || '';
        const matchesSearch = !query || title.includes(query);
        const matchesTheme = !activeTheme || themes.includes(activeTheme);
        const show = matchesSearch && matchesTheme;
        card.classList.toggle('hidden', !show);
        if (show) visible++;
      }});

      document.getElementById('countLabel').textContent =
        visible + ' writing' + (visible !== 1 ? 's' : '') + ' found';
    }}
  </script>
</body>
</html>"""
    return html


def process_writing(writing, all_writings, force=False):
    """Process a single writing: call Claude (or use cache) and generate HTML."""
    slug = slugify(writing["title"])
    cache_path = CACHE_DIR / f"{slug}.json"
    html_path = DECODER_DIR / f"{slug}.html"

    # Check cache
    if cache_path.exists() and not force:
        print(f"  [CACHED] {writing['title']}")
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        analysis = cached["analysis"]
        themes = analysis.get("related_themes", [])
    else:
        print(f"  [GENERATING] {writing['title']}...")
        prompt = build_claude_prompt(writing)
        analysis, input_tokens, output_tokens = call_claude(prompt)

        # Calculate cost
        cost = (input_tokens / 1_000_000 * INPUT_COST_PER_M) + (output_tokens / 1_000_000 * OUTPUT_COST_PER_M)
        print(f"    Tokens: {input_tokens:,} in / {output_tokens:,} out — ${cost:.4f}")

        # Cache the result
        cached = {
            "slug": slug,
            "title": writing["title"],
            "collection": writing["collection"],
            "url": writing["url"],
            "doc_id": writing["doc_id"],
            "analysis": analysis,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached, f, indent=2, ensure_ascii=False)

        themes = analysis.get("related_themes", [])

        # Rate limit: pause between API calls
        time.sleep(3)

    # Find related writings
    related = find_related_writings(writing["doc_id"], themes, all_writings)

    # Generate HTML
    html = generate_writing_html(writing, analysis, related)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "slug": slug,
        "title": writing["title"],
        "collection": writing["collection"],
        "themes": themes,
        "snippet": analysis.get("core_message", "")[:150].rsplit(" ", 1)[0] + "...",
    }


def main():
    parser = argparse.ArgumentParser(description="Generate Gosho Decoder static pages")
    parser.add_argument("--limit", type=int, default=50, help="Number of writings to process (default: 50)")
    parser.add_argument("--slug", type=str, help="Generate only this specific writing (by slug)")
    parser.add_argument("--index-only", action="store_true", help="Only regenerate index.html from cached data")
    parser.add_argument("--force", action="store_true", help="Regenerate even if cached")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY and not args.index_only:
        print("ERROR: ANTHROPIC_API_KEY not found. Set it in .env or environment.")
        sys.exit(1)

    # Ensure directories exist
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Load chunks and find top writings
    chunks = load_chunks()
    all_writings = find_top_writings(chunks, limit=args.limit)

    if args.index_only:
        # Rebuild index from existing cache files
        print("Rebuilding index from cache...")
        writings_data = []
        for cache_file in sorted(CACHE_DIR.glob("*.json")):
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            analysis = cached["analysis"]
            writings_data.append({
                "slug": cached["slug"],
                "title": cached["title"],
                "collection": cached["collection"],
                "themes": analysis.get("related_themes", []),
                "snippet": analysis.get("core_message", "")[:150].rsplit(" ", 1)[0] + "...",
            })
        index_html = generate_index_html(writings_data)
        with open(DECODER_DIR / "index.html", "w", encoding="utf-8") as f:
            f.write(index_html)
        print(f"Index generated with {len(writings_data)} writings.")
        return

    # Filter by slug if specified
    if args.slug:
        target = [w for w in all_writings if slugify(w["title"]) == args.slug]
        if not target:
            print(f"ERROR: No writing found with slug '{args.slug}'")
            print("Available slugs:")
            for w in all_writings:
                print(f"  {slugify(w['title'])}")
            sys.exit(1)
        all_writings_to_process = target
    else:
        all_writings_to_process = all_writings

    print(f"\nGosho Decoder — Processing {len(all_writings_to_process)} writings")
    print(f"{'=' * 60}\n")

    total_cost = 0
    writings_data = []

    for i, writing in enumerate(all_writings_to_process, 1):
        print(f"[{i}/{len(all_writings_to_process)}] {writing['title']} ({writing['chunk_count']} chunks)")
        try:
            result = process_writing(writing, all_writings, force=args.force)
            writings_data.append(result)

            # Track cost from cache
            cache_path = CACHE_DIR / f"{result['slug']}.json"
            if cache_path.exists():
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                total_cost += cached.get("cost", 0)
        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
            continue

    # Also load any other cached writings not in current batch (for index completeness)
    cached_slugs = {w["slug"] for w in writings_data}
    for cache_file in sorted(CACHE_DIR.glob("*.json")):
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if cached["slug"] not in cached_slugs:
            analysis = cached["analysis"]
            writings_data.append({
                "slug": cached["slug"],
                "title": cached["title"],
                "collection": cached["collection"],
                "themes": analysis.get("related_themes", []),
                "snippet": analysis.get("core_message", "")[:150].rsplit(" ", 1)[0] + "...",
            })

    # Generate index
    print(f"\nGenerating index page with {len(writings_data)} writings...")
    index_html = generate_index_html(writings_data)
    with open(DECODER_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"\n{'=' * 60}")
    print(f"Done! Generated {len(writings_data)} pages.")
    print(f"Total API cost: ${total_cost:.4f}")
    print(f"Output: {DECODER_DIR}/")


if __name__ == "__main__":
    main()
