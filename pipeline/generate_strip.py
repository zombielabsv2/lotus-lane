#!/usr/bin/env python3
"""
The Lotus Lane — Automated Comic Strip Generator

Generates a 4-panel comic strip with Nichiren Buddhist wisdom
applied to modern life challenges. Uses Claude for scripting
and GPT-4o for image generation.

Usage:
    python pipeline/generate_strip.py                    # Generate today's strip
    python pipeline/generate_strip.py --date 2026-04-02  # Generate for specific date
    python pipeline/generate_strip.py --topic "burnout"  # Force a specific topic
    python pipeline/generate_strip.py --dry-run           # Script only, no images
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from io import BytesIO

import httpx
from PIL import Image, ImageDraw, ImageFont

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import (
    CHARACTERS, CHALLENGE_TOPICS, ART_STYLE, STRIPS_DIR, STRIPS_JSON,
    ANTHROPIC_API_KEY, OPENAI_API_KEY, PANELS_PER_STRIP,
    STRIP_WIDTH, PANEL_HEIGHT, PANEL_GAP,
)

# Load environment from .env if present
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


def get_anthropic_key():
    return os.environ.get("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)


def get_openai_key():
    return os.environ.get("OPENAI_API_KEY", OPENAI_API_KEY)


def load_existing_strips():
    """Load existing strips to avoid topic repetition."""
    if STRIPS_JSON.exists():
        with open(STRIPS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def pick_topic(existing_strips, forced_topic=None):
    """Pick a challenge category and specific topic, avoiding recent repeats."""
    if forced_topic:
        # Find which category this topic belongs to
        for cat, topics in CHALLENGE_TOPICS.items():
            if forced_topic.lower() in [t.lower() for t in topics]:
                return cat, forced_topic
        return "self-doubt", forced_topic

    # Get recent categories to avoid repeats
    recent_cats = [s.get("category", "") for s in existing_strips[-6:]]

    # Pick a category we haven't used recently
    available = [c for c in CHALLENGE_TOPICS if c not in recent_cats]
    if not available:
        available = list(CHALLENGE_TOPICS.keys())

    category = random.choice(available)

    # Pick a specific topic we haven't used recently
    recent_topics = [s.get("topic", "") for s in existing_strips[-20:]]
    available_topics = [t for t in CHALLENGE_TOPICS[category] if t not in recent_topics]
    if not available_topics:
        available_topics = CHALLENGE_TOPICS[category]

    topic = random.choice(available_topics)
    return category, topic


def pick_characters():
    """Pick 2-3 characters. 70% from core roster, 30% new characters."""
    use_new = random.random() < 0.3
    if use_new:
        return {}  # Empty dict signals Claude to create new characters
    char_keys = list(CHARACTERS.keys())
    num = random.choice([2, 2, 3])  # Weighted toward 2 characters
    selected = random.sample(char_keys, num)
    return {k: CHARACTERS[k] for k in selected}


def _recent_quotes(existing_strips, n=10):
    """Get recent Nichiren quotes to avoid repetition."""
    return [s.get("quote", "") for s in existing_strips[-n:] if s.get("quote")]


def generate_script(category, topic, characters, date_str, existing_strips=None):
    """Use Claude to generate a 4-panel comic script."""
    api_key = get_anthropic_key()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    if characters:
        char_block = "CHARACTERS IN THIS STRIP:\n" + "\n".join(
            f"- {c['name']} ({c['age']}, {c['role']}): {c['personality']}"
            for c in characters.values()
        )
    else:
        char_block = """CHARACTERS: Create 2-3 NEW original Indian characters suited to this specific situation.
Give each character a name, age, role, and brief personality. Make them feel real and specific —
not generic. Vary ages, backgrounds, and genders across strips. Include their appearance details
in the scene descriptions so the artist can draw them consistently across all 4 panels."""

    prompt = f"""You are writing a 4-panel comic strip for "The Lotus Lane" — a series about
everyday people discovering Nichiren Buddhist wisdom through real-life struggles.

TODAY'S CHALLENGE: {topic} (category: {category})

{char_block}

