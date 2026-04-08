#!/usr/bin/env python3
"""
Ikeda Guidance — Static page generator for Daisaku Ikeda's quotes and wisdom.

Reads the curated quotes library (ikeda/quotes.json) and generates SEO-optimized
static HTML pages: one index page + one page per theme.

Usage:
    python pipeline/generate_ikeda_pages.py                # Generate all pages
    python pipeline/generate_ikeda_pages.py --theme courage # One specific theme
    python pipeline/generate_ikeda_pages.py --index-only    # Regenerate index only
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
IKEDA_DIR = PROJECT_ROOT / "ikeda"
QUOTES_JSON = IKEDA_DIR / "quotes.json"
SITE_URL = "https://thelotuslane.in"

# Icon mapping (theme id -> emoji)
ICONS = {
    "courage": "&#x1F6E1;",       # shield
    "hope": "&#x2600;",           # sun
    "human-revolution": "&#x2728;",# sparkles
    "prayer-faith": "&#x1F525;",  # flame
    "mentor-disciple": "&#x1F91D;",# handshake
    "youth": "&#x1F680;",         # rocket
    "dialogue": "&#x1F4AC;",      # speech bubble
    "peace": "&#x1F54A;",         # dove
    "education": "&#x1F4DA;",     # books
    "victory": "&#x1F3C6;",       # trophy
    "compassion": "&#x2764;",     # heart
    "wisdom": "&#x1F4A1;",        # lightbulb
    "friendship": "&#x1F465;",    # people
    "perseverance": "&#x26F0;",   # mountain
    "happiness": "&#x1F60A;",     # smile
    "action": "&#x26A1;",         # bolt
    "women": "&#x1F451;",         # crown
    "health": "&#x1F49A;",        # green heart
    "life-and-death": "&#x267E;", # infinity
    "gratitude": "&#x1F381;",     # gift
    "kosen-rufu": "&#x1F30D;",   # globe
}


def load_quotes():
    with open(QUOTES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_theme_page(theme, all_themes):
    """Generate an individual HTML page for a theme."""
    theme_id = theme["id"]
    name = theme["name"]
    description = theme["description"]
    quotes = theme["quotes"]
    icon = ICONS.get(theme_id, "&#x2728;")
    page_url = f"{SITE_URL}/ikeda/{theme_id}.html"
    total_quotes = len(quotes)

    # Find prev/next themes for navigation
    idx = next((i for i, t in enumerate(all_themes) if t["id"] == theme_id), -1)
    prev_theme = all_themes[idx - 1] if idx > 0 else None
    next_theme = all_themes[idx + 1] if idx < len(all_themes) - 1 else None

    # Build quotes HTML
    quotes_html = ""
    for i, q in enumerate(quotes):
        quotes_html += f"""
    <div class="quote-card" data-index="{i}">
      <blockquote>
        <p>&ldquo;{q['text']}&rdquo;</p>
      </blockquote>
      <div class="quote-meta">
        <span class="quote-source">&mdash; Daisaku Ikeda, <em>{q['source']}</em></span>
      </div>
      <button class="share-btn" onclick="shareQuote({i})" title="Share on WhatsApp">Share</button>
    </div>"""

    nav_html = '<nav class="theme-nav">'
    if prev_theme:
        nav_html += f'<a href="{prev_theme["id"]}.html" class="nav-link">&larr; {prev_theme["name"]}</a>'
    else:
        nav_html += '<span></span>'
    if next_theme:
        nav_html += f'<a href="{next_theme["id"]}.html" class="nav-link">{next_theme["name"]} &rarr;</a>'
    else:
        nav_html += '<span></span>'
    nav_html += '</nav>'

    # Schema.org JSON-LD
    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"Daisaku Ikeda on {name} — Quotes & Guidance",
        "description": description,
        "url": page_url,
        "isPartOf": {
            "@type": "WebSite",
            "name": "The Lotus Lane",
            "url": SITE_URL,
        },
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": total_quotes,
            "itemListElement": [
                {
                    "@type": "Quotation",
                    "text": q["text"],
                    "creator": {"@type": "Person", "name": "Daisaku Ikeda"},
                    "isPartOf": {"@type": "Book", "name": q["source"]},
                    "position": i + 1,
                }
                for i, q in enumerate(quotes[:10])  # First 10 for structured data
            ],
        },
    }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Daisaku Ikeda on {name} — Quotes & Guidance | The Lotus Lane</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="max-image-preview:large">
  <link rel="canonical" href="{page_url}">

  <meta property="og:type" content="article">
  <meta property="og:title" content="Daisaku Ikeda on {name} — Quotes & Guidance">
  <meta property="og:description" content="{description}">
  <meta property="og:url" content="{page_url}">
  <meta property="og:site_name" content="The Lotus Lane">

  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="Daisaku Ikeda on {name} — Quotes & Guidance">
  <meta name="twitter:description" content="{description}">

  <script type="application/ld+json">
{json.dumps(schema, indent=2)}
  </script>

  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #faf9f6; color: #2d2d2d; }}

    header {{
      text-align: center; padding: 1.5rem 1rem 0.8rem;
      border-bottom: 2px solid #e8e4de;
    }}
    header h1 {{ font-size: 1.8rem; font-weight: 300; letter-spacing: 0.15em; color: #4a4a4a; }}
    header h1 a {{ text-decoration: none; color: inherit; }}
    header h1 span {{ font-weight: 600; color: #c0392b; }}
    header .breadcrumb {{
      font-size: 0.8rem; color: #999; margin-top: 0.3rem;
    }}
    header .breadcrumb a {{ color: #c0392b; text-decoration: none; }}

    .hero {{
      max-width: 800px; margin: 2rem auto 1.5rem; padding: 0 1.5rem; text-align: center;
    }}
    .hero .icon {{ font-size: 2.5rem; margin-bottom: 0.5rem; }}
    .hero h2 {{ font-size: 1.6rem; font-weight: 600; color: #333; margin-bottom: 0.5rem; }}
    .hero p {{ font-size: 0.95rem; color: #666; line-height: 1.6; }}
    .hero .count {{ font-size: 0.8rem; color: #aaa; margin-top: 0.5rem; }}

    .quotes-grid {{
      max-width: 800px; margin: 0 auto; padding: 0 1.5rem 2rem;
    }}

    .quote-card {{
      background: white; border-radius: 12px; padding: 1.5rem;
      box-shadow: 0 2px 12px rgba(0,0,0,0.05);
      margin-bottom: 1rem; position: relative;
      border-left: 4px solid #c0392b;
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .quote-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }}

    .quote-card blockquote p {{
      font-size: 1.05rem; line-height: 1.7; color: #333;
      font-style: italic;
    }}

    .quote-meta {{
      margin-top: 0.8rem; display: flex; justify-content: space-between;
      align-items: center; flex-wrap: wrap; gap: 0.5rem;
    }}
    .quote-source {{ font-size: 0.82rem; color: #999; }}

    .share-btn {{
      padding: 0.3rem 0.8rem; border: 1px solid #d4cfc7;
      border-radius: 6px; background: white; font-size: 0.75rem;
      color: #666; cursor: pointer; transition: all 0.2s;
    }}
    .share-btn:hover {{ border-color: #25D366; color: #25D366; }}

    .theme-nav {{
      max-width: 800px; margin: 0 auto; padding: 1rem 1.5rem 2rem;
      display: flex; justify-content: space-between;
      border-top: 1px solid #e8e4de;
    }}
    .nav-link {{ color: #c0392b; text-decoration: none; font-size: 0.9rem; }}
    .nav-link:hover {{ text-decoration: underline; }}

    .cta {{
      max-width: 800px; margin: 0 auto 2rem; padding: 0 1.5rem;
    }}
    .cta-box {{
      background: white; border-radius: 12px; padding: 1.5rem;
      text-align: center; box-shadow: 0 2px 12px rgba(0,0,0,0.05);
      border: 1.5px solid #e8e4de;
    }}
    .cta-box a {{ color: #c0392b; text-decoration: none; font-weight: 600; }}

    footer {{
      text-align: center; padding: 1rem; font-size: 0.75rem; color: #bbb;
      border-top: 1px solid #e8e4de;
    }}
    footer a {{ color: #c0392b; text-decoration: none; }}

    @media (max-width: 600px) {{
      .hero h2 {{ font-size: 1.3rem; }}
      .quote-card {{ padding: 1rem; }}
      .quote-card blockquote p {{ font-size: 0.95rem; }}
    }}
  </style>

  <script data-goatcounter="https://zombielabs.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body>
  <header>
    <h1><a href="../">The <span>Lotus</span> Lane</a></h1>
    <div class="breadcrumb">
      <a href="../">Home</a> &rsaquo;
      <a href="index.html">Ikeda Guidance</a> &rsaquo;
      {name}
    </div>
  </header>

  <nav style="display:flex; justify-content:center; gap:1.2rem; padding:0.6rem 1rem; background:#f5f2ed; font-size:0.8rem; flex-wrap:wrap;">
    <a href="../" style="color:#555; text-decoration:none;">Comic Strips</a>
    <a href="index.html" style="color:#c0392b; text-decoration:none; font-weight:600;">Ikeda Guidance</a>
    <a href="../decoder/index.html" style="color:#555; text-decoration:none;">Gosho Decoder</a>
    <a href="../subscribe.html" style="color:#555; text-decoration:none;">Daimoku Daily</a>
  </nav>

  <div class="hero">
    <div class="icon">{icon}</div>
    <h2>Daisaku Ikeda on {name}</h2>
    <p>{description}</p>
    <div class="count">{total_quotes} quotes</div>
  </div>

  <div class="quotes-grid">
    {quotes_html}
  </div>

  {nav_html}

  <div class="cta">
    <div class="cta-box">
      <p style="font-size:0.95rem; color:#333; margin-bottom:0.3rem;">Want daily Buddhist wisdom in your inbox?</p>
      <p><a href="../subscribe.html">Subscribe to Daimoku Daily &rarr;</a></p>
    </div>
  </div>

  <footer>
    <p>Quotes by Daisaku Ikeda &middot; Curated by <a href="../">The Lotus Lane</a></p>
    <p style="margin-top:0.3rem;">
      <a href="index.html">All Topics</a> &middot;
      <a href="../decoder/index.html">Gosho Decoder</a> &middot;
      <a href="../subscribe.html">Daimoku Daily</a>
    </p>
  </footer>

  <script>
    const quotes = {json.dumps([q['text'] for q in quotes])};
    const sources = {json.dumps([q['source'] for q in quotes])};
    const themeName = "{name}";

    function shareQuote(idx) {{
      const text = `*"${{quotes[idx]}}"*\\n\\n— Daisaku Ikeda, ${{sources[idx]}}\\n\\nMore wisdom on ${{themeName}}:\\n{page_url}`;
      window.open(`https://wa.me/?text=${{encodeURIComponent(text)}}`, '_blank');
    }}
  </script>
</body>
</html>"""
    return html


