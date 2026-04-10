#!/usr/bin/env python3
"""
The Lotus Lane — Playwright HTML Rendering Prototype

Demonstrates rendering comic strip dialogue bands and footer
using HTML/CSS (via Playwright screenshot) instead of Pillow text drawing.

Generates:
  - output_playwright.png  — new HTML-rendered strip
  - output_current.png     — current Pillow-rendered strip (for comparison)
  - comparison.png         — side-by-side labeled comparison

Self-contained. Does NOT modify any existing pipeline code.
"""

import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Config (mirrors pipeline/config.py)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / "strips" / "cache" / "2026-04-04"
PROTOTYPE_DIR = Path(__file__).parent

STRIP_WIDTH = 1024
PANEL_HEIGHT = 700

BG_MAIN = (250, 249, 246)
BG_DIALOGUE = (245, 243, 238)
BG_FOOTER = (240, 236, 228)
SPEAKER_COLOR = "rgb(155, 40, 40)"
TEXT_COLOR = "rgb(45, 45, 45)"

# Hex versions for HTML
BG_DIALOGUE_HEX = "#f5f3ee"
BG_FOOTER_HEX = "#f0ece4"
SPEAKER_COLOR_HEX = "#9b2828"
TEXT_COLOR_HEX = "#2d2d2d"

# ---------------------------------------------------------------------------
# Load cached data
# ---------------------------------------------------------------------------

