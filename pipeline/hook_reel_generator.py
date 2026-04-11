#!/usr/bin/env python3
"""
The Lotus Lane — Hook Reel Generator (15-second algorithm-optimized format)

Generates 15-second vertical videos (1080x1920) optimized for Instagram Reels,
YouTube Shorts, and TikTok algorithm discovery.

Format:
    0.0s - 2.0s  : HOOK — Bold text overlay on striking panel ("When your boss takes credit...")
    2.0s - 8.0s  : STORY — Quick pan across 2 panels showing the struggle
    8.0s - 12.0s : WISDOM — Quote text overlay on final panel
   12.0s - 15.0s : CTA — "Follow for daily wisdom" + thelotuslane.in

Key differences from full Shorts:
    - No TTS narration (text-only, works on mute)
    - 15 seconds, not 45-60 (higher watch-through rate)
    - Bold text hooks that stop the scroll
    - Designed for the first 1-2 seconds (algorithm decision window)

Usage:
    python pipeline/hook_reel_generator.py --date 2026-04-10
    python pipeline/hook_reel_generator.py --all
    python pipeline/hook_reel_generator.py --date 2026-04-10 --no-music
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
TOTAL_DURATION = 15.0  # seconds

# Section timings (seconds)
HOOK_START, HOOK_END = 0.0, 2.5
STORY_START, STORY_END = 2.5, 8.5
WISDOM_START, WISDOM_END = 8.5, 12.5
CTA_START, CTA_END = 12.5, 15.0

# Colors
BG_COLOR = (18, 16, 22)
HOOK_TEXT_COLOR = (255, 255, 255)
HOOK_ACCENT_COLOR = (192, 57, 43)  # Red accent
WISDOM_TEXT_COLOR = (255, 255, 255)
WISDOM_ACCENT = (220, 185, 100)  # Gold
CTA_TEXT_COLOR = (200, 195, 185)
CTA_ACCENT = (192, 57, 43)

# Layout
PANEL_DISPLAY_SIZE = 960
PANEL_TOP = 200
TEXT_MARGIN = 60

PROJECT_ROOT = Path(__file__).parent.parent
STRIPS_DIR = PROJECT_ROOT / "strips"
REELS_DIR = PROJECT_ROOT / "reels"
FONTS_DIR = Path(__file__).parent / "fonts"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _find_ffmpeg():
    """Find ffmpeg binary."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    if sys.platform == "win32":
        home = Path.home()
        candidates = [
            home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages",
            Path("C:/ProgramData/chocolatey/bin"),
            Path("C:/ffmpeg/bin"),
        ]
        for base in candidates:
            if not base.exists():
                continue
            for exe in base.rglob("ffmpeg.exe"):
                return str(exe)
    return None


