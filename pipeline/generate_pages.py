#!/usr/bin/env python3
"""
Generate individual HTML pages for each comic strip.

Creates SEO-optimized pages at /strips/{date}.html with:
- Schema.org Article markup (JSON-LD)
- Open Graph + Twitter Card meta tags
- Google Discover optimization (max-image-preview:large)
- Full-width strip image with alt text
- Nichiren quote, message, and navigation

Also regenerates sitemap.xml to include all strip pages.

Usage:
    python pipeline/generate_pages.py          # Generate all pages
    python pipeline/generate_pages.py --date 2026-04-04  # Single page
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import ASSETS_BASE_URL

PROJECT_ROOT = Path(__file__).parent.parent
STRIPS_JSON = PROJECT_ROOT / "strips.json"
STRIPS_DIR = PROJECT_ROOT / "strips"
SITE_URL = "https://thelotuslane.in"


def load_strips():
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_strip_page(strip, all_strips):
    """Generate an individual HTML page for a strip."""
    date = strip["date"]
    title = strip.get("title", "The Lotus Lane")
    message = strip.get("message", "")
    quote = strip.get("quote", "")
    source = strip.get("source", "")
    category = strip.get("category", "")
    tags = strip.get("tags", [])
    image_url = f"{ASSETS_BASE_URL}/{date}.png"
    page_url = f"{SITE_URL}/strips/{date}.html"
    youtube_id = strip.get("youtube_id", "")

    # Find prev/next strips for navigation
    idx = next((i for i, s in enumerate(all_strips) if s["date"] == date), -1)
    prev_strip = all_strips[idx - 1] if idx > 0 else None
    next_strip = all_strips[idx + 1] if idx < len(all_strips) - 1 else None

    # Format date for display
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        display_date = dt.strftime("%B %d, %Y")
    except ValueError:
        display_date = date

    # SEO description: use seo_description if available, otherwise build problem-first one
    seo_desc = strip.get("seo_description", "")
    if not seo_desc:
        topic = strip.get("topic", category.replace("-", " "))
        seo_desc = f"Struggling with {topic}? {message}" if topic else message
    # Trim to 160 chars for meta description
    if len(seo_desc) > 160:
        seo_desc = seo_desc[:157] + "..."

    # Schema.org JSON-LD
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "image": image_url,
        "datePublished": date,
        "dateModified": date,
        "description": seo_desc,
        "author": {"@type": "Organization", "name": "The Lotus Lane"},
        "publisher": {
            "@type": "Organization",
            "name": "The Lotus Lane",
            "logo": {"@type": "ImageObject", "url": f"{SITE_URL}/favicon.ico"},
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
    }

    nav_html = ""
    if prev_strip:
        nav_html += f'<a href="{prev_strip["date"]}.html" class="nav-link">&larr; {prev_strip["title"]}</a>'
    if next_strip:
        nav_html += f'<a href="{next_strip["date"]}.html" class="nav-link">{next_strip["title"]} &rarr;</a>'

    quote_html = ""
    if quote:
        quote_html = f"""
    <blockquote class="quote">
      <p>&ldquo;{quote}&rdquo;</p>
      <cite>- {source or 'Nichiren Daishonin'}</cite>
    </blockquote>"""

    youtube_html = ""
    if youtube_id:
        youtube_html = f"""
    <div class="video-section">
      <h3>Watch the animated version</h3>
      <iframe src="https://www.youtube.com/embed/{youtube_id}"
              width="315" height="560" frameborder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope"
              allowfullscreen loading="lazy"></iframe>
    </div>"""

    tags_html = "".join(f'<span class="tag">{t}</span>' for t in tags)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | The Lotus Lane</title>
  <meta name="description" content="{seo_desc}">
  <meta name="robots" content="max-image-preview:large">
  <link rel="canonical" href="{page_url}">

  <!-- Open Graph -->
  <meta property="og:type" content="article">
  <meta property="og:title" content="{title} | The Lotus Lane">
  <meta property="og:description" content="{seo_desc}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:image:width" content="1024">
  <meta property="og:image:height" content="3500">
  <meta property="og:url" content="{page_url}">
  <meta property="og:site_name" content="The Lotus Lane">
  <meta property="article:published_time" content="{date}">
  <meta property="article:tag" content="{', '.join(tags)}">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title} | The Lotus Lane">
  <meta name="twitter:description" content="{seo_desc}">
  <meta name="twitter:image" content="{image_url}">

  <!-- Schema.org JSON-LD -->
  <script type="application/ld+json">
{json.dumps(schema, indent=2)}
  </script>

  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #faf9f6; color: #2d2d2d; }}
    .container {{ max-width: 700px; margin: 0 auto; padding: 1rem; }}
    header {{ text-align: center; padding: 1.2rem 0; border-bottom: 2px solid #e8e4de; }}
    header a {{ text-decoration: none; color: inherit; }}
    header h1 {{ font-size: 1.5rem; font-weight: 300; letter-spacing: 0.15em; color: #4a4a4a; }}
    header h1 span {{ font-weight: 600; color: #c0392b; }}
    .strip-header {{ padding: 1.5rem 0 0.5rem; }}
    .strip-header h2 {{ font-size: 1.4rem; color: #333; margin-bottom: 0.3rem; }}
    .strip-header .date {{ font-size: 0.85rem; color: #999; }}
    .strip-image {{ width: 100%; border-radius: 4px; margin: 1rem 0; }}
    .message {{ font-size: 1.05rem; line-height: 1.6; color: #444; padding: 0.5rem 0 1rem; }}
    .quote {{ border-left: 3px solid #c0392b; padding: 0.8rem 1.2rem; margin: 1rem 0; background: #f5f3ee; border-radius: 0 4px 4px 0; }}
    .quote p {{ font-style: italic; color: #504638; line-height: 1.5; font-size: 1rem; }}
    .quote cite {{ display: block; margin-top: 0.5rem; font-size: 0.85rem; color: #8c8278; font-style: normal; }}
    .tags {{ padding: 0.5rem 0; }}
    .tag {{ display: inline-block; background: #eee; color: #666; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem; margin: 0.2rem; }}
    .nav {{ display: flex; justify-content: space-between; padding: 1.5rem 0; border-top: 1px solid #e8e4de; margin-top: 1rem; }}
    .nav-link {{ color: #c0392b; text-decoration: none; font-size: 0.9rem; max-width: 45%; }}
    .nav-link:hover {{ text-decoration: underline; }}
    .video-section {{ text-align: center; margin: 1.5rem 0; }}
    .video-section h3 {{ font-size: 1rem; color: #666; margin-bottom: 0.8rem; font-weight: 400; }}
    .subscribe {{ text-align: center; padding: 1.5rem; background: #f0ece4; border-radius: 8px; margin: 1.5rem 0; }}
    .subscribe a {{ color: #c0392b; font-weight: 600; }}
    footer {{ text-align: center; padding: 1rem 0; color: #aaa; font-size: 0.8rem; border-top: 1px solid #e8e4de; margin-top: 1rem; }}
  </style>

  <script data-goatcounter="https://zombielabs.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body>
  <div class="container">
    <header>
      <a href="../"><h1>THE <span>LOTUS</span> LANE</h1></a>
    </header>

    <div class="strip-header">
      <h2>{title}</h2>
      <div class="date">{display_date} &middot; {category.replace('-', ' ').title()}</div>
    </div>

    <img src="{image_url}" alt="{title} - a story about {strip.get('topic', category.replace('-', ' '))}"
         class="strip-image" loading="eager" width="1024">

    <p class="message">{message}</p>

    {quote_html}

    <div class="tags">{tags_html}</div>

    {youtube_html}

    <div class="subscribe">
      <p>Get wisdom for your struggles, delivered to your inbox</p>
      <p><a href="../subscribe.html">Subscribe to The Daily Lotus &rarr;</a></p>
    </div>

    <nav class="nav">{nav_html}</nav>

    <footer>
      <p>The Lotus Lane &middot; Wisdom for everyday struggles</p>
      <p>New strips every Monday, Wednesday, Friday</p>
    </footer>
  </div>
  <script src="../nav.js" defer></script>
</body>
</html>"""
    return html


