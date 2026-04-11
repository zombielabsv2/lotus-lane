#!/usr/bin/env python3
"""
Generate SEO landing pages for universal human afflictions.

Each page curates relevant comic strips, Gosho wisdom, and Ikeda quotes
around a specific human struggle (jealousy, grief, burnout, etc.).

These pages target search queries like:
  - "how to deal with jealousy"
  - "feeling like a failure after 30"
  - "when grief won't stop"

Usage:
    python pipeline/generate_affliction_pages.py          # Generate all pages
    python pipeline/generate_affliction_pages.py --slug dealing-with-jealousy
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import AFFLICTION_PAGES, ASSETS_BASE_URL

PROJECT_ROOT = Path(__file__).parent.parent
STRIPS_JSON = PROJECT_ROOT / "strips.json"
IKEDA_QUOTES = PROJECT_ROOT / "ikeda" / "quotes.json"
WISDOM_DIR = PROJECT_ROOT / "wisdom"
SITE_URL = "https://thelotuslane.in"


def load_strips():
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ikeda_quotes():
    if not IKEDA_QUOTES.exists():
        return {}
    with open(IKEDA_QUOTES, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Build theme -> quotes map
    theme_map = {}
    for theme in data.get("themes", []):
        theme_map[theme["id"]] = theme
    return theme_map


def find_relevant_strips(strips, categories):
    """Find strips whose category or tags overlap with the affliction's categories."""
    relevant = []
    for s in strips:
        strip_cats = set([s.get("category", "")] + s.get("tags", []))
        if strip_cats & set(categories):
            relevant.append(s)
    # Sort newest first
    relevant.sort(key=lambda s: s["date"], reverse=True)
    return relevant


def find_relevant_quotes(ikeda_themes, categories):
    """Find Ikeda quotes matching the affliction's theme areas."""
    # Map affliction categories to Ikeda theme IDs
    cat_to_themes = {
        "work-stress": ["courage", "perseverance", "action"],
        "relationships": ["friendship", "compassion", "dialogue"],
        "family": ["compassion", "education", "women"],
        "health": ["health", "life-and-death", "hope"],
        "finances": ["perseverance", "courage", "action"],
        "self-doubt": ["courage", "human-revolution", "youth"],
        "grief-loss": ["life-and-death", "hope", "gratitude"],
        "perseverance": ["perseverance", "victory", "courage"],
        "anger": ["courage", "wisdom", "dialogue"],
        "loneliness": ["friendship", "compassion", "hope"],
        "envy": ["happiness", "human-revolution", "wisdom"],
    }

    theme_ids = set()
    for cat in categories:
        theme_ids.update(cat_to_themes.get(cat, []))

    quotes = []
    for tid in theme_ids:
        theme = ikeda_themes.get(tid)
        if theme:
            for q in theme.get("quotes", [])[:3]:  # Max 3 per theme
                quotes.append({
                    "text": q["text"],
                    "source": q.get("source", ""),
                    "theme": theme.get("name", tid),
                })
    return quotes[:9]  # Max 9 quotes per page


