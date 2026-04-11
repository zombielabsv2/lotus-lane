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

import httpx
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

# Load .env for API keys
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# TTS config — OpenAI tts-1-hd with "nova" voice (warm, natural)
TTS_MODEL = "tts-1-hd"
TTS_VOICE = "nova"  # warm female; alternatives: "onyx" (deep male), "shimmer" (bright female)
TTS_SPEED = 0.95  # slightly slower for dramatic effect


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


def _add_subtitle(frame, text):
    """Add subtitle text at the bottom of a frame (Reels-style captions)."""
    draw = ImageDraw.Draw(frame)
    font = _load_font(36, bold=True)
    max_w = VIDEO_WIDTH - 120
    lines = _wrap_text(text, font, max_w)

    # Position at bottom third of screen
    line_height = 48
    total_h = len(lines) * line_height
    y = VIDEO_HEIGHT - 350 - total_h

    # Semi-transparent background behind text
    pad = 16
    bg_top = y - pad
    bg_bottom = y + total_h + pad
    bg = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    bg_draw.rounded_rectangle(
        [(40, bg_top), (VIDEO_WIDTH - 40, bg_bottom)],
        radius=12, fill=(0, 0, 0, 140),
    )
    frame.paste(Image.alpha_composite(frame.convert("RGBA"), bg).convert("RGB"))

    draw = ImageDraw.Draw(frame)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (VIDEO_WIDTH - tw) // 2
        # Shadow
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0), font=font)
        # Text
        draw.text((x, y), line, fill=(255, 255, 255), font=font)
        y += line_height


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
# TTS Audio — OpenAI tts-1-hd
# ---------------------------------------------------------------------------

