#!/usr/bin/env python3
"""
The Lotus Lane — Listicle Infographic Generator

Generates listicle-format content like "5 Ikeda Quotes for When You Want to Give Up"
with tall infographic images (Pinterest/Stories) and Instagram carousels.

Cheaper than comic strips — text/typography only via Pillow, one Claude Sonnet call.
Cost: ~Rs. 1-2 per listicle.

Usage:
    python pipeline/generate_listicle.py                     # Today's listicle
    python pipeline/generate_listicle.py --date 2026-04-09   # Specific date
    python pipeline/generate_listicle.py --theme courage     # Force theme
    python pipeline/generate_listicle.py --dry-run            # Claude call only, no images
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUOTES_PATH = PROJECT_ROOT / "ikeda" / "quotes.json"
LISTICLES_DIR = PROJECT_ROOT / "listicles"
LISTICLES_JSON = LISTICLES_DIR / "listicles.json"
FONTS_DIR = Path(__file__).resolve().parent / "fonts"
SITE_URL = "https://thelotuslane.in"

# ---------------------------------------------------------------------------
# Design constants — Tall infographic (9:16, Pinterest/Stories/Reels)
# ---------------------------------------------------------------------------
INFOGRAPHIC_SIZE = (1080, 1920)
CAROUSEL_SIZE = (1080, 1080)

# Colors (matching quote card palette)
BG_TOP = (253, 246, 227)           # #FDF6E3 warm cream
BG_BOTTOM = (245, 230, 200)       # #F5E6C8 golden cream
COLOR_TITLE = (62, 39, 35)        # #3E2723 dark brown
COLOR_QUOTE = (62, 39, 35)        # #3E2723 dark brown
COLOR_EXPLANATION = (93, 64, 55)   # #5D4037 medium brown
COLOR_ATTRIBUTION = (121, 85, 72)  # #795548 lighter brown
COLOR_NUMBER = (191, 140, 64)     # #BF8C40 gold accent
COLOR_BRANDING = (189, 189, 189)  # #BDBDBD light gray
COLOR_SEPARATOR = (210, 185, 150) # subtle warm divider


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font from the fonts directory."""
    path = FONTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Font not found: {path}")
    return ImageFont.truetype(str(path), size)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_quotes() -> dict:
    """Load quotes.json."""
    with open(QUOTES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_listicles() -> list:
    """Load existing listicles metadata."""
    if LISTICLES_JSON.exists():
        with open(LISTICLES_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_listicles(listicles: list) -> None:
    """Save listicles metadata."""
    LISTICLES_DIR.mkdir(parents=True, exist_ok=True)
    with open(LISTICLES_JSON, "w", encoding="utf-8") as f:
        json.dump(listicles, f, indent=2, ensure_ascii=False)


def pick_theme(data: dict, existing_listicles: list, forced_theme: str | None = None) -> dict:
    """
    Pick a theme, rotating through available themes and avoiding recent ones.
    Returns the theme dict.
    """
    themes = data["themes"]

    if forced_theme:
        for t in themes:
            if t["id"] == forced_theme:
                return t
        available = [t["id"] for t in themes]
        raise ValueError(f"Theme '{forced_theme}' not found. Available: {available}")

    # Get recently used themes
    recent_themes = [l.get("theme", "") for l in existing_listicles[-10:]]

    # Pick a theme we haven't used recently
    available = [t for t in themes if t["id"] not in recent_themes]
    if not available:
        available = themes  # All used recently, reset

    # Round-robin: pick the first available theme in the original order
    return available[0]


# ---------------------------------------------------------------------------
# Claude API — Generate listicle content
# ---------------------------------------------------------------------------

def generate_listicle_content(theme: dict, existing_listicles: list) -> dict:
    """
    Use Claude Sonnet to pick best quotes from a theme and write a catchy
    listicle with title + explanations.

    Returns: {title, items: [{quote, source, explanation}], theme}
    """
    import httpx

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    # Send 5-7 quotes from the theme (or all if fewer)
    quotes = theme["quotes"][:7]
    quotes_block = "\n".join(
        f'{i+1}. "{q["text"]}" — {q["source"]}'
        for i, q in enumerate(quotes)
    )

    recent_titles = [l.get("title", "") for l in existing_listicles[-15:]]
    recent_titles_block = "\n".join(f'- "{t}"' for t in recent_titles) or "(none yet)"

    prompt = f"""You are creating a listicle infographic for "The Lotus Lane" — a Buddhist wisdom
brand that shares Daisaku Ikeda's guidance for modern life struggles.

THEME: {theme["name"]}
THEME DESCRIPTION: {theme["description"]}

Here are quotes from this theme:
{quotes_block}

Create a listicle with EXACTLY 5 items. Requirements:
1. Pick the 5 most powerful/shareable quotes from the list above
2. Write a catchy, emotional, specific title for the listicle
3. For each quote, write a 1-sentence explanation (15-25 words) that makes the quote feel relevant to everyday life

TITLE STYLE — The title must be:
- Specific and emotional, not generic
- Speak to a real situation or feeling
- Examples of GOOD titles:
  * "5 Quotes on Courage for When Fear Holds You Back"
  * "When Life Feels Impossible: 5 Words of Hope from Ikeda Sensei"
  * "Struggling at Work? Ikeda Sensei Has 5 Messages for You"
  * "5 Truths About Happiness You Won't Learn in School"
  * "Feeling Stuck? Here Are 5 Reminders That You're Stronger Than You Think"
- Examples of BAD titles:
  * "5 Ikeda Quotes About Courage" (too generic)
  * "Quotes for the Day" (meaningless)
  * "5 Buddhist Teachings" (not emotional)

AVOID titles similar to these recently used ones:
{recent_titles_block}

Return ONLY valid JSON:
{{
    "title": "The catchy listicle title",
    "items": [
        {{
            "quote": "The exact quote text",
            "source": "The source book/work",
            "explanation": "One sentence making this quote feel relevant to everyday life"
        }}
    ]
}}

Return exactly 5 items. Return ONLY the JSON, no other text."""

    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["content"][0]["text"]

    # Parse JSON from response (handle potential markdown wrapping)
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0]

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            result = json.loads(match.group())
        else:
            raise ValueError(f"Claude returned invalid JSON: {content[:200]}...")

    # Validate structure
    assert "title" in result, "Missing 'title' in Claude response"
    assert "items" in result, "Missing 'items' in Claude response"
    assert len(result["items"]) == 5, f"Expected 5 items, got {len(result['items'])}"

    # Add theme info
    result["theme"] = theme["id"]
    result["theme_name"] = theme["name"]

    return result


# ---------------------------------------------------------------------------
# Drawing helpers (shared with quote card)
# ---------------------------------------------------------------------------

def draw_gradient(img: Image.Image, color_top: tuple, color_bottom: tuple) -> None:
    """Draw a vertical gradient using line-by-line approach."""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for y in range(h):
        ratio = y / h
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip() if current_line else word
        bbox = font.getbbox(test)
        tw = bbox[2] - bbox[0]
        if tw <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def draw_separator(draw: ImageDraw.Draw, y: int, width: int, color: tuple) -> None:
    """Draw a subtle horizontal separator with a diamond ornament."""
    cx = width // 2
    line_len = 120
    # Left line
    draw.line([(cx - line_len, y), (cx - 12, y)], fill=color, width=1)
    # Right line
    draw.line([(cx + 12, y), (cx + line_len, y)], fill=color, width=1)
    # Center diamond
    size = 6
    pts = [(cx, y - size), (cx + size, y), (cx, y + size), (cx - size, y)]
    draw.polygon(pts, fill=color)


def draw_lotus_small(draw: ImageDraw.Draw, cx: int, cy: int, color: tuple, size: int = 16) -> None:
    """Draw a small lotus flower."""
    import math
    pw = int(size * 0.38)
    ph = int(size * 0.9)
    r, g, b = color
    light = (min(255, r + 40), min(255, g + 40), min(255, b + 40))
    angles = [-40, -20, 0, 20, 40]
    for angle_deg in angles:
        angle = math.radians(angle_deg)
        tip_x = cx + math.sin(angle) * ph
        tip_y = cy - math.cos(angle) * ph
        perp_x = math.cos(angle) * pw
        perp_y = math.sin(angle) * pw
        base_l = (cx - perp_x, cy - perp_y)
        base_r = (cx + perp_x, cy + perp_y)
        pts = [base_l, (tip_x, tip_y), base_r]
        fill = light if abs(angle_deg) > 25 else color
        draw.polygon(pts, fill=fill)
    cr = max(2, size // 8)
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)


# ---------------------------------------------------------------------------
# Image generation — Tall infographic (1080x1920)
# ---------------------------------------------------------------------------

def generate_infographic(listicle: dict) -> Image.Image:
    """Generate a tall 1080x1920 infographic image."""
    w, h = INFOGRAPHIC_SIZE
    img = Image.new("RGB", (w, h))
    draw_gradient(img, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    # Fonts
    font_title = load_font("Nunito-Bold.ttf", 44)
    font_quote = load_font("Nunito-Regular.ttf", 28)
    font_attribution = load_font("Nunito-Bold.ttf", 20)
    font_explanation = load_font("Nunito-Regular.ttf", 22)
    font_number = load_font("Nunito-Bold.ttf", 48)
    font_branding = load_font("Nunito-Regular.ttf", 18)
    font_branding_sm = load_font("Nunito-Regular.ttf", 14)

    margin_x = 80
    text_area_width = w - 2 * margin_x
    y = 70

    # --- Lotus flower at top ---
    draw_lotus_small(draw, w // 2, y, COLOR_NUMBER, size=22)
    y += 40

    # --- Title ---
    title_lines = wrap_text(listicle["title"], font_title, text_area_width)
    sample_bbox = font_title.getbbox("Ag")
    title_line_h = int((sample_bbox[3] - sample_bbox[1]) * 1.4)
    for line in title_lines:
        bbox = font_title.getbbox(line)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, y), line, fill=COLOR_TITLE, font=font_title)
        y += title_line_h
    y += 20

    # --- Separator below title ---
    draw_separator(draw, y, w, COLOR_SEPARATOR)
    y += 30

    # --- Items ---
    items = listicle["items"]
    # Calculate available height for items
    bottom_reserve = 100  # space for branding
    available_h = h - y - bottom_reserve
    item_spacing = available_h // len(items)

    for i, item in enumerate(items):
        item_start_y = y

        # Number
        num_str = str(i + 1)
        num_bbox = font_number.getbbox(num_str)
        num_tw = num_bbox[2] - num_bbox[0]
        draw.text((margin_x, item_start_y), num_str, fill=COLOR_NUMBER, font=font_number)

        # Quote text (italic-like via regular font, in curly quotes)
        quote_text = f"\u201C{item['quote']}\u201D"
        quote_x = margin_x + num_tw + 20
        quote_max_w = w - quote_x - margin_x
        quote_lines = wrap_text(quote_text, font_quote, quote_max_w)
        q_bbox = font_quote.getbbox("Ag")
        quote_line_h = int((q_bbox[3] - q_bbox[1]) * 1.45)

        qy = item_start_y + 5
        for qline in quote_lines[:4]:  # max 4 lines per quote
            draw.text((quote_x, qy), qline, fill=COLOR_QUOTE, font=font_quote)
            qy += quote_line_h

        # Attribution
        attr_text = f"\u2014 Daisaku Ikeda, {item['source']}"
        draw.text((quote_x, qy), attr_text, fill=COLOR_ATTRIBUTION, font=font_attribution)
        qy += int(font_attribution.getbbox("Ag")[3] * 1.4)

        # Explanation
        expl_lines = wrap_text(item["explanation"], font_explanation, quote_max_w)
        e_bbox = font_explanation.getbbox("Ag")
        expl_line_h = int((e_bbox[3] - e_bbox[1]) * 1.4)
        for eline in expl_lines[:2]:  # max 2 lines
            draw.text((quote_x, qy), eline, fill=COLOR_EXPLANATION, font=font_explanation)
            qy += expl_line_h

        # Separator between items (not after the last)
        if i < len(items) - 1:
            sep_y = item_start_y + item_spacing - 15
            draw_separator(draw, sep_y, w, COLOR_SEPARATOR)

        y = item_start_y + item_spacing

    # --- Branding at bottom ---
    brand_y = h - 70
    wm1 = "The Lotus Lane"
    wm1_bbox = font_branding.getbbox(wm1)
    wm1_tw = wm1_bbox[2] - wm1_bbox[0]
    draw.text(((w - wm1_tw) // 2, brand_y), wm1, fill=COLOR_BRANDING, font=font_branding)

    wm2 = "\u2022 thelotuslane.in \u2022"
    wm2_bbox = font_branding_sm.getbbox(wm2)
    wm2_tw = wm2_bbox[2] - wm2_bbox[0]
    draw.text(((w - wm2_tw) // 2, brand_y + 26), wm2, fill=COLOR_BRANDING, font=font_branding_sm)

    return img


# ---------------------------------------------------------------------------
# Image generation — Instagram carousel (1080x1080 per slide)
# ---------------------------------------------------------------------------

def generate_carousel_cover(listicle: dict) -> Image.Image:
    """Generate the cover slide (1080x1080) for the Instagram carousel."""
    w, h = CAROUSEL_SIZE
    img = Image.new("RGB", (w, h))
    draw_gradient(img, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    font_title = load_font("Nunito-Bold.ttf", 52)
    font_subtitle = load_font("Nunito-Regular.ttf", 28)
    font_branding = load_font("Nunito-Regular.ttf", 18)
    font_branding_sm = load_font("Nunito-Regular.ttf", 14)

    margin_x = 100
    text_area_width = w - 2 * margin_x

    # Lotus at top
    draw_lotus_small(draw, w // 2, 180, COLOR_NUMBER, size=30)

    # Title (centered vertically)
    title_lines = wrap_text(listicle["title"], font_title, text_area_width)
    t_bbox = font_title.getbbox("Ag")
    title_line_h = int((t_bbox[3] - t_bbox[1]) * 1.5)
    total_title_h = title_line_h * len(title_lines)
    title_start_y = (h - total_title_h) // 2 - 40

    for line in title_lines:
        bbox = font_title.getbbox(line)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, title_start_y), line, fill=COLOR_TITLE, font=font_title)
        title_start_y += title_line_h

    # Subtitle
    sub_text = f"Wisdom from Daisaku Ikeda on {listicle.get('theme_name', 'life')}"
    sub_lines = wrap_text(sub_text, font_subtitle, text_area_width)
    sub_y = title_start_y + 30
    s_bbox = font_subtitle.getbbox("Ag")
    sub_line_h = int((s_bbox[3] - s_bbox[1]) * 1.4)
    for sline in sub_lines:
        sbbox = font_subtitle.getbbox(sline)
        stw = sbbox[2] - sbbox[0]
        draw.text(((w - stw) // 2, sub_y), sline, fill=COLOR_EXPLANATION, font=font_subtitle)
        sub_y += sub_line_h

    # Separator
    draw_separator(draw, sub_y + 30, w, COLOR_SEPARATOR)

    # Swipe indicator
    swipe_font = load_font("Nunito-Regular.ttf", 22)
    swipe_text = "Swipe for all 5 quotes \u2192"
    sw_bbox = swipe_font.getbbox(swipe_text)
    sw_tw = sw_bbox[2] - sw_bbox[0]
    draw.text(((w - sw_tw) // 2, sub_y + 70), swipe_text, fill=COLOR_ATTRIBUTION, font=swipe_font)

    # Branding at bottom
    brand_y = h - 70
    wm1 = "The Lotus Lane"
    wm1_bbox = font_branding.getbbox(wm1)
    wm1_tw = wm1_bbox[2] - wm1_bbox[0]
    draw.text(((w - wm1_tw) // 2, brand_y), wm1, fill=COLOR_BRANDING, font=font_branding)
    wm2 = "\u2022 thelotuslane.in \u2022"
    wm2_bbox = font_branding_sm.getbbox(wm2)
    wm2_tw = wm2_bbox[2] - wm2_bbox[0]
    draw.text(((w - wm2_tw) // 2, brand_y + 26), wm2, fill=COLOR_BRANDING, font=font_branding_sm)

    return img


def generate_carousel_slide(item: dict, slide_num: int, total: int, theme_name: str) -> Image.Image:
    """Generate a single carousel slide (1080x1080) for one quote."""
    w, h = CAROUSEL_SIZE
    img = Image.new("RGB", (w, h))
    draw_gradient(img, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    font_number = load_font("Nunito-Bold.ttf", 72)
    font_quote = load_font("Nunito-Regular.ttf", 34)
    font_attribution = load_font("Nunito-Bold.ttf", 22)
    font_explanation = load_font("Nunito-Regular.ttf", 24)
    font_branding = load_font("Nunito-Regular.ttf", 16)
    font_counter = load_font("Nunito-Regular.ttf", 18)

    margin_x = 90
    text_area_width = w - 2 * margin_x

    # Slide counter (top right)
    counter_text = f"{slide_num}/{total}"
    c_bbox = font_counter.getbbox(counter_text)
    c_tw = c_bbox[2] - c_bbox[0]
    draw.text((w - margin_x - c_tw, 50), counter_text, fill=COLOR_ATTRIBUTION, font=font_counter)

    # Large number
    num_str = str(slide_num)
    num_bbox = font_number.getbbox(num_str)
    num_tw = num_bbox[2] - num_bbox[0]
    draw.text(((w - num_tw) // 2, 120), num_str, fill=COLOR_NUMBER, font=font_number)

    # Separator
    draw_separator(draw, 220, w, COLOR_SEPARATOR)

    # Quote (centered, larger)
    quote_text = f"\u201C{item['quote']}\u201D"
    quote_lines = wrap_text(quote_text, font_quote, text_area_width)
    q_bbox = font_quote.getbbox("Ag")
    quote_line_h = int((q_bbox[3] - q_bbox[1]) * 1.55)
    total_quote_h = quote_line_h * min(len(quote_lines), 8)

    # Center the quote block vertically
    quote_area_top = 260
    quote_area_bottom = h - 320
    quote_start_y = quote_area_top + (quote_area_bottom - quote_area_top - total_quote_h) // 2

    for qline in quote_lines[:8]:
        bbox = font_quote.getbbox(qline)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, quote_start_y), qline, fill=COLOR_QUOTE, font=font_quote)
        quote_start_y += quote_line_h

    # Attribution
    attr_y = quote_start_y + 20
    attr_text = f"\u2014 Daisaku Ikeda"
    a_bbox = font_attribution.getbbox(attr_text)
    a_tw = a_bbox[2] - a_bbox[0]
    draw.text(((w - a_tw) // 2, attr_y), attr_text, fill=COLOR_ATTRIBUTION, font=font_attribution)

    # Source
    source_font = load_font("Nunito-Regular.ttf", 18)
    source_text = item["source"]
    s_bbox = source_font.getbbox(source_text)
    s_tw = s_bbox[2] - s_bbox[0]
    draw.text(((w - s_tw) // 2, attr_y + 32), source_text, fill=COLOR_ATTRIBUTION, font=source_font)

    # Separator above explanation
    sep_y = h - 250
    draw_separator(draw, sep_y, w, COLOR_SEPARATOR)

    # Explanation
    expl_lines = wrap_text(item["explanation"], font_explanation, text_area_width)
    e_bbox = font_explanation.getbbox("Ag")
    expl_line_h = int((e_bbox[3] - e_bbox[1]) * 1.45)
    expl_y = sep_y + 25
    for eline in expl_lines[:3]:
        ebbox = font_explanation.getbbox(eline)
        etw = ebbox[2] - ebbox[0]
        draw.text(((w - etw) // 2, expl_y), eline, fill=COLOR_EXPLANATION, font=font_explanation)
        expl_y += expl_line_h

    # Branding
    brand_y = h - 60
    wm = "The Lotus Lane \u2022 thelotuslane.in"
    wm_bbox = font_branding.getbbox(wm)
    wm_tw = wm_bbox[2] - wm_bbox[0]
    draw.text(((w - wm_tw) // 2, brand_y), wm, fill=COLOR_BRANDING, font=font_branding)

    return img


# ---------------------------------------------------------------------------
# SEO page generation
# ---------------------------------------------------------------------------

def generate_seo_page(listicle: dict, target_date: str, all_listicles: list) -> str:
    """Generate an SEO-optimized HTML page for the listicle."""
    title = listicle["title"]
    theme = listicle.get("theme", "")
    theme_name = listicle.get("theme_name", theme.replace("-", " ").title())
    items = listicle["items"]
    page_url = f"{SITE_URL}/listicles/{target_date}.html"
    image_url = f"{SITE_URL}/listicles/{target_date}.png"

    # Format date for display
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        display_date = dt.strftime("%B %d, %Y")
    except ValueError:
        display_date = target_date

    # Build description from first item
    description = f"{title}. {items[0]['explanation']}"

    # Schema.org JSON-LD
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "image": image_url,
        "datePublished": target_date,
        "dateModified": target_date,
        "description": description,
        "author": {"@type": "Organization", "name": "The Lotus Lane"},
        "publisher": {
            "@type": "Organization",
            "name": "The Lotus Lane",
            "logo": {"@type": "ImageObject", "url": f"{SITE_URL}/favicon.ico"},
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
    }

    # Navigation
    idx = next((i for i, l in enumerate(all_listicles) if l.get("date") == target_date), -1)
    prev_l = all_listicles[idx - 1] if idx > 0 else None
    next_l = all_listicles[idx + 1] if 0 <= idx < len(all_listicles) - 1 else None

    nav_html = ""
    if prev_l:
        nav_html += f'<a href="{prev_l["date"]}.html" class="nav-link">&larr; {prev_l["title"]}</a>'
    if next_l:
        nav_html += f'<a href="{next_l["date"]}.html" class="nav-link">{next_l["title"]} &rarr;</a>'

    # Items HTML
    items_html = ""
    for i, item in enumerate(items):
        items_html += f"""
    <div class="quote-item">
      <div class="quote-number">{i + 1}</div>
      <div class="quote-content">
        <blockquote>&ldquo;{item['quote']}&rdquo;</blockquote>
        <cite>&mdash; Daisaku Ikeda, {item['source']}</cite>
        <p class="explanation">{item['explanation']}</p>
      </div>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | The Lotus Lane</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="max-image-preview:large">
  <link rel="canonical" href="{page_url}">

  <!-- Open Graph -->
  <meta property="og:type" content="article">
  <meta property="og:title" content="{title} | The Lotus Lane">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:image:width" content="1080">
  <meta property="og:image:height" content="1920">
  <meta property="og:url" content="{page_url}">
  <meta property="og:site_name" content="The Lotus Lane">
  <meta property="article:published_time" content="{target_date}">
  <meta property="article:tag" content="{theme_name}">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title} | The Lotus Lane">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{image_url}">

  <!-- Pinterest -->
  <meta property="og:image:alt" content="{title}">

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
    .listicle-header {{ padding: 1.5rem 0 0.5rem; text-align: center; }}
    .listicle-header h2 {{ font-size: 1.6rem; color: #3E2723; margin-bottom: 0.4rem; line-height: 1.3; }}
    .listicle-header .meta {{ font-size: 0.85rem; color: #999; }}
    .infographic {{ width: 100%; max-width: 540px; margin: 1.5rem auto; display: block; border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }}
    .quote-item {{ display: flex; gap: 1rem; padding: 1.2rem 0; border-bottom: 1px solid #e8e4de; }}
    .quote-item:last-child {{ border-bottom: none; }}
    .quote-number {{ font-size: 2rem; font-weight: 700; color: #BF8C40; min-width: 2.5rem; padding-top: 0.2rem; }}
    .quote-content {{ flex: 1; }}
    .quote-content blockquote {{ font-style: italic; color: #3E2723; line-height: 1.6; font-size: 1.05rem; margin-bottom: 0.4rem; }}
    .quote-content cite {{ display: block; font-size: 0.85rem; color: #795548; font-style: normal; margin-bottom: 0.4rem; }}
    .quote-content .explanation {{ font-size: 0.95rem; color: #5D4037; line-height: 1.5; }}
    .share-section {{ text-align: center; padding: 1.5rem; background: #f5f3ee; border-radius: 8px; margin: 1.5rem 0; }}
    .share-section a {{ display: inline-block; padding: 0.6rem 1.2rem; background: #25D366; color: white; border-radius: 6px; text-decoration: none; font-weight: 600; margin: 0.3rem; font-size: 0.9rem; }}
    .share-section a.pinterest {{ background: #E60023; }}
    .subscribe {{ text-align: center; padding: 1.5rem; background: #f0ece4; border-radius: 8px; margin: 1.5rem 0; }}
    .subscribe a {{ color: #c0392b; font-weight: 600; }}
    .nav {{ display: flex; justify-content: space-between; padding: 1.5rem 0; border-top: 1px solid #e8e4de; margin-top: 1rem; }}
    .nav-link {{ color: #c0392b; text-decoration: none; font-size: 0.9rem; max-width: 45%; }}
    .nav-link:hover {{ text-decoration: underline; }}
    footer {{ text-align: center; padding: 1rem 0; color: #aaa; font-size: 0.8rem; border-top: 1px solid #e8e4de; margin-top: 1rem; }}
  </style>

  <script data-goatcounter="https://zombielabs.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body>
  <div class="container">
    <header>
      <a href="../"><h1>THE <span>LOTUS</span> LANE</h1></a>
    </header>

    <div class="listicle-header">
      <h2>{title}</h2>
      <div class="meta">{display_date} &middot; {theme_name} &middot; Ikeda Sensei&rsquo;s Guidance</div>
    </div>

    <img src="{target_date}.png" alt="{title}"
         class="infographic" loading="eager" width="1080" height="1920">

    {items_html}

    <div class="share-section">
      <p style="margin-bottom: 0.8rem; color: #666;">Share this with someone who needs it</p>
      <a href="https://wa.me/?text={title}%20%E2%80%94%20{page_url}" target="_blank">WhatsApp</a>
      <a href="https://pinterest.com/pin/create/button/?url={page_url}&media={image_url}&description={title}" target="_blank" class="pinterest">Pinterest</a>
    </div>

    <div class="subscribe">
      <p>Get daily Buddhist wisdom in your inbox</p>
      <p><a href="../subscribe.html">Subscribe to Daimoku Daily &rarr;</a></p>
    </div>

    <nav class="nav">{nav_html}</nav>

    <footer>
      <p>The Lotus Lane &middot; Buddhist wisdom for everyday life</p>
      <p>Guidance by Daisaku Ikeda &middot; Curated with care</p>
    </footer>
  </div>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Save everything
# ---------------------------------------------------------------------------

def save_listicle(listicle: dict, target_date: str, infographic: Image.Image | None,
                  carousel_cover: Image.Image | None, carousel_slides: list | None) -> dict:
    """Save all listicle outputs and update listicles.json."""
    LISTICLES_DIR.mkdir(parents=True, exist_ok=True)

    # Save infographic
    if infographic:
        infographic_path = LISTICLES_DIR / f"{target_date}.png"
        infographic.save(str(infographic_path), "PNG", optimize=True)
        size_kb = infographic_path.stat().st_size / 1024
        print(f"  Saved infographic: {infographic_path} ({size_kb:.0f} KB)")

    # Save carousel
    if carousel_cover and carousel_slides:
        carousel_dir = LISTICLES_DIR / target_date
        carousel_dir.mkdir(parents=True, exist_ok=True)

        cover_path = carousel_dir / "cover.png"
        carousel_cover.save(str(cover_path), "PNG", optimize=True)
        print(f"  Saved carousel cover: {cover_path}")

        for i, slide in enumerate(carousel_slides):
            slide_path = carousel_dir / f"{i + 1}.png"
            slide.save(str(slide_path), "PNG", optimize=True)
        print(f"  Saved {len(carousel_slides)} carousel slides to {carousel_dir}")

    # Update listicles.json
    existing = load_listicles()
    entry = {
        "date": target_date,
        "title": listicle["title"],
        "theme": listicle.get("theme", ""),
        "theme_name": listicle.get("theme_name", ""),
        "image": f"listicles/{target_date}.png",
        "items": listicle["items"],
    }

    # Replace existing entry for same date if any
    existing = [l for l in existing if l.get("date") != target_date]
    existing.append(entry)
    existing.sort(key=lambda l: l.get("date", ""))
    save_listicles(existing)
    print(f"  Updated listicles.json ({len(existing)} total listicles)")

    # Generate SEO page
    html = generate_seo_page(listicle, target_date, existing)
    page_path = LISTICLES_DIR / f"{target_date}.html"
    page_path.write_text(html, encoding="utf-8")
    print(f"  Generated SEO page: {page_path}")

    return entry


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def generate(date_str: str | None = None, forced_theme: str | None = None,
             dry_run: bool = False) -> dict:
    """Main generation pipeline."""
    date_str = date_str or date.today().isoformat()

    print(f"\n{'='*60}")
    print(f"  The Lotus Lane \u2014 Listicle Generator")
    print(f"  Date: {date_str}")
    print(f"{'='*60}\n")

    data = load_quotes()
    existing = load_listicles()

    # Pick theme
    theme = pick_theme(data, existing, forced_theme=forced_theme)
    print(f"  Theme: {theme['name']} ({theme['id']})")
    print(f"  Quotes in theme: {len(theme['quotes'])}")

    # Generate content via Claude
    print(f"\n  Generating listicle content with Claude Sonnet...")
    listicle = generate_listicle_content(theme, existing)
    print(f"  Title: {listicle['title']}")
    print(f"  Items: {len(listicle['items'])}")

    if dry_run:
        print(f"\n  [DRY RUN] Content generated, skipping image generation.")
        print(json.dumps(listicle, indent=2, ensure_ascii=False))
        return listicle

    # Generate images
    print(f"\n  Generating infographic (1080x1920)...")
    infographic = generate_infographic(listicle)

    print(f"  Generating carousel cover (1080x1080)...")
    carousel_cover = generate_carousel_cover(listicle)

    print(f"  Generating {len(listicle['items'])} carousel slides (1080x1080)...")
    carousel_slides = [
        generate_carousel_slide(item, i + 1, len(listicle["items"]),
                                listicle.get("theme_name", ""))
        for i, item in enumerate(listicle["items"])
    ]

    # Save everything
    print(f"\n  Saving...")
    entry = save_listicle(listicle, date_str, infographic, carousel_cover, carousel_slides)

    # Cost report
    print(f"\n  Done! Listicle saved for {date_str}")
    print(f"  Title: {entry['title']}")
    print(f"  Theme: {entry['theme_name']}")
    print(f"  Cost: ~Rs. 1-2 (one Claude Sonnet call, all images local Pillow)")

    return entry


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate a Lotus Lane listicle infographic")
    parser.add_argument("--date", help="Date for the listicle (YYYY-MM-DD)")
    parser.add_argument("--theme", help="Force a specific theme (e.g. courage, hope)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate content only (Claude call), skip images")
    args = parser.parse_args()

    generate(date_str=args.date, forced_theme=args.theme, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