def generate_affliction_page(slug, title, meta_desc, categories, strips, ikeda_themes):
    """Generate a single affliction landing page."""
    relevant_strips = find_relevant_strips(strips, categories)
    relevant_quotes = find_relevant_quotes(ikeda_themes, categories)
    page_url = f"{SITE_URL}/wisdom/{slug}.html"
    now = datetime.now().strftime("%Y-%m-%d")

    # Schema.org
    schema = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": meta_desc,
        "url": page_url,
        "publisher": {"@type": "Organization", "name": "The Lotus Lane"},
        "dateModified": now,
    }

    # Build strip cards HTML
    strips_html = ""
    for s in relevant_strips[:6]:  # Show top 6
        topic = s.get("topic", s.get("category", "").replace("-", " "))
        strips_html += f"""
    <a href="../strips/{s['date']}.html" class="strip-card">
      <img src="{ASSETS_BASE_URL}/{s['date']}.png" alt="{s.get('title', '')}" loading="lazy" width="200">
      <div class="strip-card-info">
        <div class="strip-card-title">{s.get('title', '')}</div>
        <div class="strip-card-topic">{topic}</div>
        <div class="strip-card-message">{s.get('message', '')[:120]}...</div>
      </div>
    </a>"""

    if not strips_html:
        strips_html = '<p class="empty">More stories coming soon.</p>'

    # Build quotes HTML
    quotes_html = ""
    for q in relevant_quotes:
        quotes_html += f"""
    <div class="wisdom-quote">
      <p>&ldquo;{q['text']}&rdquo;</p>
      <cite>&mdash; {q['source']}</cite>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | The Lotus Lane</title>
  <meta name="description" content="{meta_desc}">
  <meta name="robots" content="max-image-preview:large">
  <link rel="canonical" href="{page_url}">

  <meta property="og:type" content="article">
  <meta property="og:title" content="{title} | The Lotus Lane">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:url" content="{page_url}">

  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{title} | The Lotus Lane">
  <meta name="twitter:description" content="{meta_desc}">

  <script type="application/ld+json">
{json.dumps(schema, indent=2)}
  </script>

  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #faf9f6; color: #2d2d2d; }}
    .container {{ max-width: 740px; margin: 0 auto; padding: 1rem; }}
    header {{ text-align: center; padding: 1.2rem 0; border-bottom: 2px solid #e8e4de; }}
    header a {{ text-decoration: none; color: inherit; }}
    header h1 {{ font-size: 1.5rem; font-weight: 300; letter-spacing: 0.15em; color: #4a4a4a; }}
    header h1 span {{ font-weight: 600; color: #c0392b; }}

    .hero {{ padding: 2.5rem 0 1.5rem; text-align: center; }}
    .hero h2 {{ font-size: 1.8rem; font-weight: 500; color: #333; line-height: 1.3; margin-bottom: 0.8rem; }}
    .hero p {{ font-size: 1.05rem; color: #666; line-height: 1.7; max-width: 600px; margin: 0 auto; }}

    .section-title {{ font-size: 1.1rem; font-weight: 600; color: #555; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #e8e4de; }}

    .strip-card {{ display: flex; gap: 1rem; padding: 1rem; background: white; border-radius: 8px; box-shadow: 0 1px 6px rgba(0,0,0,0.05); margin-bottom: 0.8rem; text-decoration: none; color: inherit; transition: box-shadow 0.2s; }}
    .strip-card:hover {{ box-shadow: 0 3px 12px rgba(0,0,0,0.1); }}
    .strip-card img {{ width: 120px; height: 120px; object-fit: cover; border-radius: 6px; flex-shrink: 0; }}
    .strip-card-info {{ flex: 1; min-width: 0; }}
    .strip-card-title {{ font-size: 1rem; font-weight: 600; color: #333; margin-bottom: 0.2rem; }}
    .strip-card-topic {{ font-size: 0.75rem; color: #c0392b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem; }}
    .strip-card-message {{ font-size: 0.85rem; color: #666; line-height: 1.5; }}

    .wisdom-quote {{ border-left: 3px solid #c0392b; padding: 0.8rem 1.2rem; margin: 0.8rem 0; background: #f5f3ee; border-radius: 0 6px 6px 0; }}
    .wisdom-quote p {{ font-style: italic; color: #504638; line-height: 1.6; font-size: 0.95rem; }}
    .wisdom-quote cite {{ display: block; margin-top: 0.4rem; font-size: 0.8rem; color: #8c8278; font-style: normal; }}

    .subscribe-cta {{ text-align: center; padding: 2rem; background: #f0ece4; border-radius: 10px; margin: 2rem 0; }}
    .subscribe-cta h3 {{ font-size: 1.1rem; color: #333; margin-bottom: 0.4rem; }}
    .subscribe-cta p {{ font-size: 0.9rem; color: #666; margin-bottom: 0.8rem; }}
    .subscribe-cta a {{ display: inline-block; padding: 0.7rem 1.5rem; background: #c0392b; color: white; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 0.9rem; }}
    .subscribe-cta a:hover {{ background: #a93226; }}

    .related-links {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1.5rem 0; }}
    .related-links a {{ padding: 0.4rem 0.8rem; background: white; border: 1px solid #d4cfc7; border-radius: 999px; font-size: 0.8rem; color: #666; text-decoration: none; transition: all 0.2s; }}
    .related-links a:hover {{ border-color: #c0392b; color: #c0392b; }}

    .empty {{ color: #999; font-style: italic; padding: 1rem 0; }}
    footer {{ text-align: center; padding: 1.5rem 0; color: #aaa; font-size: 0.8rem; border-top: 1px solid #e8e4de; margin-top: 2rem; }}

    @media (max-width: 600px) {{
      .hero h2 {{ font-size: 1.4rem; }}
      .strip-card {{ flex-direction: column; }}
      .strip-card img {{ width: 100%; height: 180px; }}
    }}
  </style>

  <script data-goatcounter="https://zombielabs.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body>
  <div class="container">
    <header>
      <a href="../"><h1>THE <span>LOTUS</span> LANE</h1></a>
    </header>

    <div class="hero">
      <h2>{title}</h2>
      <p>{meta_desc}</p>
    </div>

    <h3 class="section-title">Stories about this</h3>
    {strips_html}

    <h3 class="section-title">Words that help</h3>
    {quotes_html}

    <div class="subscribe-cta">
      <h3>Going through this right now?</h3>
      <p>Tell us what you're struggling with. We'll send wisdom that actually helps.</p>
      <a href="../subscribe.html">Get personalized wisdom</a>
    </div>

    <h3 class="section-title">More life challenges</h3>
    <div class="related-links" id="relatedLinks"></div>

    <footer>
      <p>The Lotus Lane &middot; Ancient wisdom for modern struggles</p>
    </footer>
  </div>

  <script src="../nav.js" defer></script>
  <script>
    // Populate related affliction links (all except current)
    const pages = {json.dumps({slug: title for slug, (title, _, _) in AFFLICTION_PAGES.items()})};
    const current = '{slug}';
    const container = document.getElementById('relatedLinks');
    Object.entries(pages).forEach(([s, t]) => {{
      if (s !== current) {{
        const a = document.createElement('a');
        a.href = s + '.html';
        a.textContent = t;
        container.appendChild(a);
      }}
    }});
  </script>
</body>
</html>"""
    return html