def generate_tts(text, output_path, voice=TTS_VOICE, speed=TTS_SPEED):
    """Generate TTS audio using OpenAI's tts-1-hd. Returns True on success."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return False

    try:
        response = httpx.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": TTS_MODEL,
                "voice": voice,
                "input": text,
                "speed": speed,
                "response_format": "mp3",
            },
            timeout=30,
        )
        response.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"  TTS error: {e}")
        return False


def _get_audio_duration(path, ffmpeg_path):
    """Get duration of an audio file in seconds using ffprobe."""
    # Find ffprobe next to ffmpeg (replace only the filename, not directory)
    ffmpeg_dir = str(Path(ffmpeg_path).parent)
    ffprobe = str(Path(ffmpeg_dir) / Path(ffmpeg_path).name.replace("ffmpeg", "ffprobe"))
    if not Path(ffprobe).exists():
        ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 3.0

    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        dur = float(result.stdout.strip())
        return dur
    except Exception:
        return 3.0


def build_audio_segments(hook_text, quote, message, tmp_dir, ffmpeg_path):
    """Generate separate TTS clips per section, measure each, concatenate.

    Returns dict with exact timestamps per section, or None on failure.
    """
    hook_speech = hook_text.replace("\n", " ").strip()
    bridge = "As one ancient letter puts it."

    # Generate individual TTS clips
    clips = [
        ("hook", hook_speech, "nova", 0.88),
        ("message", message, "nova", 0.92),
        ("bridge", bridge, "nova", 0.85),
        ("quote", quote, "nova", 0.88),
        ("cta", "The Lotus Lane.", "nova", 0.9),
    ]

    paths = {}
    durations = {}
    for name, text, voice, speed in clips:
        path = Path(tmp_dir) / f"{name}.mp3"
        ok = generate_tts(text, path, voice=voice, speed=speed)
        if not ok:
            if name == "hook":
                return None  # hook is required
            continue
        dur = _get_audio_duration(path, ffmpeg_path)
        paths[name] = path
        durations[name] = dur

    # Small silence between sections
    gap = 0.4
    silence_path = Path(tmp_dir) / "gap.mp3"
    subprocess.run([
        ffmpeg_path, "-y",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(gap), "-c:a", "libmp3lame", "-q:a", "4",
        str(silence_path),
    ], capture_output=True)

    # CTA silence (2s)
    cta_silence = Path(tmp_dir) / "cta_silence.mp3"
    subprocess.run([
        ffmpeg_path, "-y",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "2.0", "-c:a", "libmp3lame", "-q:a", "4",
        str(cta_silence),
    ], capture_output=True)

    # Build concat list and calculate exact timestamps
    concat_list = Path(tmp_dir) / "concat.txt"
    entries = []
    timestamps = {}
    t = 0.0

    for name in ["hook", "message", "bridge", "quote", "cta"]:
        if name in paths:
            timestamps[f"{name}_start"] = t
            entries.append(f"file '{paths[name]}'")
            t += durations[name]
            timestamps[f"{name}_end"] = t
            # Add gap after each section (except cta)
            if name != "cta":
                entries.append(f"file '{silence_path}'")
                t += gap

    # Add CTA silence at end
    entries.append(f"file '{cta_silence}'")
    timestamps["cta_visual_start"] = t
    t += 2.0
    timestamps["total_dur"] = t

    with open(concat_list, "w") as f:
        f.write("\n".join(entries))

    output_audio = Path(tmp_dir) / "full_audio.mp3"
    result = subprocess.run([
        ffmpeg_path, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "libmp3lame", "-q:a", "2",
        str(output_audio),
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  Audio concat error: {result.stderr[:300]}")
        return None

    timestamps["audio_path"] = str(output_audio)
    return timestamps


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

    # Create output directory and temp space
    REELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="lotus_reel_")
    frames_dir = Path(tmp_dir) / "frames"
    frames_dir.mkdir()

    message = script.get("message", strip.get("message", ""))

    # --- STEP 1: AUDIO — generate per-section clips, measure exact durations ---
    if verbose:
        print(f"  [Step 1] Generating TTS (OpenAI {TTS_MODEL}/nova, per-section)...")

    ts = build_audio_segments(hook_text, quote, message, tmp_dir, ffmpeg_path)
    has_audio = ts is not None

    if has_audio:
        actual_duration = ts["total_dur"]
        audio_path = ts["audio_path"]
        # Exact timestamps from measured audio durations
        t_hook_end = ts.get("hook_end", 2.0)
        t_msg_start = ts.get("message_start", t_hook_end + 0.4)
        t_msg_end = ts.get("message_end", t_msg_start + 4.0)
        t_bridge_start = ts.get("bridge_start", t_msg_end + 0.4)
        t_bridge_end = ts.get("bridge_end", t_bridge_start + 2.0)
        t_quote_start = ts.get("quote_start", t_bridge_end + 0.4)
        t_quote_end = ts.get("quote_end", t_quote_start + 3.0)
        t_cta = ts.get("cta_visual_start", t_quote_end)

        if verbose:
            print(f"  hook 0-{t_hook_end:.1f}s | msg {t_msg_start:.1f}-{t_msg_end:.1f}s | bridge {t_bridge_start:.1f}-{t_bridge_end:.1f}s | quote {t_quote_start:.1f}-{t_quote_end:.1f}s | CTA {t_cta:.1f}-{actual_duration:.1f}s")
    else:
        actual_duration = TOTAL_DURATION
        audio_path = None
        t_hook_end = 2.5
        t_msg_start, t_msg_end = 2.9, 7.0
        t_bridge_start, t_bridge_end = 7.4, 9.0
        t_quote_start, t_quote_end = 9.4, 13.0
        t_cta = 13.0
        if verbose:
            print(f"  No audio — using fixed timing")

    # Subtitle text matching exactly what the voice says
    hook_speech = hook_text.replace("\n", " ").strip()
    seg_message = message
    seg_bridge = "As one ancient letter puts it."
    seg_quote = f'"{quote}"'

    # --- STEP 2: RENDER FRAMES with subtitles ---
    total_frames = int(actual_duration * FPS)
    if verbose:
        print(f"  [Step 2] Rendering {total_frames} frames ({actual_duration:.1f}s)...")

    for frame_idx in range(total_frames):
        t = frame_idx / FPS

        if t < t_hook_end:
            # HOOK: bold hook text — both lines shown, text = what voice says
            progress = 1.0  # show all lines immediately
            frame = render_hook_frame(panels[0], hook_text, progress)

        elif t < t_msg_end:
            # MESSAGE: pan across panels + full message as subtitle
            span = t_msg_end - t_msg_start
            progress = max(0.0, min(1.0, (t - t_msg_start) / max(span, 0.1)))
            if progress < 0.5:
                panel = panels[0]
                pan_progress = progress * 2
            else:
                panel = panels[min(1, len(panels) - 1)]
                pan_progress = (progress - 0.5) * 2
            frame = render_story_frame(panel, pan_progress)
            _add_subtitle(frame, seg_message)

        elif t < t_bridge_end:
            # BRIDGE: "As one ancient letter puts it."
            progress = (t - t_bridge_start) / max(t_bridge_end - t_bridge_start, 0.1)
            panel = panels[min(2, len(panels) - 1)]
            frame = render_story_frame(panel, progress)
            _add_subtitle(frame, seg_bridge)

        elif t < t_quote_end:
            # QUOTE: wisdom quote overlay — quote text visible in frame
            progress = (t - t_quote_start) / max(t_quote_end - t_quote_start, 0.1)
            frame = render_wisdom_frame(panels[-1], quote, source, progress)

        elif t < actual_duration:
            # CTA: follow + website
            progress = (t - t_cta) / max(actual_duration - t_cta, 0.1)
            frame = render_cta_frame(progress)

        else:
            frame = render_cta_frame(1.0)

        frame.save(frames_dir / f"frame_{frame_idx:05d}.png", "PNG")

    # --- STEP 3: ASSEMBLE video + audio ---
    if verbose:
        print(f"  [Step 3] Assembling video...")

    output_path = REELS_DIR / f"{date_str}.mp4"

    if has_audio:
        cmd = [
            ffmpeg_path, "-y",
            "-framerate", str(FPS),
            "-i", str(frames_dir / "frame_%05d.png"),
            "-i", audio_path,
            "-c:v", "libx264",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "23",
            "-movflags", "+faststart",
            "-shortest",
            str(output_path),
        ]
    else:
        cmd = [
            ffmpeg_path, "-y",
            "-framerate", str(FPS),
            "-i", str(frames_dir / "frame_%05d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "23",
            "-movflags", "+faststart",
            "-t", str(actual_duration),
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