Write a 4-panel comic strip. Requirements:
1. Panel 1: Set up the relatable struggle. Show the character(s) in a specific, vivid moment.
2. Panel 2: The struggle deepens or a conversation reveals the emotional core.
3. Panel 3: A moment of wisdom — a character shares or recalls a Nichiren Buddhist insight.
   Use an ACTUAL quote or paraphrase from Nichiren's writings that genuinely addresses this situation.
4. Panel 4: A shift — not a full resolution, but a moment of determination, humor, or warmth.
   The character takes one small step or sees things differently.

TONE: Warm, real, sometimes funny. Never preachy. The wisdom should feel earned, not lectured.
The characters should feel like real people, not mouthpieces.

SETTING: India. All cultural references, currency (use Rs. or rupees, never $), food, places,
slang, and social dynamics should be authentically Indian. Characters may use light Hindi/Marathi
words naturally (arre, yaar, beta, bewakoof, etc.).

IMPORTANT: Use a DIFFERENT Nichiren quote each time. Do NOT use any of these recently used quotes:
{chr(10).join(f'- "{q[:80]}..."' for q in _recent_quotes(existing_strips or [], 10)) or '(none yet)'}

Return your response as JSON with this exact structure:
{{
    "title": "Short catchy title for this strip",
    "panels": [
        {{
            "panel_number": 1,
            "scene_description": "Detailed visual description of the scene, characters, setting, expressions, poses. Be specific enough for an AI image generator.",
            "dialogue": ["Character Name: Their dialogue line", "Character Name: Response"],
            "mood": "one word mood"
        }},
        // ... panels 2, 3, 4
    ],
    "nichiren_quote": "The actual Nichiren quote referenced or paraphrased in the strip",
    "source": "Source reference (e.g., WND-1, p. 302)",
    "message": "A 1-2 sentence takeaway that captures the wisdom of this strip for the reader",
    "tags": ["{category}", "one-or-two-more-relevant-tags"]
}}

Return ONLY the JSON, no other text."""

    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2000,
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
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from mixed content
        import re
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Claude returned invalid JSON: {content[:200]}...")


def generate_panel_image(panel, characters, strip_title, panel_num):
    """Use GPT-4o to generate a single panel image."""
    api_key = get_openai_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    # Build character visual descriptions for this panel
    if characters:
        char_visuals = "\n".join(
            f"- {c['name']}: {c['appearance']}"
            for c in characters.values()
            if c['name'] in panel.get('scene_description', '')
            or any(c['name'] in d for d in panel.get('dialogue', []))
        )
        if not char_visuals:
            char_visuals = "\n".join(
                f"- {c['name']}: {c['appearance']}"
                for c in characters.values()
            )
    else:
        char_visuals = "Draw characters as described in the scene description. Indian characters with authentic appearance."

    prompt = f"""{ART_STYLE}

Scene: {panel['scene_description']}

Characters in this panel:
{char_visuals}

Mood: {panel.get('mood', 'neutral')}