def _load_font(size, bold=False):
    """Load font with fallback chain."""
    candidates = [
        FONTS_DIR / ("ComicNeue-Bold.ttf" if bold else "ComicNeue-Regular.ttf"),
        FONTS_DIR / ("Nunito-Bold.ttf" if bold else "Nunito-Regular.ttf"),
        Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf"),
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(str(p), size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _wrap_text(text, font, max_width):
    """Word-wrap text to fit within max_width pixels."""
    tmp = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(tmp)
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _draw_centered_text(draw, text, font, y, width, color, line_spacing=1.4):
    """Draw centered, wrapped text. Returns y after last line."""
    max_w = width - TEXT_MARGIN * 2
    lines = _wrap_text(text, font, max_w)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (width - tw) // 2
        draw.text((x, y), line, fill=color, font=font)
        y += int(th * line_spacing)
    return y


def _build_hook_text(strip):
    """Generate a scroll-stopping hook from the strip's topic/title."""
    topic = strip.get("topic", "")
    title = strip.get("title", "")
    category = strip.get("category", "")

    # Map common topics to punchy hooks
    hook_templates = {
        "toxic boss": "When your boss makes\nyou feel worthless...",
        "imposter syndrome": "Everyone else belongs here.\nExcept you. Right?",
        "burnout": "You gave everything.\nThere's nothing left.",
        "layoff anxiety": "The email that\nchanges everything.",
        "breakup recovery": "They moved on.\nYou're still here.",
        "loneliness": "Surrounded by people.\nCompletely alone.",
        "jealousy": "They got what\nyou wanted.",
        "depression fog": "Some days, getting\nout of bed is the war.",
        "grief-loss": "The grief hits\nat 3 AM.",
        "comparison trap": "Everyone has it\nfigured out. Except you.",
        "family expectations": "You're not living\ntheir dream anymore.",
        "fear of failure": "What if you try\nand it's not enough?",
        "trust issues": "You want to trust.\nBut last time...",
        "aging parents": "When did they\nget so old?",
        "debt overwhelm": "The numbers don't\nstop growing.",
        "career stagnation": "5 years. Same desk.\nSame ceiling.",
        "being overlooked for promotion": "She got the promotion.\nYou got the lesson.",
        "difficult coworker": "That one person who\ndrains your entire day.",
        "wanting to give up": "What's the point\nof trying anymore?",
        "loss of a loved one": "They're gone.\nAnd the world just... continues.",
        "miscarriage": "Nobody talks about\nthe loss you carry.",
        "pet loss": "It was just a dog.\nExcept it wasn't.",
        "chronic illness": "Your body gave up\nbefore you did.",
        "anxiety attacks": "Your heart races.\nFor no reason at all.",
        "financial comparison": "Your friends earn\ntwice what you do.",
    }

    # Try exact match first
    if topic in hook_templates:
        return hook_templates[topic]

    # Try category-level hooks
    category_hooks = {
        "work-stress": f"Work is crushing you.\nAnd nobody sees it.",
        "relationships": f"Love shouldn't\nhurt this much.",
        "family": f"Family: the people who\nknow exactly where it hurts.",
        "health": f"Your body is\ntrying to tell you something.",
        "finances": f"Money anxiety\nnever sleeps.",
        "self-doubt": f"The voice in your head\nthat says you're not enough.",
        "grief-loss": f"Grief doesn't\nfollow a timeline.",
        "perseverance": f"You've been strong\nfor too long.",
        "anger": f"The anger doesn't\nmake sense anymore.",
        "loneliness": f"You haven't felt\nunderstood in months.",
        "envy": f"It should have\nbeen you.",
    }

    if category in category_hooks:
        return category_hooks[category]

    # Fallback: use the title
    return title


# ---------------------------------------------------------------------------
# Frame rendering
# ---------------------------------------------------------------------------

def render_hook_frame(panel_img, hook_text, progress=1.0):
    """Render the HOOK section: dark panel with bold text overlay.

    progress: 0.0 to 1.0 for text reveal animation
    """
    frame = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(frame)

    # Place panel image (dimmed) as background
    panel = panel_img.copy()
    scale = VIDEO_WIDTH / panel.width
    panel = panel.resize((VIDEO_WIDTH, int(panel.height * scale)), Image.LANCZOS)
    # Center vertically
    py = (VIDEO_HEIGHT - panel.height) // 2
    # Darken the panel
    dark_overlay = Image.new("RGBA", panel.size, (0, 0, 0, 160))
    panel = panel.convert("RGBA")
    panel = Image.alpha_composite(panel, dark_overlay)
    frame.paste(panel.convert("RGB"), (0, py))

    # Draw hook text — large, bold, centered
    font = _load_font(72, bold=True)
    lines = hook_text.split("\n")

    # Calculate total text height
    line_height = 90
    total_h = len(lines) * line_height
    start_y = (VIDEO_HEIGHT - total_h) // 2

    # Animate: reveal lines based on progress
    visible_lines = max(1, int(len(lines) * progress))

    for i, line in enumerate(lines[:visible_lines]):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (VIDEO_WIDTH - tw) // 2

        y = start_y + i * line_height

        # Shadow
        draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=font)
        # Main text
        draw.text((x, y), line, fill=HOOK_TEXT_COLOR, font=font)

    # Red accent bar at bottom
    bar_y = VIDEO_HEIGHT - 80
    draw.rectangle([(VIDEO_WIDTH // 2 - 60, bar_y), (VIDEO_WIDTH // 2 + 60, bar_y + 6)],
                   fill=HOOK_ACCENT_COLOR)

    return frame


def render_story_frame(panel_img, progress):
    """Render the STORY section: Ken Burns pan across panel.

    progress: 0.0 to 1.0 through the story section
    """
    frame = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_COLOR)

    # Scale panel to fill width
    panel = panel_img.copy()
    scale = VIDEO_WIDTH / panel.width
    scaled_h = int(panel.height * scale)
    panel = panel.resize((VIDEO_WIDTH, scaled_h), Image.LANCZOS)

    # Ken Burns: slow zoom + vertical pan
    zoom = 1.0 + 0.08 * progress
    crop_w = int(VIDEO_WIDTH / zoom)
    crop_h = int(VIDEO_HEIGHT / zoom)

    # Pan from top to bottom
    cx = VIDEO_WIDTH // 2
    cy = int(PANEL_TOP + (scaled_h - PANEL_TOP) * progress)
    cy = max(crop_h // 2, min(cy, scaled_h - crop_h // 2))

    left = max(0, cx - crop_w // 2)
    top = max(0, cy - crop_h // 2)
    right = min(panel.width, left + crop_w)
    bottom = min(scaled_h, top + crop_h)

    cropped = panel.crop((left, top, right, bottom))
    cropped = cropped.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

    frame.paste(cropped, (0, 0))

    return frame


def render_wisdom_frame(panel_img, quote, source, progress):
    """Render the WISDOM section: panel with quote overlay."""
    frame = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_COLOR)

    # Panel as dimmed background
    panel = panel_img.copy()
    scale = VIDEO_WIDTH / panel.width
    panel = panel.resize((VIDEO_WIDTH, int(panel.height * scale)), Image.LANCZOS)
    py = (VIDEO_HEIGHT - panel.height) // 2
    dark = Image.new("RGBA", panel.size, (0, 0, 0, 180))
    panel = Image.alpha_composite(panel.convert("RGBA"), dark)
    frame.paste(panel.convert("RGB"), (0, py))

    draw = ImageDraw.Draw(frame)

    # Quote text
    quote_font = _load_font(40, bold=True)
    source_font = _load_font(24, bold=False)

    # Opening quote mark
    mark_font = _load_font(80, bold=True)
    draw.text((TEXT_MARGIN, VIDEO_HEIGHT // 2 - 200), "\u201c", fill=WISDOM_ACCENT, font=mark_font)

    # Quote text
    y = VIDEO_HEIGHT // 2 - 120
    y = _draw_centered_text(draw, quote, quote_font, y, VIDEO_WIDTH, WISDOM_TEXT_COLOR)

    # Source
    if source:
        y += 20
        _draw_centered_text(draw, f"\u2014 {source}", source_font, y, VIDEO_WIDTH, (160, 155, 145))

    return frame


def render_cta_frame(progress):
    """Render the CTA section: follow + website."""
    frame = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(frame)

    # Brand name
    brand_font = _load_font(48, bold=True)
    brand_text = "THE LOTUS LANE"
    bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
    tw = bbox[2] - bbox[0]
    draw.text(((VIDEO_WIDTH - tw) // 2, VIDEO_HEIGHT // 2 - 100),
              brand_text, fill=CTA_ACCENT, font=brand_font)

    # Tagline
    tag_font = _load_font(32, bold=False)
    tag_text = "Ancient wisdom for modern struggles"
    bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
    tw = bbox[2] - bbox[0]
    draw.text(((VIDEO_WIDTH - tw) // 2, VIDEO_HEIGHT // 2 - 30),
              tag_text, fill=CTA_TEXT_COLOR, font=tag_font)

    # CTA
    cta_font = _load_font(36, bold=True)
    cta_text = "Follow for daily wisdom"
    bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
    tw = bbox[2] - bbox[0]
    # Draw button-like background
    btn_w = tw + 60
    btn_h = 60
    btn_x = (VIDEO_WIDTH - btn_w) // 2
    btn_y = VIDEO_HEIGHT // 2 + 50
    draw.rounded_rectangle(
        [(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)],
        radius=30, fill=CTA_ACCENT
    )
    draw.text((btn_x + 30, btn_y + 10), cta_text, fill=(255, 255, 255), font=cta_font)

    # Website
    url_font = _load_font(26, bold=False)
    url_text = "thelotuslane.in"
    bbox = draw.textbbox((0, 0), url_text, font=url_font)
    tw = bbox[2] - bbox[0]
    draw.text(((VIDEO_WIDTH - tw) // 2, VIDEO_HEIGHT // 2 + 140),
              url_text, fill=(120, 115, 110), font=url_font)

    # Subtle "New stories Mon, Wed, Fri"
    sub_font = _load_font(22, bold=False)
    sub_text = "New stories every Mon, Wed, Fri"
    bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    tw = bbox[2] - bbox[0]
    draw.text(((VIDEO_WIDTH - tw) // 2, VIDEO_HEIGHT // 2 + 180),
              sub_text, fill=(90, 85, 80), font=sub_font)

    return frame


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_hook_reel(date_str, verbose=True):
    """Generate a 15-second hook reel from a cached strip.

    Returns path to generated MP4, or None on failure.
    """
    cache_dir = STRIPS_DIR / "cache" / date_str

    # Load script
    script_path = cache_dir / "script.json"
    if not script_path.exists():
        print(f"  [{date_str}] No cached script found")
        return None

    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    script = data["script"]

    # Load panel images
    panel_paths = [cache_dir / f"panel_{i}.png" for i in range(1, 5)]
    panels = []
    for p in panel_paths:
        if p.exists():
            panels.append(Image.open(p).convert("RGB"))
    if len(panels) < 2:
        print(f"  [{date_str}] Need at least 2 panels, found {len(panels)}")
        return None

    # Load strip metadata
    with open(PROJECT_ROOT / "strips.json", "r", encoding="utf-8") as f:
        strips = json.load(f)
    strip = next((s for s in strips if s["date"] == date_str), {})

    # Generate hook text
    hook_text = _build_hook_text(strip)
    quote = script.get("nichiren_quote", strip.get("quote", ""))
    source = script.get("source", strip.get("source", ""))

    # Truncate quote for video readability (max ~100 chars)
    if len(quote) > 120:
        # Find a natural break point
        for sep in [". ", ", ", " — ", "; "]:
            idx = quote[:120].rfind(sep)
            if idx > 40:
                quote = quote[:idx + 1]
                break
        else:
            quote = quote[:117] + "..."

    if verbose:
        print(f"\n  Hook Reel Generator — {date_str}")
        print(f"  Title: {script.get('title', 'Untitled')}")
        print(f"  Hook: {hook_text.replace(chr(10), ' | ')}")
        print(f"  Quote: {quote[:60]}...")

    # Find ffmpeg
    ffmpeg_path = _find_ffmpeg()
    if not ffmpeg_path:
        print("  ERROR: ffmpeg not found")
        return None

    # Create output directory
    REELS_DIR.mkdir(parents=True, exist_ok=True)

    # Render all frames
    total_frames = int(TOTAL_DURATION * FPS)
    tmp_dir = tempfile.mkdtemp(prefix="lotus_reel_")
    frames_dir = Path(tmp_dir) / "frames"
    frames_dir.mkdir()

    if verbose:
        print(f"  Rendering {total_frames} frames...")

    for frame_idx in range(total_frames):
        t = frame_idx / FPS  # current time in seconds

        if t < HOOK_END:
            # HOOK section: text reveal on first panel
            progress = min(1.0, (t - HOOK_START) / (HOOK_END - HOOK_START))
            frame = render_hook_frame(panels[0], hook_text, progress)

        elif t < STORY_END:
            # STORY section: pan across panels 1 and 2
            progress = (t - STORY_START) / (STORY_END - STORY_START)
            # Switch between panels
            if progress < 0.5:
                panel = panels[0]
                pan_progress = progress * 2  # 0 to 1 within first panel
            else:
                panel = panels[1] if len(panels) > 1 else panels[0]
                pan_progress = (progress - 0.5) * 2  # 0 to 1 within second panel
            frame = render_story_frame(panel, pan_progress)

        elif t < WISDOM_END:
            # WISDOM section: quote overlay on last panel
            progress = (t - WISDOM_START) / (WISDOM_END - WISDOM_START)
            wisdom_panel = panels[-1]
            frame = render_wisdom_frame(wisdom_panel, quote, source, progress)

        else:
            # CTA section
            progress = (t - CTA_START) / (CTA_END - CTA_START)
            frame = render_cta_frame(progress)

        # Save frame
        frame.save(frames_dir / f"frame_{frame_idx:05d}.png", "PNG")

    if verbose:
        print(f"  Assembling video with ffmpeg...")

    # Assemble with ffmpeg
    output_path = REELS_DIR / f"{date_str}.mp4"

    cmd = [
        ffmpeg_path,
        "-y",  # overwrite
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%05d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "23",
        "-movflags", "+faststart",
        "-t", str(TOTAL_DURATION),
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ffmpeg error: {result.stderr[:500]}")
        return None

    # Cleanup
    shutil.rmtree(tmp_dir, ignore_errors=True)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    if verbose:
        print(f"  Done! {output_path} ({file_size_mb:.1f} MB)")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate 15-second hook reels for Reels/TikTok")
    parser.add_argument("--date", help="Generate reel for specific date")
    parser.add_argument("--all", action="store_true", help="Generate reels for all cached strips")
    parser.add_argument("--latest", action="store_true", help="Generate reel for latest strip")
    args = parser.parse_args()

    if args.date:
        generate_hook_reel(args.date)

    elif args.all:
        cache_root = STRIPS_DIR / "cache"
        if not cache_root.exists():
            print("No cached strips found")
            return
        dates = sorted(d.name for d in cache_root.iterdir() if d.is_dir())
        print(f"Generating hook reels for {len(dates)} strips...\n")
        success = 0
        for date_str in dates:
            result = generate_hook_reel(date_str)
            if result:
                success += 1
        print(f"\nGenerated {success}/{len(dates)} hook reels")

    elif args.latest:
        cache_root = STRIPS_DIR / "cache"
        if not cache_root.exists():
            print("No cached strips found")
            return
        dates = sorted(d.name for d in cache_root.iterdir() if d.is_dir())
        if dates:
            generate_hook_reel(dates[-1])
        else:
            print("No cached strips found")

    else:
        print("Specify --date, --all, or --latest")


if __name__ == "__main__":
    main()
