#!/usr/bin/env python3
"""
Generate WhatsApp-optimized "Good Morning" quote card images from Ikeda quotes.

Usage:
    python pipeline/generate_quote_card.py                    # Today's card
    python pipeline/generate_quote_card.py --date 2026-04-09  # Specific date
    python pipeline/generate_quote_card.py --theme courage    # Force theme
    python pipeline/generate_quote_card.py --all-themes       # 1 sample per theme
"""

import argparse
import hashlib
import json
import math
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUOTES_PATH = PROJECT_ROOT / "ikeda" / "quotes.json"
CARDS_DIR = PROJECT_ROOT / "cards"
HISTORY_PATH = CARDS_DIR / "history.json"
FONTS_DIR = Path(__file__).resolve().parent / "fonts"

# ---------------------------------------------------------------------------
# Design constants
# ---------------------------------------------------------------------------
CARD_SIZE = (1080, 1080)

# Colors
BG_TOP = (253, 246, 227)        # #FDF6E3 warm cream
BG_BOTTOM = (245, 230, 200)     # #F5E6C8 golden cream
COLOR_GOOD_MORNING = (191, 140, 64)    # #BF8C40 dark gold/amber
COLOR_QUOTE = (62, 39, 35)             # #3E2723 dark brown
COLOR_ATTRIBUTION = (121, 85, 72)      # #795548 medium brown
COLOR_SOURCE = (158, 128, 110)         # #9E806E warm taupe
COLOR_WATERMARK = (189, 189, 189)      # #BDBDBD light gray
COLOR_LOTUS = (191, 140, 64)           # match Good Morning gold
COLOR_DIVIDER = (210, 185, 150)        # subtle warm divider

# Fonts
FONT_GOOD_MORNING_SIZE = 46
FONT_QUOTE_SIZE_DEFAULT = 34
FONT_QUOTE_SIZE_MIN = 22
FONT_ATTRIBUTION_SIZE = 24
FONT_SOURCE_SIZE = 18
FONT_WATERMARK_SIZE = 16

# Layout
MARGIN_X = 80
TOP_Y = 120
QUOTE_BOTTOM_MARGIN = 280  # space reserved below quote area for attribution etc.
BOTTOM_Y = CARD_SIZE[1] - 60


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


def load_history() -> dict:
    """Load history of used quotes. Returns dict with 'used' list and 'last_theme_index'."""
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"used": [], "last_theme_index": -1}


def save_history(history: dict) -> None:
    """Save history."""
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def quote_id(theme_id: str, quote_text: str) -> str:
    """Generate a stable ID for a quote."""
    h = hashlib.md5(f"{theme_id}:{quote_text}".encode()).hexdigest()[:10]
    return f"{theme_id}:{h}"


def pick_quote(data: dict, history: dict, forced_theme: str | None = None) -> tuple[dict, str, dict]:
    """
    Pick a quote, rotating through themes and avoiding recent repeats.
    Returns (theme_dict, theme_id, quote_dict).
    """
    themes = data["themes"]
    used_ids = set(history.get("used", []))
    last_idx = history.get("last_theme_index", -1)

    if forced_theme:
        # Find the forced theme
        theme = None
        for t in themes:
            if t["id"] == forced_theme:
                theme = t
                break
        if not theme:
            available = [t["id"] for t in themes]
            raise ValueError(f"Theme '{forced_theme}' not found. Available: {available}")

        # Pick an unused quote from this theme
        for q in theme["quotes"]:
            qid = quote_id(theme["id"], q["text"])
            if qid not in used_ids:
                return theme, theme["id"], q
        # All used — reset this theme and pick first
        history["used"] = [u for u in history.get("used", []) if not u.startswith(f"{theme['id']}:")]
        return theme, theme["id"], theme["quotes"][0]

    # Rotate through themes round-robin
    total_themes = len(themes)
    for offset in range(1, total_themes + 1):
        idx = (last_idx + offset) % total_themes
        theme = themes[idx]
        for q in theme["quotes"]:
            qid = quote_id(theme["id"], q["text"])
            if qid not in used_ids:
                history["last_theme_index"] = idx
                return theme, theme["id"], q

    # All 315 quotes used — reset history
    history["used"] = []
    history["last_theme_index"] = 0
    return themes[0], themes[0]["id"], themes[0]["quotes"][0]