CRITICAL RULES:
- Do NOT include ANY text, titles, words, letters, speech bubbles, captions, or watermarks anywhere in the image.
- Do NOT write the title "{strip_title}" or any other text in the image.
- ONLY draw the characters, their expressions, and the scene. Nothing else.
- The image must be PURELY visual — zero text of any kind."""

    response = httpx.post(
        "https://api.openai.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-image-1",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "quality": "medium",
        },
        timeout=120,
    )
    response.raise_for_status()
    result = response.json()

    # Download the image
    image_data = result["data"][0]
    if "b64_json" in image_data:
        import base64
        img_bytes = base64.b64decode(image_data["b64_json"])
    else:
        img_url = image_data["url"]
        img_resp = httpx.get(img_url, timeout=60)
        img_bytes = img_resp.content

    return Image.open(BytesIO(img_bytes))


def _load_fonts(font_size):
    """Load fonts with fallback chain. Prefers Comic Neue for warm comic feel."""
    fonts_dir = Path(__file__).parent / "fonts"
    pairs = [
        (fonts_dir / "ComicNeue-Regular.ttf", fonts_dir / "ComicNeue-Bold.ttf"),
        (fonts_dir / "Nunito-Regular.ttf", fonts_dir / "Nunito-Bold.ttf"),
        ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ]
    for regular, bold in pairs:
        try:
            return ImageFont.truetype(str(regular), font_size), ImageFont.truetype(str(bold), font_size)
        except (OSError, IOError):
            continue
    default = ImageFont.load_default()
    return default, default


def _wrap_text(text, font, max_width, draw):
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines if lines else [text]


def add_dialogue_to_panel(panel_img, dialogue_lines, panel_width, panel_height):
    """Add speech bubble text overlay to a panel image."""
    if not dialogue_lines:
        return panel_img

    draw = ImageDraw.Draw(panel_img)

    font_size = max(20, panel_width // 50)
    font, font_bold = _load_fonts(font_size)
    line_height = int(font_size * 1.35)

    max_bubble_width = int(panel_width * 0.85)
    max_text_width = max_bubble_width - 40  # padding on both sides
    padding_x = 16
    padding_y = 12

    y_offset = 12

    for line in dialogue_lines[:3]:
        parts = line.split(": ", 1)
        if len(parts) == 2:
            speaker, text = parts
        else:
            speaker, text = "", line

        # Measure speaker name width
        if speaker:
            name_str = f"{speaker}: "
            name_bbox = draw.textbbox((0, 0), name_str, font=font_bold)
            name_w = name_bbox[2] - name_bbox[0]
        else:
            name_str = ""
            name_w = 0

        # Word-wrap the dialogue text
        wrapped = _wrap_text(text, font, max_text_width - name_w, draw)
        # If first line with speaker name is too wide, re-wrap for subsequent lines
        if len(wrapped) > 1:
            first_line_wrapped = _wrap_text(text, font, max_text_width - name_w, draw)
            rest_wrapped = []
            if len(first_line_wrapped) > 1:
                rest_text = " ".join(first_line_wrapped[1:])
                rest_wrapped = _wrap_text(rest_text, font, max_text_width, draw)
            wrapped = [first_line_wrapped[0]] + rest_wrapped

        # Calculate bubble dimensions
        text_lines_count = len(wrapped)
        bubble_text_h = text_lines_count * line_height
        bubble_h = bubble_text_h + padding_y * 2

        # Find the widest line to size the bubble
        widest = 0
        for i, wline in enumerate(wrapped):
            extra = name_w if i == 0 and speaker else 0
            bbox = draw.textbbox((0, 0), wline, font=font)
            w = bbox[2] - bbox[0] + extra
            widest = max(widest, w)

        bubble_w = min(widest + padding_x * 2, max_bubble_width)
        bubble_x = max(10, (panel_width - bubble_w) // 2)
        bubble_y = y_offset

        # Draw bubble with rounded corners
        bubble = Image.new("RGBA", panel_img.size, (0, 0, 0, 0))
        bubble_draw = ImageDraw.Draw(bubble)

        # Subtle shadow
        bubble_draw.rounded_rectangle(
            [bubble_x + 2, bubble_y + 2, bubble_x + bubble_w + 2, bubble_y + bubble_h + 2],
            radius=14, fill=(0, 0, 0, 30),
        )
        # Main bubble
        bubble_draw.rounded_rectangle(
            [bubble_x, bubble_y, bubble_x + bubble_w, bubble_y + bubble_h],
            radius=14, fill=(255, 255, 255, 230), outline=(180, 175, 165, 200), width=2,
        )
        panel_img = Image.alpha_composite(panel_img.convert("RGBA"), bubble)
        draw = ImageDraw.Draw(panel_img)

        # Draw text lines
        text_x = bubble_x + padding_x
        text_y = bubble_y + padding_y
        for i, wline in enumerate(wrapped):
            x = text_x
            if i == 0 and speaker:
                draw.text((x, text_y), name_str, fill=(160, 40, 40), font=font_bold)
                x += name_w
                draw.text((x, text_y), wline, fill=(40, 40, 40), font=font)
            else:
                draw.text((x, text_y), wline, fill=(40, 40, 40), font=font)
            text_y += line_height

        y_offset += bubble_h + 10

    return panel_img


def _measure_dialogue_band(dialogue_lines, font, font_bold, line_height, max_text_width, draw):
    """Calculate how tall a dialogue band needs to be for the given lines."""
    if not dialogue_lines:
        return 0

    total_h = 0
    for line in dialogue_lines[:3]:
        parts = line.split(": ", 1)
        if len(parts) == 2:
            speaker, text = parts
            name_str = f"{speaker}: "
            name_w = draw.textbbox((0, 0), name_str, font=font_bold)[2]
        else:
            text = line
            name_w = 0

        wrapped = _wrap_text(text, font, max_text_width - name_w, draw)
        if len(wrapped) > 1:
            first = _wrap_text(text, font, max_text_width - name_w, draw)
            rest_text = " ".join(first[1:])
            rest = _wrap_text(rest_text, font, max_text_width, draw)
            wrapped = [first[0]] + rest

        total_h += len(wrapped) * line_height + 8  # 8px gap between speakers

    return total_h + 20  # top + bottom padding


def _draw_dialogue_band(strip, dialogue_lines, x, y, band_width, font, font_bold, line_height, max_text_width):
    """Draw dialogue text on a clean background area below a panel."""
    draw = ImageDraw.Draw(strip)
    text_x = x + 40  # left margin
    text_y = y + 10   # top padding

    for line in dialogue_lines[:3]:
        parts = line.split(": ", 1)
        if len(parts) == 2:
            speaker, text = parts
            name_str = f"{speaker}: "
            name_w = draw.textbbox((0, 0), name_str, font=font_bold)[2]
        else:
            speaker, text = "", line
            name_str = ""
            name_w = 0

        wrapped = _wrap_text(text, font, max_text_width - name_w, draw)
        if len(wrapped) > 1:
            first = _wrap_text(text, font, max_text_width - name_w, draw)
            rest_text = " ".join(first[1:])
            rest = _wrap_text(rest_text, font, max_text_width, draw)
            wrapped = [first[0]] + rest

        for i, wline in enumerate(wrapped):
            cx = text_x
            if i == 0 and speaker:
                draw.text((cx, text_y), name_str, fill=(155, 40, 40), font=font_bold)
                cx += name_w
            draw.text((cx, text_y), wline, fill=(45, 45, 45), font=font)
            text_y += line_height

        text_y += 8  # gap between speakers


def assemble_strip(panel_images, script, date_str):
    """Combine panel images into a vertical strip with dialogue in clean bands below each panel.

    Uses Playwright HTML/CSS rendering for dialogue bands and footer (browser-grade typography).
    """
    from pipeline.playwright_renderer import render_strip_bands, PlaywrightBrowser

    panel_width = STRIP_WIDTH
    panel_h = PANEL_HEIGHT
    bg_color = (250, 249, 246)

    # Fit panel images: scale to width, then center-crop to height
    resized = []
    for img in panel_images:
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, bg_color)
            bg.paste(img, mask=img.split()[3])
            img = bg
        scale = panel_width / img.width
        scaled_h = int(img.height * scale)
        img = img.resize((panel_width, scaled_h), Image.LANCZOS)
        if scaled_h > panel_h:
            top = (scaled_h - panel_h) // 2
            img = img.crop((0, top, panel_width, top + panel_h))
        elif scaled_h < panel_h:
            padded = Image.new("RGB", (panel_width, panel_h), bg_color)
            padded.paste(img, (0, (panel_h - scaled_h) // 2))
            img = padded
        resized.append(img)

    # Render dialogue bands + footer via Playwright (single browser instance)
    with PlaywrightBrowser() as browser:
        band_images, footer_image = render_strip_bands(script, panel_width, browser)

    # Calculate total height
    total_h = sum(panel_h + b.height for b in band_images) + footer_image.height
    strip = Image.new("RGB", (panel_width, total_h), bg_color)

    # Paste panels with dialogue bands below each
    y = 0
    for i, img in enumerate(resized):
        strip.paste(img, (0, y))
        y += panel_h

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

def _cache_dir(date_str):
    """Return the cache directory for a given date's strip artifacts."""
    d = STRIPS_DIR / "cache" / date_str
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_script(date_str, script, category, topic, characters):
    """Cache the script JSON so it never needs to be regenerated."""
    cache = _cache_dir(date_str)
    data = {
        "script": script,
        "category": category,
        "topic": topic,
        "characters": list(characters.keys()),
    }
    with open(cache / "script.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_cached_script(date_str):
    """Load a cached script, or return None."""
    path = STRIPS_DIR / "cache" / date_str / "script.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_panel_image(date_str, panel_num, img):
    """Cache an individual panel image."""
    cache = _cache_dir(date_str)
    img.save(cache / f"panel_{panel_num}.png", "PNG")


def _load_cached_panels(date_str):
    """Load cached panel images, or return None if any are missing."""
    cache = STRIPS_DIR / "cache" / date_str
    panels = []
    # Check for 3 or 4 panels (supports both old and new strips)
    num_panels = 3 if (cache / "panel_3.png").exists() and not (cache / "panel_4.png").exists() else 4
    if not (cache / "panel_1.png").exists():
        return None
    for i in range(1, num_panels + 1):
        path = cache / f"panel_{i}.png"
        if not path.exists():
            return None
        panels.append(Image.open(path))
    return panels


def save_strip(strip_image, script, date_str, category, topic, characters):
    """Save the strip image and update strips.json."""
    STRIPS_DIR.mkdir(parents=True, exist_ok=True)

    # Save image
    filename = f"{date_str}.png"
    filepath = STRIPS_DIR / filename
    strip_image.save(filepath, "PNG", optimize=True)
    print(f"  Saved strip image: {filepath}")

    # Build strip entry, preserving extra fields (e.g. youtube_id) from existing entry
    strips = load_existing_strips()
    existing = next((s for s in strips if s["date"] == date_str), {})

    entry = {
        **existing,  # preserve youtube_id and any other fields
        "date": date_str,
        "title": script.get("title", ""),
        "image": f"strips/{filename}",
        "message": script.get("message", ""),
        "quote": script.get("nichiren_quote", ""),
        "source": script.get("source", ""),
        "tags": script.get("tags", [category]),
        "category": category,
        "topic": topic,
        "characters": list(characters.keys()),
    }

    # Update strips.json
    strips = [s for s in strips if s["date"] != date_str]
    strips.append(entry)
    strips.sort(key=lambda s: s["date"])

    with open(STRIPS_JSON, "w", encoding="utf-8") as f:
        json.dump(strips, f, indent=2, ensure_ascii=False)

    print(f"  Updated strips.json ({len(strips)} total strips)")
    return entry


def generate(date_str=None, forced_topic=None, dry_run=False, reassemble=False):
    """Main generation pipeline.

    Caches scripts and panel images so re-assembly is free.
    Use reassemble=True to re-compose from cache with zero API calls.
    """
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  The Lotus Lane — Strip Generator")
    print(f"  Date: {date_str}{'  [REASSEMBLE]' if reassemble else ''}")
    print(f"{'='*60}\n")

    existing = load_existing_strips()
    qc_retries_total = 0

    # --- SCRIPT: use cache if available ---
    cached = _load_cached_script(date_str)
    if cached:
        script = cached["script"]
        category = cached["category"]
        topic = cached["topic"]
        char_keys = cached["characters"]
        characters = {k: CHARACTERS[k] for k in char_keys if k in CHARACTERS}
        print(f"  [CACHED] Script loaded from cache")
    elif reassemble:
        print(f"  ERROR: --reassemble specified but no cached script for {date_str}")
        return None
    else:
        category, topic = pick_topic(existing, forced_topic)
        characters = pick_characters()
        print(f"  Category: {category}")
        print(f"  Topic: {topic}")
        char_names = ', '.join(c['name'] for c in characters.values()) if characters else 'New (AI-created)'
        print(f"  Characters: {char_names}")
        print(f"\n  Generating script with Claude...")
        script = generate_script(category, topic, characters, date_str, existing_strips=existing)
        _save_script(date_str, script, category, topic, characters)
        print(f"  [SAVED] Script cached")

    print(f"  Title: {script['title']}")
    print(f"  Quote: {script.get('nichiren_quote', 'N/A')[:80]}...")

    if dry_run:
        print(f"\n  [DRY RUN] Script generated, skipping image generation.")
        print(json.dumps(script, indent=2, ensure_ascii=False))
        return script

    # --- PANELS: use cache if available ---
    panel_images = _load_cached_panels(date_str)
    if panel_images:
        print(f"  [CACHED] 4 panel images loaded from cache")
    else:
        if reassemble:
            print(f"  ERROR: --reassemble specified but no cached panels for {date_str}")
            return None

        from pipeline.quality_check import run_full_qc

        MAX_RETRIES = 3
        openai_key = get_openai_key()
        panel_images = []
        qc_retries_total = 0

        for i, panel in enumerate(script["panels"]):
            img = None
            for attempt in range(1, MAX_RETRIES + 1):
                label = f"  Panel {i+1}/{len(script['panels'])}"
                if attempt > 1:
                    print(f"{label} — retry {attempt}/{MAX_RETRIES}...")
                else:
                    print(f"{label} — generating...")

                try:
                    img = generate_panel_image(panel, characters, script["title"], i + 1)
                except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                    qc_retries_total += 1
                    print(f"{label} — API ERROR: {e}")
                    if attempt < MAX_RETRIES:
                        time.sleep(5)
                        continue
                    else:
                        print(f"{label} — FAILED after {MAX_RETRIES} attempts")
                        raise

                # Run QC
                passed, issues = run_full_qc(img, openai_key, panel_num=i + 1)
                if passed:
                    print(f"{label} — QC passed")
                    break
                else:
                    qc_retries_total += 1
                    print(f"{label} — QC FAILED: {'; '.join(issues)}")
                    if attempt < MAX_RETRIES:
                        time.sleep(2)
                    else:
                        print(f"{label} — Using best attempt after {MAX_RETRIES} tries")

            _save_panel_image(date_str, i + 1, img)
            panel_images.append(img)
            if i < len(script["panels"]) - 1:
                time.sleep(2)

        print(f"  [SAVED] {len(panel_images)} panel images cached"
              f"{f' ({qc_retries_total} QC retries)' if qc_retries_total else ''}")

    # --- ASSEMBLE (always runs, zero cost) ---
    print(f"  Assembling strip...")
    strip_image = assemble_strip(panel_images, script, date_str)

    # --- SAVE ---
    print(f"  Saving...")
    entry = save_strip(strip_image, script, date_str, category, topic, characters)

    # Cost report
    was_script_cached = bool(cached)
    was_panels_cached = reassemble and bool(_load_cached_panels(date_str))
    retries = qc_retries_total
    num_panels = len(script.get("panels", []))
    num_images = 0 if was_panels_cached else (num_panels + retries)
    claude_cost_usd = 0.0 if was_script_cached else 0.013
    image_cost_usd = num_images * 0.042  # gpt-image-1, 1024x1024, medium
    qc_cost_usd = num_images * 0.00002   # gpt-4o-mini vision check
    total_usd = claude_cost_usd + image_cost_usd + qc_cost_usd
    total_inr = total_usd * 85

    print(f"\n  Done! Strip saved for {date_str}")
    print(f"  Title: {entry['title']}")
    print(f"  Tags: {', '.join(entry['tags'])}")
    if total_usd == 0:
        print(f"  Cost: Rs. 0  [FREE - from cache]")
    else:
        print(f"  Cost: Rs. {total_inr:.1f} (${total_usd:.3f})"
              f" — script: Rs. {claude_cost_usd*85:.1f}, "
              f"images: Rs. {image_cost_usd*85:.1f} ({num_images} generated), "
              f"QC: Rs. {qc_cost_usd*85:.2f}")
    return entry


def reassemble_all():
    """Re-assemble ALL cached strips with current layout. Zero API calls."""
    cache_root = STRIPS_DIR / "cache"
    if not cache_root.exists():
        print("No cache directory found.")
        return

    dates = sorted(d.name for d in cache_root.iterdir() if d.is_dir())
    print(f"Found {len(dates)} cached strips to reassemble.\n")

    for date_str in dates:
        generate(date_str=date_str, reassemble=True)


def main():
    parser = argparse.ArgumentParser(description="Generate a Lotus Lane comic strip")
    parser.add_argument("--date", help="Date for the strip (YYYY-MM-DD)")
    parser.add_argument("--topic", help="Force a specific topic")
    parser.add_argument("--dry-run", action="store_true", help="Generate script only, no images")
    parser.add_argument("--reassemble", action="store_true",
                        help="Re-assemble from cached scripts + panels (zero API cost)")
    parser.add_argument("--reassemble-all", action="store_true",
                        help="Re-assemble ALL cached strips (zero API cost)")
    args = parser.parse_args()

    if args.reassemble_all:
        reassemble_all()
    else:
        generate(date_str=args.date, forced_topic=args.topic,
                 dry_run=args.dry_run, reassemble=args.reassemble)


if __name__ == "__main__":
    main()