def generate_index_page(data):
    """Generate the main Ikeda Guidance index page."""
    themes = data["themes"]
    total = sum(len(t["quotes"]) for t in themes)

    # Build theme cards
    cards_html = ""
    for t in themes:
        icon = ICONS.get(t["id"], "&#x2728;")
        count = len(t["quotes"])
        # Pick a featured quote (first one)
        featured = t["quotes"][0]["text"]
        if len(featured) > 120:
            featured = featured[:117] + "..."

        cards_html += f"""
    <a href="{t['id']}.html" class="theme-card">
      <div class="card-icon">{icon}</div>
      <h3>{t['name']}</h3>
      <p class="card-desc">{t['description'][:100]}{'...' if len(t['description']) > 100 else ''}</p>
      <p class="card-quote">&ldquo;{featured}&rdquo;</p>
      <span class="card-count">{count} quotes &rarr;</span>
    </a>"""

    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Daisaku Ikeda Guidance — Quotes & Wisdom for Life",
        "description": f"Explore {total} curated quotes and guidance from Daisaku Ikeda across {len(themes)} life themes. Buddhist wisdom for courage, hope, peace, and daily life.",
        "url": f"{SITE_URL}/ikeda/index.html",
        "isPartOf": {"@type": "WebSite", "name": "The Lotus Lane", "url": SITE_URL},
    }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Daisaku Ikeda Guidance — Quotes & Wisdom for Life | The Lotus Lane</title>
  <meta name="description" content="Explore {total} curated quotes and guidance from Daisaku Ikeda across {len(themes)} life themes. Buddhist wisdom for courage, hope, peace, and daily life.">
  <meta name="robots" content="max-image-preview:large">
  <link rel="canonical" href="{SITE_URL}/ikeda/index.html">

  <meta property="og:type" content="website">
  <meta property="og:title" content="Daisaku Ikeda Guidance — Quotes & Wisdom for Life">
  <meta property="og:description" content="Explore {total} curated quotes from Ikeda Sensei across {len(themes)} life themes. Buddhist wisdom for everyday life.">
  <meta property="og:url" content="{SITE_URL}/ikeda/index.html">
  <meta property="og:site_name" content="The Lotus Lane">

  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="Daisaku Ikeda Guidance — Quotes & Wisdom for Life">
  <meta name="twitter:description" content="Explore {total} curated quotes from Ikeda Sensei across {len(themes)} life themes.">

  <script type="application/ld+json">
{json.dumps(schema, indent=2)}
  </script>

  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #faf9f6; color: #2d2d2d; }}

    header {{
      text-align: center; padding: 1.5rem 1rem 0.8rem;
      border-bottom: 2px solid #e8e4de;
    }}
    header h1 {{ font-size: 1.8rem; font-weight: 300; letter-spacing: 0.15em; color: #4a4a4a; }}
    header h1 a {{ text-decoration: none; color: inherit; }}
    header h1 span {{ font-weight: 600; color: #c0392b; }}
    header p.tagline {{ font-size: 0.85rem; color: #999; margin-top: 0.2rem; font-style: italic; }}

    .hero {{
      max-width: 800px; margin: 2rem auto 1rem; padding: 0 1.5rem; text-align: center;
    }}
    .hero h2 {{ font-size: 1.6rem; font-weight: 600; color: #333; margin-bottom: 0.6rem; }}
    .hero p {{ font-size: 0.95rem; color: #666; line-height: 1.6; }}
    .hero .stats {{
      display: flex; justify-content: center; gap: 2rem; margin-top: 1rem;
    }}
    .hero .stat {{
      text-align: center;
    }}
    .hero .stat-number {{
      font-size: 1.6rem; font-weight: 700; color: #c0392b;
    }}
    .hero .stat-label {{
      font-size: 0.75rem; color: #999; text-transform: uppercase; letter-spacing: 0.05em;
    }}

    .search-bar {{
      max-width: 600px; margin: 1.5rem auto 0.5rem; padding: 0 1.5rem;
    }}
    .search-bar input {{
      width: 100%; padding: 0.7rem 1rem;
      border: 1px solid #d4cfc7; border-radius: 8px;
      font-size: 0.9rem; outline: none; background: white;
    }}
    .search-bar input:focus {{ border-color: #c0392b; }}

    .themes-grid {{
      max-width: 900px; margin: 1.5rem auto; padding: 0 1.5rem;
      display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1rem;
    }}

    .theme-card {{
      display: block; text-decoration: none; color: inherit;
      background: white; border-radius: 12px; padding: 1.2rem;
      box-shadow: 0 2px 12px rgba(0,0,0,0.05);
      border: 1.5px solid transparent;
      transition: all 0.2s;
    }}
    .theme-card:hover {{
      border-color: #c0392b;
      transform: translateY(-2px);
      box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }}

    .card-icon {{ font-size: 1.8rem; margin-bottom: 0.4rem; }}
    .theme-card h3 {{ font-size: 1.1rem; color: #333; margin-bottom: 0.3rem; }}
    .card-desc {{ font-size: 0.8rem; color: #888; line-height: 1.4; margin-bottom: 0.6rem; }}
    .card-quote {{
      font-size: 0.82rem; color: #555; font-style: italic; line-height: 1.4;
      padding: 0.5rem; background: #fdf8f0; border-radius: 6px;
      border-left: 3px solid #c0392b; margin-bottom: 0.6rem;
    }}
    .card-count {{
      font-size: 0.75rem; color: #c0392b; font-weight: 600;
    }}

    .cta {{
      max-width: 900px; margin: 2rem auto; padding: 0 1.5rem;
      display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;
    }}
    .cta-box {{
      background: white; border-radius: 12px; padding: 1.2rem;
      text-align: center; box-shadow: 0 2px 12px rgba(0,0,0,0.05);
      border: 1.5px solid #e8e4de; text-decoration: none; color: inherit;
      transition: border-color 0.2s;
    }}
    .cta-box:hover {{ border-color: #c0392b; }}
    .cta-box .cta-icon {{ font-size: 1.5rem; margin-bottom: 0.3rem; }}
    .cta-box .cta-title {{ font-size: 0.95rem; font-weight: 600; color: #333; }}
    .cta-box .cta-desc {{ font-size: 0.8rem; color: #777; margin-top: 0.2rem; }}

    footer {{
      text-align: center; padding: 1.5rem 1rem; font-size: 0.75rem; color: #bbb;
      border-top: 1px solid #e8e4de; margin-top: 1rem;
    }}
    footer a {{ color: #c0392b; text-decoration: none; }}

    @media (max-width: 600px) {{
      .hero h2 {{ font-size: 1.3rem; }}
      .themes-grid {{ grid-template-columns: 1fr; }}
      .cta {{ grid-template-columns: 1fr; }}
      .hero .stats {{ gap: 1rem; }}
    }}
  </style>

  <script data-goatcounter="https://zombielabs.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body>
  <header>
    <h1><a href="../">The <span>Lotus</span> Lane</a></h1>
    <p class="tagline">Buddhist wisdom for everyday struggles</p>
  </header>

  <nav style="display:flex; justify-content:center; gap:1.2rem; padding:0.6rem 1rem; background:#f5f2ed; font-size:0.8rem; flex-wrap:wrap;">
    <a href="../" style="color:#555; text-decoration:none;">Comic Strips</a>
    <a href="index.html" style="color:#c0392b; text-decoration:none; font-weight:600;">Ikeda Guidance</a>
    <a href="../decoder/index.html" style="color:#555; text-decoration:none;">Gosho Decoder</a>
    <a href="../subscribe.html" style="color:#555; text-decoration:none;">Daimoku Daily</a>
  </nav>

  <div class="hero">
    <h2>Guidance from Daisaku Ikeda</h2>
    <p>
      Explore the wisdom of SGI President Daisaku Ikeda &mdash; a lifetime of guidance
      on courage, hope, peace, and the limitless potential within every human life.
    </p>
    <div class="stats">
      <div class="stat">
        <div class="stat-number">{total}</div>
        <div class="stat-label">Quotes</div>
      </div>
      <div class="stat">
        <div class="stat-number">{len(themes)}</div>
        <div class="stat-label">Themes</div>
      </div>
    </div>
  </div>

  <div class="search-bar">
    <input type="text" id="search" placeholder="Search quotes by keyword..." oninput="filterThemes(this.value)">
  </div>

  <div class="themes-grid" id="themesGrid">
    {cards_html}
  </div>

  <div class="cta">
    <a href="../decoder/index.html" class="cta-box">
      <div class="cta-icon">&#x1F4DC;</div>
      <div class="cta-title">Gosho Decoder</div>
      <div class="cta-desc">Nichiren's writings in plain English &rarr;</div>
    </a>
    <a href="../subscribe.html" class="cta-box">
      <div class="cta-icon">&#x1F4E7;</div>
      <div class="cta-title">Daimoku Daily</div>
      <div class="cta-desc">Personalized guidance emails &rarr;</div>
    </a>
  </div>

  <footer>
    <p>Quotes by Daisaku Ikeda &middot; Curated by <a href="../">The Lotus Lane</a></p>
    <p style="margin-top:0.3rem;">
      <a href="../">Comic Strips</a> &middot;
      <a href="../decoder/index.html">Gosho Decoder</a> &middot;
      <a href="../subscribe.html">Daimoku Daily</a>
    </p>
  </footer>

  <script>
    function filterThemes(query) {{
      const cards = document.querySelectorAll('.theme-card');
      const q = query.toLowerCase().trim();
      cards.forEach(card => {{
        const text = card.textContent.toLowerCase();
        card.style.display = !q || text.includes(q) ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate Ikeda Guidance HTML pages")
    parser.add_argument("--theme", help="Generate page for a specific theme only")
    parser.add_argument("--index-only", action="store_true", help="Regenerate index only")
    args = parser.parse_args()

    if not QUOTES_JSON.exists():
        print(f"Quotes file not found: {QUOTES_JSON}")
        sys.exit(1)

    data = load_quotes()
    themes = data["themes"]
    IKEDA_DIR.mkdir(parents=True, exist_ok=True)

    if args.index_only:
        html = generate_index_page(data)
        out = IKEDA_DIR / "index.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Generated {out}")
        return

    if args.theme:
        theme = next((t for t in themes if t["id"] == args.theme), None)
        if not theme:
            print(f"Theme not found: {args.theme}")
            print(f"Available: {', '.join(t['id'] for t in themes)}")
            sys.exit(1)
        html = generate_theme_page(theme, themes)
        out = IKEDA_DIR / f"{args.theme}.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Generated {out}")
    else:
        # Generate all theme pages
        count = 0
        for theme in themes:
            html = generate_theme_page(theme, themes)
            out = IKEDA_DIR / f"{theme['id']}.html"
            with open(out, "w", encoding="utf-8") as f:
                f.write(html)
            count += 1
        print(f"  Generated {count} theme pages")

    # Always regenerate index
    html = generate_index_page(data)
    out = IKEDA_DIR / "index.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Generated index page")
    print(f"  Total: {sum(len(t['quotes']) for t in themes)} quotes across {len(themes)} themes")


if __name__ == "__main__":
    main()