def generate_sitemap(strips):
    """Regenerate sitemap.xml including all strip pages and decoder pages."""
    urls = [
        (f"{SITE_URL}/", "weekly", "1.0"),
        (f"{SITE_URL}/subscribe.html", "monthly", "0.6"),
    ]

    # Strip pages
    for s in strips:
        urls.append((f"{SITE_URL}/strips/{s['date']}.html", "monthly", "0.8"))

    # Decoder pages (check what exists)
    decoder_dir = PROJECT_ROOT / "decoder"
    if decoder_dir.exists():
        for html_file in sorted(decoder_dir.glob("*.html")):
            urls.append((f"{SITE_URL}/decoder/{html_file.name}", "monthly", "0.7"))

    # Ikeda Guidance pages
    ikeda_dir = PROJECT_ROOT / "ikeda"
    if ikeda_dir.exists():
        for html_file in sorted(ikeda_dir.glob("*.html")):
            urls.append((f"{SITE_URL}/ikeda/{html_file.name}", "monthly", "0.7"))

    # Listicle pages
    listicles_dir = PROJECT_ROOT / "listicles"
    if listicles_dir.exists():
        for html_file in sorted(listicles_dir.glob("*.html")):
            urls.append((f"{SITE_URL}/listicles/{html_file.name}", "monthly", "0.7"))

    # Wisdom / affliction pages (high priority — these target universal search terms)
    wisdom_dir = PROJECT_ROOT / "wisdom"
    if wisdom_dir.exists():
        for html_file in sorted(wisdom_dir.glob("*.html")):
            pri = "0.9" if html_file.name == "index.html" else "0.85"
            urls.append((f"{SITE_URL}/wisdom/{html_file.name}", "weekly", pri))

    xml_entries = "\n".join(
        f"  <url>\n    <loc>{url}</loc>\n    <changefreq>{freq}</changefreq>\n    <priority>{pri}</priority>\n  </url>"
        for url, freq, pri in urls
    )

    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{xml_entries}