def record_usage(history: dict, theme_id: str, quote: dict) -> None:
    """Record that a quote was used."""
    qid = quote_id(theme_id, quote["text"])
    if qid not in history.get("used", []):
        history.setdefault("used", []).append(qid)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_gradient_fast(img: Image.Image, color_top: tuple, color_bottom: tuple) -> None:
    """Draw a vertical gradient using line-by-line approach (faster than pixel-by-pixel)."""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for y in range(h):
        ratio = y / h
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def wrap_text_to_width(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
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
            # If a single word exceeds max_width, force it onto its own line
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def fit_quote_font_size(text: str, max_width: int, max_height: int) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """
    Find the largest font size that fits the quote within the available area.
    Returns (font, wrapped_lines, line_height).
    """
    for size in range(FONT_QUOTE_SIZE_DEFAULT, FONT_QUOTE_SIZE_MIN - 1, -2):
        font = load_font("Nunito-Regular.ttf", size)
        lines = wrap_text_to_width(text, font, max_width)
        # Calculate total height
        sample_bbox = font.getbbox("Ag")
        line_h = int((sample_bbox[3] - sample_bbox[1]) * 1.6)
        total_h = line_h * len(lines)
        if total_h <= max_height:
            return font, lines, line_h

    # At minimum size, if still too long, truncate
    font = load_font("Nunito-Regular.ttf", FONT_QUOTE_SIZE_MIN)
    lines = wrap_text_to_width(text, font, max_width)
    sample_bbox = font.getbbox("Ag")
    line_h = int((sample_bbox[3] - sample_bbox[1]) * 1.6)
    max_lines = max(3, max_height // line_h)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;:!? ") + "..."
    return font, lines, line_h


def draw_lotus_flower(draw: ImageDraw.Draw, cx: int, cy: int, color: tuple, size: int = 30) -> None:
    """Draw a stylized lotus flower using ellipse petals."""
    # Semi-transparent look: use a slightly lighter shade for inner petals
    r, g, b = color
    light = (min(255, r + 40), min(255, g + 40), min(255, b + 40))

    # Petal dimensions
    pw = int(size * 0.38)  # petal half-width
    ph = int(size * 0.9)   # petal height

    # 5 petals arranged in a fan
    angles = [-40, -20, 0, 20, 40]
    for angle_deg in angles:
        angle = math.radians(angle_deg)
        # Tip of this petal
        tip_x = cx + math.sin(angle) * ph
        tip_y = cy - math.cos(angle) * ph
        # Base points (left and right of center)
        perp_x = math.cos(angle) * pw
        perp_y = math.sin(angle) * pw
        base_l = (cx - perp_x, cy - perp_y)
        base_r = (cx + perp_x, cy + perp_y)
        # Draw petal as a polygon (tear-drop shape)
        pts = [base_l, (tip_x, tip_y), base_r]
        fill = light if abs(angle_deg) > 25 else color
        draw.polygon(pts, fill=fill)

    # Small center circle
    cr = max(3, size // 8)
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)


def draw_lotus_ornament(draw: ImageDraw.Draw, cx: int, cy: int, color: tuple, size: int = 12) -> None:
    """Draw a small stylized diamond ornament (for divider lines)."""
    # Center diamond
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    draw.polygon(pts, fill=color)
    # Two small dots flanking
    dot_r = max(2, size // 4)
    offset = size * 2
    draw.ellipse([cx - offset - dot_r, cy - dot_r, cx - offset + dot_r, cy + dot_r], fill=color)
    draw.ellipse([cx + offset - dot_r, cy - dot_r, cx + offset + dot_r, cy + dot_r], fill=color)


def draw_decorative_line(draw: ImageDraw.Draw, y: int, width: int, color: tuple) -> None:
    """Draw a subtle decorative horizontal line with a lotus ornament in the center."""
    cx = width // 2
    line_w = 200
    # Left line
    draw.line([(cx - line_w, y), (cx - 24, y)], fill=color, width=1)
    # Right line
    draw.line([(cx + 24, y), (cx + line_w, y)], fill=color, width=1)
    # Center ornament
    draw_lotus_ornament(draw, cx, y, color, size=8)


# ---------------------------------------------------------------------------
# Main card generation
# ---------------------------------------------------------------------------

def generate_card(quote_text: str, source: str, theme_name: str, target_date: date) -> Image.Image:
    """Generate a single quote card image."""
    img = Image.new("RGB", CARD_SIZE)
    draw_gradient_fast(img, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    # Load fonts
    font_gm = load_font("Nunito-Bold.ttf", FONT_GOOD_MORNING_SIZE)
    font_attr = load_font("Nunito-Bold.ttf", FONT_ATTRIBUTION_SIZE)
    font_source = load_font("Nunito-Regular.ttf", FONT_SOURCE_SIZE)
    font_watermark = load_font("Nunito-Regular.ttf", FONT_WATERMARK_SIZE)

    w, h = CARD_SIZE
    text_area_width = w - 2 * MARGIN_X

    # --- Lotus flower at the very top ---
    lotus_y = TOP_Y - 36
    draw_lotus_flower(draw, w // 2, lotus_y, COLOR_LOTUS, size=28)

    # --- "Good Morning" ---
    gm_text = "Good Morning"
    gm_bbox = font_gm.getbbox(gm_text)
    gm_tw = gm_bbox[2] - gm_bbox[0]
    draw.text(((w - gm_tw) // 2, TOP_Y), gm_text, fill=COLOR_GOOD_MORNING, font=font_gm)

    # --- Decorative line below Good Morning ---
    deco_y = TOP_Y + (gm_bbox[3] - gm_bbox[1]) + 30
    draw_decorative_line(draw, deco_y, w, COLOR_DIVIDER)

    # --- Quote text ---
    quote_area_top = deco_y + 40
    quote_area_height = h - quote_area_top - QUOTE_BOTTOM_MARGIN

    # Add opening and closing curly quotes
    display_text = f"\u201C{quote_text}\u201D"

    font_quote, lines, line_h = fit_quote_font_size(display_text, text_area_width, quote_area_height)

    # Center the quote block vertically in its area
    total_text_h = line_h * len(lines)
    quote_start_y = quote_area_top + (quote_area_height - total_text_h) // 2

    for i, line in enumerate(lines):
        line_bbox = font_quote.getbbox(line)
        line_tw = line_bbox[2] - line_bbox[0]
        x = (w - line_tw) // 2
        y = quote_start_y + i * line_h
        draw.text((x, y), line, fill=COLOR_QUOTE, font=font_quote)

    # --- Attribution section ---
    attr_y = h - QUOTE_BOTTOM_MARGIN + 40

    # Decorative line above attribution
    draw_decorative_line(draw, attr_y - 20, w, COLOR_DIVIDER)

    # "- Daisaku Ikeda"
    attr_text = "\u2014 Daisaku Ikeda"
    attr_bbox = font_attr.getbbox(attr_text)
    attr_tw = attr_bbox[2] - attr_bbox[0]
    draw.text(((w - attr_tw) // 2, attr_y), attr_text, fill=COLOR_ATTRIBUTION, font=font_attr)

    # Source book name
    source_y = attr_y + (attr_bbox[3] - attr_bbox[1]) + 12
    source_bbox = font_source.getbbox(source)
    source_tw = source_bbox[2] - source_bbox[0]
    draw.text(((w - source_tw) // 2, source_y), source, fill=COLOR_SOURCE, font=font_source)

    # --- Bottom watermark ---
    wm_line1 = "The Lotus Lane"
    wm_line2 = "\u2022 thelotuslane.in \u2022"

    wm1_bbox = font_watermark.getbbox(wm_line1)
    wm1_tw = wm1_bbox[2] - wm1_bbox[0]
    wm1_th = wm1_bbox[3] - wm1_bbox[1]

    wm2_font = load_font("Nunito-Regular.ttf", 13)
    wm2_bbox = wm2_font.getbbox(wm_line2)
    wm2_tw = wm2_bbox[2] - wm2_bbox[0]

    wm_y = BOTTOM_Y - wm1_th - 14
    draw.text(((w - wm1_tw) // 2, wm_y), wm_line1, fill=COLOR_WATERMARK, font=font_watermark)
    draw.text(((w - wm2_tw) // 2, wm_y + wm1_th + 4), wm_line2, fill=COLOR_WATERMARK, font=wm2_font)

    return img


def save_card(img: Image.Image, output_path: Path) -> None:
    """Save card as optimized PNG (< 500KB target for WhatsApp)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Save as PNG with optimization
    img.save(str(output_path), "PNG", optimize=True)
    size_kb = output_path.stat().st_size / 1024
    print(f"  Saved: {output_path} ({size_kb:.0f} KB)")
    if size_kb > 500:
        # Re-save as JPEG if PNG is too large
        jpg_path = output_path.with_suffix(".jpg")
        img.save(str(jpg_path), "JPEG", quality=85, optimize=True)
        jpg_kb = jpg_path.stat().st_size / 1024
        print(f"  Also saved JPEG fallback: {jpg_path} ({jpg_kb:.0f} KB)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate WhatsApp Good Morning quote cards")
    parser.add_argument("--date", type=str, help="Date for the card (YYYY-MM-DD), default today")
    parser.add_argument("--theme", type=str, help="Force a specific theme (e.g. courage, hope)")
    parser.add_argument("--all-themes", action="store_true", help="Generate 1 sample per theme")
    args = parser.parse_args()

    data = load_quotes()
    history = load_history()

    if args.all_themes:
        # Generate one card per theme
        print(f"Generating sample cards for all {len(data['themes'])} themes...")
        samples_dir = CARDS_DIR / "samples"
        samples_dir.mkdir(parents=True, exist_ok=True)
        for theme in data["themes"]:
            quote = theme["quotes"][0]  # first quote of each theme
            target_date = date.today()
            img = generate_card(quote["text"], quote["source"], theme["name"], target_date)
            out_path = samples_dir / f"{theme['id']}.png"
            save_card(img, out_path)
            print(f"  [{theme['id']}] \"{quote['text'][:60]}...\"")
        print(f"\nDone! {len(data['themes'])} sample cards in {samples_dir}")
        return

    # Single card
    target_date_str = args.date or date.today().isoformat()
    try:
        target_date = date.fromisoformat(target_date_str)
    except ValueError:
        print(f"Error: Invalid date format '{target_date_str}'. Use YYYY-MM-DD.")
        sys.exit(1)

    theme_dict, theme_id, quote = pick_quote(data, history, forced_theme=args.theme)
    record_usage(history, theme_id, quote)
    save_history(history)

    print(f"Date: {target_date}")
    print(f"Theme: {theme_dict['name']}")
    print(f"Quote: \"{quote['text'][:80]}{'...' if len(quote['text']) > 80 else ''}\"")
    print(f"Source: {quote['source']}")

    img = generate_card(quote["text"], quote["source"], theme_dict["name"], target_date)
    out_path = CARDS_DIR / f"{target_date.isoformat()}.png"
    save_card(img, out_path)

    print(f"\nCard generated successfully!")


if __name__ == "__main__":
    main()