def load_script():
    with open(CACHE_DIR / "script.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_panel_images():
    panels = []
    for i in range(1, 5):
        img = Image.open(CACHE_DIR / f"panel_{i}.png")
        panels.append(img)
    return panels


def resize_panel(img, target_w=STRIP_WIDTH, target_h=PANEL_HEIGHT):
    """Scale to width, center-crop to height (same as pipeline)."""
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, BG_MAIN)
        bg.paste(img, mask=img.split()[3])
        img = bg
    scale = target_w / img.width
    scaled_h = int(img.height * scale)
    img = img.resize((target_w, scaled_h), Image.LANCZOS)
    if scaled_h > target_h:
        top = (scaled_h - target_h) // 2
        img = img.crop((0, top, target_w, top + target_h))
    elif scaled_h < target_h:
        padded = Image.new("RGB", (target_w, target_h), BG_MAIN)
        padded.paste(img, (0, (scaled_h - target_h) // 2))
        img = padded
    return img


# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

def _dialogue_html(dialogue_lines):
    """Build HTML for a single panel's dialogue band."""
    lines_html = ""
    for line in dialogue_lines[:3]:
        parts = line.split(": ", 1)
        if len(parts) == 2:
            speaker, text = parts
            # Strip parenthetical stage directions from speaker display
            # e.g. "Arjun: (thinking) Some text" -> speaker="Arjun", text="(thinking) Some text"
            lines_html += f"""
            <div class="dialogue-line">
                <span class="speaker">{speaker}:</span>
                <span class="text">{text}</span>
            </div>"""
        else:
            lines_html += f"""
            <div class="dialogue-line">
                <span class="text">{line}</span>
            </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Comic+Neue:wght@400;700&family=Nunito:wght@400;600;700&display=swap');

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    width: {STRIP_WIDTH}px;
    margin: 0;
    padding: 0;
    background: {BG_DIALOGUE_HEX};
    font-family: 'Nunito', 'Comic Neue', 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
  }}

  .dialogue-band {{
    width: {STRIP_WIDTH}px;
    padding: 18px 44px 16px 44px;
    background: {BG_DIALOGUE_HEX};
    border-top: 1px solid #dcd8cf;
  }}

  .dialogue-line {{
    margin-bottom: 10px;
    line-height: 1.55;
    letter-spacing: 0.01em;
  }}

  .dialogue-line:last-child {{
    margin-bottom: 0;
  }}

  .speaker {{
    font-family: 'Comic Neue', 'Nunito', sans-serif;
    font-weight: 700;
    color: {SPEAKER_COLOR_HEX};
    font-size: 28px;
    text-shadow: 0 1px 1px rgba(155, 40, 40, 0.08);
    margin-right: 6px;
  }}

  .text {{
    font-family: 'Nunito', 'Comic Neue', sans-serif;
    font-weight: 400;
    color: {TEXT_COLOR_HEX};
    font-size: 26px;
    text-shadow: 0 0.5px 0 rgba(0,0,0,0.04);
  }}
</style>
</head>
<body>
  <div class="dialogue-band" id="capture">
    {lines_html}
  </div>
</body>
</html>"""


def _footer_html(nichiren_quote, source, brand_text="The Lotus Lane  \u00b7  thelotuslane.in"):
    """Build HTML for the footer (quote + source + branding)."""
    quote_html = ""
    if nichiren_quote:
        quote_html = f'<div class="quote">\u201c{nichiren_quote}\u201d</div>'
        if source:
            quote_html += f'<div class="source">\u2014 {source}</div>'

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Comic+Neue:wght@400;700&family=Nunito:wght@400;600;700&display=swap');

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    width: {STRIP_WIDTH}px;
    margin: 0;
    padding: 0;
    background: {BG_FOOTER_HEX};
    font-family: 'Nunito', 'Comic Neue', 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
  }}

  .footer {{
    width: {STRIP_WIDTH}px;
    padding: 20px 50px 18px 50px;
    background: {BG_FOOTER_HEX};
    border-top: 2px solid #d2cdc3;
    text-align: center;
  }}

  .quote {{
    font-family: 'Nunito', serif;
    font-size: 22px;
    font-weight: 600;
    color: #504638;
    line-height: 1.5;
    letter-spacing: 0.01em;
    text-shadow: 0 0.5px 0 rgba(0,0,0,0.03);
    margin-bottom: 6px;
    font-style: italic;
  }}

  .source {{
    font-family: 'Nunito', sans-serif;
    font-size: 17px;
    font-weight: 400;
    color: #8c8278;
    margin-bottom: 14px;
    letter-spacing: 0.02em;
  }}

  .brand {{
    font-family: 'Comic Neue', 'Nunito', sans-serif;
    font-size: 18px;
    font-weight: 700;
    color: #a09688;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }}
</style>
</head>
<body>
  <div class="footer" id="capture">
    {quote_html}
    <div class="brand">{brand_text}</div>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Playwright rendering
# ---------------------------------------------------------------------------

def render_html_to_image(html_content, width=STRIP_WIDTH):
    """Render an HTML string to a PIL Image using Playwright (sync API)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_viewport_size({"width": width, "height": 800})
        page.set_content(html_content)

        # Wait for Google Fonts to load (up to 5s)
        page.wait_for_timeout(500)  # small initial wait
        try:
            page.wait_for_function(
                "document.fonts.ready.then(() => true)",
                timeout=5000
            )
        except Exception:
            pass  # proceed even if fonts timeout — fallback fonts will work

        # Wait a bit more for rendering to settle
        page.wait_for_timeout(300)

        # Screenshot just the #capture element
        element = page.query_selector("#capture")
        if element:
            img_bytes = element.screenshot()
        else:
            img_bytes = page.screenshot(full_page=True)

        browser.close()

    from io import BytesIO
    return Image.open(BytesIO(img_bytes))


def render_all_bands(script):
    """Render all dialogue bands + footer as PIL images via Playwright.

    Opens a single browser and reuses it for all renders (much faster).
    """
    from playwright.sync_api import sync_playwright
    from io import BytesIO

    panels = script["panels"]
    band_images = []
    footer_image = None

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_viewport_size({"width": STRIP_WIDTH, "height": 800})

        # --- Render dialogue bands ---
        for i, panel_data in enumerate(panels):
            dialogue = panel_data.get("dialogue", [])
            if not dialogue:
                # Empty band — just a thin separator
                band = Image.new("RGB", (STRIP_WIDTH, 10), BG_DIALOGUE)
                band_images.append(band)
                continue

            html = _dialogue_html(dialogue)
            page.set_content(html)

            # Wait for fonts on first load, subsequent loads reuse cache
            if i == 0:
                page.wait_for_timeout(800)
                try:
                    page.wait_for_function(
                        "document.fonts.ready.then(() => true)",
                        timeout=5000
                    )
                except Exception:
                    pass
                page.wait_for_timeout(500)
            else:
                page.wait_for_timeout(400)

            element = page.query_selector("#capture")
            img_bytes = element.screenshot() if element else page.screenshot(full_page=True)
            band_images.append(Image.open(BytesIO(img_bytes)))

        # --- Render footer ---
        quote = script.get("nichiren_quote", "")
        source = script.get("source", "")
        html = _footer_html(quote, source)
        page.set_content(html)
        page.wait_for_timeout(400)
        element = page.query_selector("#capture")
        img_bytes = element.screenshot() if element else page.screenshot(full_page=True)
        footer_image = Image.open(BytesIO(img_bytes))

        browser.close()

    return band_images, footer_image


# ---------------------------------------------------------------------------
# Strip assembly (Playwright version)
# ---------------------------------------------------------------------------

def assemble_playwright_strip(panel_images, script):
    """Assemble the full strip: panel -> dialogue band -> panel -> ... -> footer."""
    panels = script["panels"]

    # Resize panels
    resized = [resize_panel(img) for img in panel_images]

    # Render dialogue bands + footer via Playwright
    print("  Rendering HTML dialogue bands with Playwright...")
    band_images, footer_image = render_all_bands(script)

    # Calculate total height
    total_h = 0
    for i in range(len(resized)):
        total_h += PANEL_HEIGHT + band_images[i].height
    total_h += footer_image.height

    # Create canvas
    strip = Image.new("RGB", (STRIP_WIDTH, total_h), BG_MAIN)

    y = 0
    for i, panel_img in enumerate(resized):
        # Paste panel
        strip.paste(panel_img, (0, y))
        y += PANEL_HEIGHT

        # Paste dialogue band
        band = band_images[i]
        if band.mode == "RGBA":
            strip.paste(band, (0, y), band)
        else:
            strip.paste(band, (0, y))
        y += band.height

    # Paste footer
    if footer_image.mode == "RGBA":
        strip.paste(footer_image, (0, y), footer_image)
    else:
        strip.paste(footer_image, (0, y))

    return strip


# ---------------------------------------------------------------------------
# Current Pillow-based strip (import from existing pipeline)
# ---------------------------------------------------------------------------

def generate_current_strip(panel_images, script):
    """Generate the current Pillow-based strip using the existing pipeline code."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from pipeline.generate_strip import assemble_strip
    return assemble_strip(panel_images, script, "2026-04-04")


# ---------------------------------------------------------------------------
# Comparison image
# ---------------------------------------------------------------------------

def make_comparison(current_img, playwright_img):
    """Create a side-by-side comparison image with labels."""
    # Scale both to same width for fair comparison
    target_w = STRIP_WIDTH

    def scale_to_width(img, w):
        ratio = w / img.width
        return img.resize((w, int(img.height * ratio)), Image.LANCZOS)

    left = scale_to_width(current_img, target_w)
    right = scale_to_width(playwright_img, target_w)

    # Make both same height (pad the shorter one)
    max_h = max(left.height, right.height)
    if left.height < max_h:
        padded = Image.new("RGB", (target_w, max_h), BG_MAIN)
        padded.paste(left, (0, 0))
        left = padded
    if right.height < max_h:
        padded = Image.new("RGB", (target_w, max_h), BG_MAIN)
        padded.paste(right, (0, 0))
        right = padded

    # Label bar height
    label_h = 60
    gap = 20  # gap between the two strips

    total_w = target_w * 2 + gap
    total_h = label_h + max_h

    comp = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(comp)

    # Load a font for labels
    try:
        fonts_dir = PROJECT_ROOT / "pipeline" / "fonts"
        label_font = ImageFont.truetype(str(fonts_dir / "Nunito-Bold.ttf"), 32)
    except (OSError, IOError):
        try:
            label_font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 32)
        except (OSError, IOError):
            label_font = ImageFont.load_default()

    # Draw labels
    # Left label: "CURRENT (Pillow)"
    draw.rectangle([0, 0, target_w, label_h], fill=(220, 80, 60))
    lbl = "CURRENT (Pillow)"
    bbox = draw.textbbox((0, 0), lbl, font=label_font)
    lx = (target_w - (bbox[2] - bbox[0])) // 2
    ly = (label_h - (bbox[3] - bbox[1])) // 2
    draw.text((lx, ly), lbl, fill=(255, 255, 255), font=label_font)

    # Right label: "NEW (Playwright)"
    draw.rectangle([target_w + gap, 0, total_w, label_h], fill=(40, 160, 80))
    lbl = "NEW (Playwright)"
    bbox = draw.textbbox((0, 0), lbl, font=label_font)
    rx = target_w + gap + (target_w - (bbox[2] - bbox[0])) // 2
    ry = (label_h - (bbox[3] - bbox[1])) // 2
    draw.text((rx, ry), lbl, fill=(255, 255, 255), font=label_font)

    # Paste strips below labels
    comp.paste(left, (0, label_h))
    comp.paste(right, (target_w + gap, label_h))

    return comp


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  The Lotus Lane — Playwright Rendering Prototype")
    print("=" * 60)

    # Load data
    print("\n  Loading cached script and panels...")
    data = load_script()
    script = data["script"]
    panel_images = load_panel_images()
    print(f"  Title: {script['title']}")
    print(f"  Panels: {len(panel_images)}")

    # 1. Generate Playwright-rendered strip
    print("\n  [1/3] Generating Playwright-rendered strip...")
    pw_strip = assemble_playwright_strip(panel_images, script)
    pw_path = PROTOTYPE_DIR / "output_playwright.png"
    pw_strip.save(str(pw_path), "PNG", optimize=True)
    print(f"  Saved: {pw_path}")
    print(f"  Size: {pw_strip.width}x{pw_strip.height}")

    # 2. Generate current Pillow-based strip
    print("\n  [2/3] Generating current Pillow-based strip...")
    current_strip = generate_current_strip(panel_images, script)
    current_path = PROTOTYPE_DIR / "output_current.png"
    current_strip.save(str(current_path), "PNG", optimize=True)
    print(f"  Saved: {current_path}")
    print(f"  Size: {current_strip.width}x{current_strip.height}")

    # 3. Create comparison
    print("\n  [3/3] Creating side-by-side comparison...")
    comparison = make_comparison(current_strip, pw_strip)
    comp_path = PROTOTYPE_DIR / "comparison.png"
    comparison.save(str(comp_path), "PNG", optimize=True)
    print(f"  Saved: {comp_path}")
    print(f"  Size: {comparison.width}x{comparison.height}")

    print("\n  Done!")
    return str(comp_path)


if __name__ == "__main__":
    comp_path = main()