def generate_index_page():
    """Generate the wisdom/ index page listing all affliction topics."""
    cards_html = ""
    for slug, (title, meta_desc, _) in sorted(AFFLICTION_PAGES.items()):
        cards_html += f"""
    <a href="{slug}.html" class="topic-card">
      <div class="topic-title">{title}</div>
      <div class="topic-desc">{meta_desc[:100]}...</div>
    </a>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Life Challenges — Wisdom for What You're Going Through | The Lotus Lane</title>
  <meta name="description" content="Jealousy, grief, burnout, loneliness, anger, self-doubt — whatever you're going through, ancient wisdom has something to say about it.">
  <meta name="robots" content="max-image-preview:large">
  <link rel="canonical" href="{SITE_URL}/wisdom/">

  <meta property="og:type" content="website">
  <meta property="og:title" content="Life Challenges — The Lotus Lane">
  <meta property="og:description" content="Whatever you're going through, ancient wisdom has something to say about it.">
  <meta property="og:url" content="{SITE_URL}/wisdom/">

  <script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "CollectionPage",
  "name": "Life Challenges",
  "description": "Wisdom for universal human struggles — jealousy, grief, burnout, loneliness, anger, self-doubt.",
  "url": "{SITE_URL}/wisdom/",
  "publisher": {{"@type": "Organization", "name": "The Lotus Lane"}}
}}
  </script>

  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #faf9f6; color: #2d2d2d; }}
    .container {{ max-width: 740px; margin: 0 auto; padding: 1rem; }}
    header {{ text-align: center; padding: 1.2rem 0; border-bottom: 2px solid #e8e4de; }}
    header a {{ text-decoration: none; color: inherit; }}
    header h1 {{ font-size: 1.5rem; font-weight: 300; letter-spacing: 0.15em; color: #4a4a4a; }}
    header h1 span {{ font-weight: 600; color: #c0392b; }}

    .hero {{ text-align: center; padding: 2.5rem 0 1.5rem; }}
    .hero h2 {{ font-size: 1.8rem; font-weight: 400; color: #333; margin-bottom: 0.5rem; }}
    .hero p {{ font-size: 1rem; color: #777; max-width: 520px; margin: 0 auto; line-height: 1.6; }}

    .topics-grid {{ display: grid; grid-template-columns: 1fr; gap: 0.8rem; margin: 1.5rem 0; }}
    .topic-card {{ display: block; padding: 1.2rem 1.5rem; background: white; border-radius: 10px; box-shadow: 0 1px 6px rgba(0,0,0,0.05); text-decoration: none; color: inherit; transition: all 0.2s; border: 1.5px solid transparent; }}
    .topic-card:hover {{ border-color: #c0392b; box-shadow: 0 3px 12px rgba(0,0,0,0.08); }}
    .topic-title {{ font-size: 1.05rem; font-weight: 600; color: #333; margin-bottom: 0.3rem; }}
    .topic-desc {{ font-size: 0.85rem; color: #777; line-height: 1.5; }}

    footer {{ text-align: center; padding: 1.5rem 0; color: #aaa; font-size: 0.8rem; border-top: 1px solid #e8e4de; margin-top: 2rem; }}

    @media (max-width: 600px) {{
      .hero h2 {{ font-size: 1.4rem; }}
    }}
  </style>

  <script data-goatcounter="https://zombielabs.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body>
  <div class="container">
    <header>
      <a href="../"><h1>THE <span>LOTUS</span> LANE</h1></a>
    </header>

    <div class="hero">
      <h2>What are you going through?</h2>
      <p>Pick your struggle. We'll show you stories and wisdom from people who've been there.</p>
    </div>

    <div class="topics-grid">
      {cards_html}
    </div>

    <footer>
      <p>The Lotus Lane &middot; Ancient wisdom for modern struggles</p>
    </footer>
  </div>
  <script src="../nav.js" defer></script>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate affliction SEO landing pages")
    parser.add_argument("--slug", help="Generate a single page by slug")
    args = parser.parse_args()

    WISDOM_DIR.mkdir(parents=True, exist_ok=True)

    strips = load_strips()
    ikeda_themes = load_ikeda_quotes()

    if args.slug:
        if args.slug not in AFFLICTION_PAGES:
            print(f"Unknown slug: {args.slug}")
            print(f"Available: {', '.join(AFFLICTION_PAGES.keys())}")
            sys.exit(1)

        title, meta_desc, categories = AFFLICTION_PAGES[args.slug]
        html = generate_affliction_page(args.slug, title, meta_desc, categories, strips, ikeda_themes)
        out_path = WISDOM_DIR / f"{args.slug}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Generated {out_path}")
    else:
        # Generate all affliction pages
        count = 0
        for slug, (title, meta_desc, categories) in AFFLICTION_PAGES.items():
            html = generate_affliction_page(slug, title, meta_desc, categories, strips, ikeda_themes)
            out_path = WISDOM_DIR / f"{slug}.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            count += 1

        # Generate index page
        index_html = generate_index_page()
        with open(WISDOM_DIR / "index.html", "w", encoding="utf-8") as f:
            f.write(index_html)

        print(f"  Generated {count} affliction pages + index in wisdom/")


if __name__ == "__main__":
    main()