</urlset>
"""
    with open(PROJECT_ROOT / "sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap)
    print(f"  Updated sitemap.xml ({len(urls)} URLs)")


def generate_rss(strips):
    """Generate an RSS 2.0 feed from strips data."""
    # Sort newest first for the feed
    sorted_strips = sorted(strips, key=lambda s: s["date"], reverse=True)

    items = []
    for s in sorted_strips[:50]:  # Limit to most recent 50 strips
        date = s["date"]
        title = s.get("title", "The Lotus Lane")
        message = s.get("message", "")
        image_url = f"{ASSETS_BASE_URL}/{date}.png"
        page_url = f"{SITE_URL}/strips/{date}.html"

        # Format pubDate as RFC 822
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            pub_date = dt.strftime("%a, %d %b %Y 00:00:00 +0000")
        except ValueError:
            pub_date = date

        # Escape XML special characters
        safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        items.append(f"""    <item>
      <title>{safe_title}</title>
      <link>{page_url}</link>
      <description>{safe_message}</description>
      <pubDate>{pub_date}</pubDate>
      <guid isPermaLink="true">{page_url}</guid>
      <enclosure url="{image_url}" type="image/png" />
    </item>""")

    items_xml = "\n".join(items)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>The Lotus Lane</title>
    <link>{SITE_URL}/</link>
    <description>Buddhist wisdom comic strips for everyday struggles. New strips every Monday, Wednesday, Friday.</description>
    <language>en</language>
    <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml" />
{items_xml}
  </channel>
</rss>
"""
    with open(PROJECT_ROOT / "feed.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"  Updated feed.xml ({len(items)} items)")


def update_og_image(strips):
    """Update OG image meta tags in index.html and subscribe.html to latest strip."""
    sorted_strips = sorted(strips, key=lambda s: s["date"], reverse=True)
    if not sorted_strips:
        return

    latest_date = sorted_strips[0]["date"]
    latest_image_url = f"{ASSETS_BASE_URL}/{latest_date}.png"

    for html_file in ["index.html", "subscribe.html"]:
        filepath = PROJECT_ROOT / html_file
        if not filepath.exists():
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        import re
        # Update og:image (match any previous URL pattern)
        new_content = re.sub(
            r'<meta property="og:image" content="[^"]+\.png">',
            f'<meta property="og:image" content="{latest_image_url}">',
            content,
        )
        # Update twitter:image
        new_content = re.sub(
            r'<meta name="twitter:image" content="[^"]+\.png">',
            f'<meta name="twitter:image" content="{latest_image_url}">',
            new_content,
        )

        if new_content != content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"  Updated OG image in {html_file} to {latest_date}.png")


def main():
    parser = argparse.ArgumentParser(description="Generate individual strip HTML pages for SEO")
    parser.add_argument("--date", help="Generate page for a specific date only")
    args = parser.parse_args()

    strips = load_strips()
    strips.sort(key=lambda s: s["date"])

    if args.date:
        strip = next((s for s in strips if s["date"] == args.date), None)
        if not strip:
            print(f"Strip not found: {args.date}")
            sys.exit(1)
        html = generate_strip_page(strip, strips)
        out_path = STRIPS_DIR / f"{args.date}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Generated {out_path}")
    else:
        count = 0
        for strip in strips:
            html = generate_strip_page(strip, strips)
            out_path = STRIPS_DIR / f"{strip['date']}.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            count += 1
        print(f"  Generated {count} strip pages")

    generate_sitemap(strips)
    generate_rss(strips)
    update_og_image(strips)


if __name__ == "__main__":
    main()
