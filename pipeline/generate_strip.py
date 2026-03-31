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
    """Pick 2-3 characters for this strip."""
    char_keys = list(CHARACTERS.keys())
    num = random.choice([2, 2, 3])  # Weighted toward 2 characters
    selected = random.sample(char_keys, num)
    return {k: CHARACTERS[k] for k in selected}


def generate_script(category, topic, characters, date_str):
    """Use Claude to generate a 4-panel comic script."""
    api_key = get_anthropic_key()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    char_descriptions = "\n".join(
        f"- {c['name']} ({c['age']}, {c['role']}): {c['personality']}"
        for c in characters.values()
    )

    prompt = f"""You are writing a 4-panel comic strip for "The Lotus Lane" — a series about
everyday people discovering Nichiren Buddhist wisdom through real-life struggles.

TODAY'S CHALLENGE: {topic} (category: {category})

CHARACTERS IN THIS STRIP:
{char_descriptions}

Write a 4-panel comic strip. Requirements:
1. Panel 1: Set up the relatable struggle. Show the character(s) in a specific, vivid moment.
2. Panel 2: The struggle deepens or a conversation reveals the emotional core.
3. Panel 3: A moment of wisdom — a character shares or recalls a Nichiren Buddhist insight.
   Use an ACTUAL quote or paraphrase from Nichiren's writings that genuinely addresses this situation.
4. Panel 4: A shift — not a full resolution, but a moment of determination, humor, or warmth.
   The character takes one small step or sees things differently.

TONE: Warm, real, sometimes funny. Never preachy. The wisdom should feel earned, not lectured.
The characters should feel like real people, not mouthpieces.

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

    return json.loads(content)


def generate_panel_image(panel, characters, strip_title, panel_num):
    """Use GPT-4o to generate a single panel image."""
    api_key = get_openai_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    # Build character visual descriptions for this panel
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

    prompt = f"""{ART_STYLE}

Comic panel {panel_num} of 4 for a strip titled "{strip_title}".

Scene: {panel['scene_description']}

Characters in this panel:
{char_visuals}

Mood: {panel.get('mood', 'neutral')}

IMPORTANT: Do NOT include any text, speech bubbles, or dialogue in the image.
Only draw the characters and scene. Text will be added separately.
Draw this as a single comic panel, horizontal format (landscape orientation)."""

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
            "size": "1536x1024",
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
    """Load fonts with fallback chain."""
    pairs = [
        ("arial.ttf", "arialbd.ttf"),
        ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in pairs:
        try:
            return ImageFont.truetype(regular, font_size), ImageFont.truetype(bold, font_size)
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


def assemble_strip(panel_images, script, date_str):
    """Combine panel images into a single vertical strip with dialogue overlays."""
    panel_width = STRIP_WIDTH
    panel_h = PANEL_HEIGHT

    # Resize panels to uniform size
    resized = []
    for i, img in enumerate(panel_images):
        img = img.resize((panel_width, panel_h), Image.LANCZOS)

        # Add dialogue overlay
        dialogue = script["panels"][i].get("dialogue", [])
        img = add_dialogue_to_panel(img, dialogue, panel_width, panel_h)
        resized.append(img)

    # Title bar height
    title_h = 80
    # Total strip height
    total_h = title_h + len(resized) * panel_h + (len(resized) - 1) * PANEL_GAP + 40

    strip = Image.new("RGB", (panel_width, total_h), (250, 249, 246))
    draw = ImageDraw.Draw(strip)

    # Draw title
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 36)
        date_font = ImageFont.truetype("arial.ttf", 18)
    except (OSError, IOError):
        title_font = ImageFont.load_default()
        date_font = ImageFont.load_default()

    title = script.get("title", "The Lotus Lane")
    bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = bbox[2] - bbox[0]
    draw.text(((panel_width - title_w) // 2, 20), title, fill=(74, 74, 74), font=title_font)

    # Date
    formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    bbox = draw.textbbox((0, 0), formatted_date, font=date_font)
    date_w = bbox[2] - bbox[0]
    draw.text(((panel_width - date_w) // 2, 58), formatted_date, fill=(170, 170, 170), font=date_font)

    # Paste panels
    y = title_h
    for img in resized:
        # Convert RGBA to RGB if needed
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (250, 249, 246))
            bg.paste(img, mask=img.split()[3])
            img = bg
        strip.paste(img, (0, y))
        y += panel_h + PANEL_GAP

    return strip


def save_strip(strip_image, script, date_str, category, topic, characters):
    """Save the strip image and update strips.json."""
    STRIPS_DIR.mkdir(parents=True, exist_ok=True)

    # Save image
    filename = f"{date_str}.png"
    filepath = STRIPS_DIR / filename
    strip_image.save(filepath, "PNG", optimize=True)
    print(f"  Saved strip image: {filepath}")

    # Build strip entry
    entry = {
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
    strips = load_existing_strips()
    # Remove existing entry for same date if re-generating
    strips = [s for s in strips if s["date"] != date_str]
    strips.append(entry)
    strips.sort(key=lambda s: s["date"])

    with open(STRIPS_JSON, "w", encoding="utf-8") as f:
        json.dump(strips, f, indent=2, ensure_ascii=False)

    print(f"  Updated strips.json ({len(strips)} total strips)")
    return entry


def generate(date_str=None, forced_topic=None, dry_run=False):
    """Main generation pipeline."""
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  The Lotus Lane — Strip Generator")
    print(f"  Date: {date_str}")
    print(f"{'='*60}\n")

    # 1. Pick topic and characters
    existing = load_existing_strips()
    category, topic = pick_topic(existing, forced_topic)
    characters = pick_characters()

    print(f"  Category: {category}")
    print(f"  Topic: {topic}")
    print(f"  Characters: {', '.join(c['name'] for c in characters.values())}")

    # 2. Generate script with Claude
    print(f"\n  Generating script with Claude...")
    script = generate_script(category, topic, characters, date_str)
    print(f"  Title: {script['title']}")
    print(f"  Quote: {script.get('nichiren_quote', 'N/A')[:80]}...")

    if dry_run:
        print(f"\n  [DRY RUN] Script generated, skipping image generation.")
        print(json.dumps(script, indent=2, ensure_ascii=False))
        return script

    # 3. Generate panel images with GPT-4o
    panel_images = []
    for i, panel in enumerate(script["panels"]):
        print(f"  Generating panel {i+1}/{len(script['panels'])}...")
        img = generate_panel_image(panel, characters, script["title"], i + 1)
        panel_images.append(img)
        if i < len(script["panels"]) - 1:
            time.sleep(2)  # Rate limiting

    # 4. Assemble strip
    print(f"  Assembling strip...")
    strip_image = assemble_strip(panel_images, script, date_str)

    # 5. Save
    print(f"  Saving...")
    entry = save_strip(strip_image, script, date_str, category, topic, characters)

    print(f"\n  Done! Strip saved for {date_str}")
    print(f"  Title: {entry['title']}")
    print(f"  Tags: {', '.join(entry['tags'])}")
    return entry


def main():
    parser = argparse.ArgumentParser(description="Generate a Lotus Lane comic strip")
    parser.add_argument("--date", help="Date for the strip (YYYY-MM-DD)")
    parser.add_argument("--topic", help="Force a specific topic")
    parser.add_argument("--dry-run", action="store_true", help="Generate script only, no images")
    args = parser.parse_args()

    generate(date_str=args.date, forced_topic=args.topic, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
