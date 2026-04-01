#!/usr/bin/env python3
"""
The Lotus Lane -- YouTube Shorts Video Generator

Generates 30-60 second vertical videos (1080x1920) from cached comic strip
panels and scripts. Each panel gets a Ken Burns effect (slow zoom), dialogue
appears as clean subtitles, and a branded end card displays the Nichiren quote.

Requirements:
    - ffmpeg must be installed and on PATH
    - Pillow (already in pipeline requirements)

Usage:
    python pipeline/video_generator.py --date 2026-03-31    # Single date
    python pipeline/video_generator.py --all                 # All cached strips
    python pipeline/video_generator.py --date 2026-03-31 --fps 30  # Custom FPS
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

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS_DEFAULT = 24

# Timing (seconds)
PANEL_DURATION = 9       # Each of 4 panels
FADE_DURATION = 0.5      # Cross-fade between panels
END_CARD_DURATION = 4    # Final quote + branding card

# Ken Burns: zoom from 1.0x to this scale over the panel duration
KB_ZOOM_START = 1.0
KB_ZOOM_END = 1.08

# Panel image placement: square panel occupies top portion of portrait frame
PANEL_TOP_MARGIN = 80
PANEL_DISPLAY_SIZE = 960  # square panel rendered at this size within 1080 width

# Subtitle styling
SUBTITLE_FONT_SIZE = 36
SUBTITLE_LINE_HEIGHT = 46
SUBTITLE_BAND_BOTTOM_MARGIN = 180  # from bottom of frame
SUBTITLE_MAX_WIDTH = 960
SUBTITLE_BG_ALPHA = 180  # 0-255

# End card styling
ENDCARD_QUOTE_SIZE = 38
ENDCARD_SOURCE_SIZE = 26
ENDCARD_BRAND_SIZE = 28
ENDCARD_MSG_SIZE = 30

# Colors
BG_COLOR = (24, 22, 28)          # Dark background
SUBTITLE_TEXT_COLOR = (255, 255, 255)
SUBTITLE_BG_COLOR = (0, 0, 0)
ENDCARD_BG = (30, 27, 35)
ENDCARD_ACCENT = (200, 170, 100)  # Warm gold
ENDCARD_TEXT = (240, 235, 225)
ENDCARD_DIM = (160, 155, 145)

PROJECT_ROOT = Path(__file__).parent.parent
STRIPS_DIR = PROJECT_ROOT / "strips"
SHORTS_DIR = PROJECT_ROOT / "shorts"
FONTS_DIR = Path(__file__).parent / "fonts"


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _load_font(size, bold=False):
    """Load a font with fallback chain."""
    candidates = [
        FONTS_DIR / ("Nunito-Bold.ttf" if bold else "Nunito-Regular.ttf"),
        FONTS_DIR / ("ComicNeue-Bold.ttf" if bold else "ComicNeue-Regular.ttf"),
        Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(str(p), size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Text wrapping
# ---------------------------------------------------------------------------

def _wrap_text(text, font, max_width):
    """Word-wrap text to fit within max_width pixels. Returns list of lines."""
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


# ---------------------------------------------------------------------------
# Ken Burns frame generation
# ---------------------------------------------------------------------------

def _ken_burns_crop(panel_img, progress, zoom_start=KB_ZOOM_START, zoom_end=KB_ZOOM_END):
    """Apply a gentle zoom-in Ken Burns effect to a panel image.

    Args:
        panel_img: PIL Image (1024x1024)
        progress: float 0.0 to 1.0 (start to end of panel duration)
        zoom_start: initial zoom level
        zoom_end: final zoom level

    Returns:
        PIL Image cropped/scaled for the current frame
    """
    w, h = panel_img.size
    # Smooth easing (ease-in-out)
    t = 0.5 - 0.5 * math.cos(math.pi * progress)
    zoom = zoom_start + (zoom_end - zoom_start) * t

    # Calculate crop box (center crop at current zoom)
    crop_w = w / zoom
    crop_h = h / zoom
    # Slight drift toward top-right as we zoom
    drift_x = 0.5 + 0.03 * t
    drift_y = 0.5 - 0.02 * t
    left = (w - crop_w) * drift_x
    top = (h - crop_h) * drift_y
    right = left + crop_w
    bottom = top + crop_h

    cropped = panel_img.crop((int(left), int(top), int(right), int(bottom)))
    return cropped.resize((PANEL_DISPLAY_SIZE, PANEL_DISPLAY_SIZE), Image.LANCZOS)


def _compose_panel_frame(panel_img_kb, dialogue_lines, font, font_bold):
    """Compose a single video frame: dark background + panel + subtitles.

    Args:
        panel_img_kb: Ken Burns processed panel image (PANEL_DISPLAY_SIZE x PANEL_DISPLAY_SIZE)
        dialogue_lines: list of dialogue strings for this panel
        font: regular subtitle font
        font_bold: bold subtitle font (for speaker names)

    Returns:
        PIL Image (VIDEO_WIDTH x VIDEO_HEIGHT)
    """
    frame = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_COLOR)

    # Place panel centered horizontally, near top
    panel_x = (VIDEO_WIDTH - PANEL_DISPLAY_SIZE) // 2
    frame.paste(panel_img_kb, (panel_x, PANEL_TOP_MARGIN))

    if not dialogue_lines:
        return frame

    # Build subtitle text block
    all_lines = []
    for line in dialogue_lines[:3]:
        parts = line.split(": ", 1)
        if len(parts) == 2:
            speaker, text = parts[0], parts[1]
            # Clean up parenthetical stage directions in speaker
            if "(" in speaker:
                speaker = speaker.split("(")[0].strip()
        else:
            speaker, text = None, line

        wrapped = _wrap_text(text, font, SUBTITLE_MAX_WIDTH - 20)
        for i, wline in enumerate(wrapped):
            all_lines.append((speaker if i == 0 else None, wline))

    if not all_lines:
        return frame

    # Calculate subtitle band dimensions
    band_h = len(all_lines) * SUBTITLE_LINE_HEIGHT + 24  # padding
    band_y = VIDEO_HEIGHT - SUBTITLE_BAND_BOTTOM_MARGIN - band_h
    band_x = (VIDEO_WIDTH - SUBTITLE_MAX_WIDTH) // 2

    # Draw semi-transparent background band
    overlay = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(
        [band_x - 10, band_y - 8, band_x + SUBTITLE_MAX_WIDTH + 10, band_y + band_h + 8],
        radius=16,
        fill=(*SUBTITLE_BG_COLOR, SUBTITLE_BG_ALPHA),
    )
    frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(frame)
    text_y = band_y + 12
    for speaker, wline in all_lines:
        x = band_x + 10
        if speaker:
            name_text = f"{speaker}: "
            draw.text((x, text_y), name_text, fill=ENDCARD_ACCENT, font=font_bold)
            name_bbox = draw.textbbox((0, 0), name_text, font=font_bold)
            x += name_bbox[2] - name_bbox[0]
        draw.text((x, text_y), wline, fill=SUBTITLE_TEXT_COLOR, font=font)
        text_y += SUBTITLE_LINE_HEIGHT

    return frame


def _compose_end_card(nichiren_quote, source, message, title):
    """Create the branded end card frame with Nichiren quote.

    Returns:
        PIL Image (VIDEO_WIDTH x VIDEO_HEIGHT)
    """
    frame = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), ENDCARD_BG)
    draw = ImageDraw.Draw(frame)

    font_quote = _load_font(ENDCARD_QUOTE_SIZE, bold=False)
    font_source = _load_font(ENDCARD_SOURCE_SIZE, bold=False)
    font_brand = _load_font(ENDCARD_BRAND_SIZE, bold=True)
    font_msg = _load_font(ENDCARD_MSG_SIZE, bold=False)

    y = 500  # vertical center area

    # Decorative line
    line_w = 200
    line_x = (VIDEO_WIDTH - line_w) // 2
    draw.line([(line_x, y), (line_x + line_w, y)], fill=ENDCARD_ACCENT, width=2)
    y += 40

    # Nichiren quote
    if nichiren_quote:
        quote_wrapped = _wrap_text(f'"{nichiren_quote}"', font_quote, 900)
        for wline in quote_wrapped:
            bbox = draw.textbbox((0, 0), wline, font=font_quote)
            w = bbox[2] - bbox[0]
            draw.text(((VIDEO_WIDTH - w) // 2, y), wline, fill=ENDCARD_TEXT, font=font_quote)
            y += int(ENDCARD_QUOTE_SIZE * 1.5)

        y += 10

    # Source
    if source:
        source_text = f"-- {source}"
        bbox = draw.textbbox((0, 0), source_text, font=font_source)
        w = bbox[2] - bbox[0]
        draw.text(((VIDEO_WIDTH - w) // 2, y), source_text, fill=ENDCARD_DIM, font=font_source)
        y += 60

    # Message / takeaway
    if message:
        y += 20
        msg_wrapped = _wrap_text(message, font_msg, 860)
        for wline in msg_wrapped:
            bbox = draw.textbbox((0, 0), wline, font=font_msg)
            w = bbox[2] - bbox[0]
            draw.text(((VIDEO_WIDTH - w) // 2, y), wline, fill=ENDCARD_DIM, font=font_msg)
            y += int(ENDCARD_MSG_SIZE * 1.5)

    # Bottom decorative line
    y += 40
    draw.line([(line_x, y), (line_x + line_w, y)], fill=ENDCARD_ACCENT, width=2)

    # Branding at bottom
    brand_y = VIDEO_HEIGHT - 200
    brand_text = "The Lotus Lane"
    bbox = draw.textbbox((0, 0), brand_text, font=font_brand)
    w = bbox[2] - bbox[0]
    draw.text(((VIDEO_WIDTH - w) // 2, brand_y), brand_text, fill=ENDCARD_ACCENT, font=font_brand)

    url_font = _load_font(24, bold=False)
    url_text = "tinyurl.com/thelotuslane"
    bbox = draw.textbbox((0, 0), url_text, font=url_font)
    w = bbox[2] - bbox[0]
    draw.text(((VIDEO_WIDTH - w) // 2, brand_y + 45), url_text, fill=ENDCARD_DIM, font=url_font)

    return frame


# ---------------------------------------------------------------------------
# Cross-fade helper
# ---------------------------------------------------------------------------

def _blend_frames(frame_a, frame_b, alpha):
    """Blend two frames. alpha=0.0 -> frame_a, alpha=1.0 -> frame_b."""
    return Image.blend(frame_a, frame_b, alpha)


# ---------------------------------------------------------------------------
# Main video generation
# ---------------------------------------------------------------------------

def check_ffmpeg():
    """Check if ffmpeg is available. Returns path or None.

    Searches PATH first, then common Windows install locations (winget, choco).
    """
    found = shutil.which("ffmpeg")
    if found:
        return found

    # Search common Windows install locations
    if sys.platform == "win32":
        home = Path.home()
        candidates = [
            # winget installs here
            home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages",
            # chocolatey
            Path("C:/ProgramData/chocolatey/bin"),
            # manual installs
            Path("C:/ffmpeg/bin"),
        ]
        for base in candidates:
            if not base.exists():
                continue
            # Search recursively for ffmpeg.exe
            for exe in base.rglob("ffmpeg.exe"):
                return str(exe)

    return None


def generate_video(date_str, fps=FPS_DEFAULT, verbose=True):
    """Generate a YouTube Shorts video for a given strip date.

    Args:
        date_str: Date string like "2026-03-31"
        fps: Frames per second (default 24)
        verbose: Print progress messages

    Returns:
        Path to generated video, or None on failure
    """
    cache_dir = STRIPS_DIR / "cache" / date_str

    # Validate inputs
    script_path = cache_dir / "script.json"
    if not script_path.exists():
        print(f"  ERROR: No script.json found for {date_str}")
        return None

    panel_paths = [cache_dir / f"panel_{i}.png" for i in range(1, 5)]
    missing = [p for p in panel_paths if not p.exists()]
    if missing:
        print(f"  ERROR: Missing panels for {date_str}: {[p.name for p in missing]}")
        return None

    ffmpeg_path = check_ffmpeg()
    if not ffmpeg_path:
        print("  ERROR: ffmpeg not found on PATH.")
        print("  Install ffmpeg:")
        print("    Windows: winget install ffmpeg  OR  choco install ffmpeg")
        print("    macOS:   brew install ffmpeg")
        print("    Linux:   sudo apt install ffmpeg")
        return None

    # Load data
    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    script = data["script"]
    panels_data = script["panels"]
    panel_images = [Image.open(p).convert("RGB") for p in panel_paths]

    if verbose:
        print(f"\n{'='*60}")
        print(f"  The Lotus Lane -- Shorts Video Generator")
        print(f"  Date: {date_str}")
        print(f"  Title: {script.get('title', 'Untitled')}")
        print(f"  FPS: {fps}")
        print(f"{'='*60}\n")

    # Load fonts
    font = _load_font(SUBTITLE_FONT_SIZE)
    font_bold = _load_font(SUBTITLE_FONT_SIZE, bold=True)

    # Create temp directory for frames
    tmp_dir = tempfile.mkdtemp(prefix="lotus_shorts_")
    frame_num = 0

    try:
        # ----- Generate frames for each panel -----
        for panel_idx in range(4):
            panel_img = panel_images[panel_idx]
            dialogue = panels_data[panel_idx].get("dialogue", [])
            total_frames = int(PANEL_DURATION * fps)

            if verbose:
                print(f"  Panel {panel_idx + 1}/4: generating {total_frames} frames...")

            for f_idx in range(total_frames):
                progress = f_idx / max(total_frames - 1, 1)

                # Ken Burns effect
                kb_img = _ken_burns_crop(panel_img, progress)

                # Subtitle fade-in: show dialogue after 0.5s, fade in over 0.3s
                fade_in_start = int(0.5 * fps)
                fade_in_end = int(0.8 * fps)

                if f_idx < fade_in_start:
                    visible_dialogue = []
                else:
                    visible_dialogue = dialogue

                frame = _compose_panel_frame(kb_img, visible_dialogue, font, font_bold)

                # Cross-fade transition: fade OUT last FADE_DURATION seconds
                # (the fade-in of the next panel is handled by blending)
                fade_frames = int(FADE_DURATION * fps)

                if panel_idx < 3 and f_idx >= total_frames - fade_frames:
                    # We're in the fade-out zone of this panel
                    # Generate the first frame of the next panel for blending
                    next_panel_img = panel_images[panel_idx + 1]
                    next_dialogue = panels_data[panel_idx + 1].get("dialogue", [])
                    next_kb = _ken_burns_crop(next_panel_img, 0.0)
                    # Don't show dialogue during transition
                    next_frame = _compose_panel_frame(next_kb, [], font, font_bold)

                    fade_progress = (f_idx - (total_frames - fade_frames)) / fade_frames
                    frame = _blend_frames(frame, next_frame, fade_progress)

                # Save frame
                frame_path = os.path.join(tmp_dir, f"frame_{frame_num:05d}.png")
                frame.save(frame_path, "PNG")
                frame_num += 1

        # ----- Generate end card frames -----
        end_card = _compose_end_card(
            script.get("nichiren_quote", ""),
            script.get("source", ""),
            script.get("message", ""),
            script.get("title", ""),
        )
        end_card_frames = int(END_CARD_DURATION * fps)

        if verbose:
            print(f"  End card: generating {end_card_frames} frames...")

        # Fade in from last panel
        last_panel_img = panel_images[3]
        last_kb = _ken_burns_crop(last_panel_img, 1.0)
        last_dialogue = panels_data[3].get("dialogue", [])
        last_frame = _compose_panel_frame(last_kb, last_dialogue, font, font_bold)
        fade_frames = int(FADE_DURATION * fps)

        for f_idx in range(end_card_frames):
            if f_idx < fade_frames:
                alpha = f_idx / fade_frames
                frame = _blend_frames(last_frame, end_card, alpha)
            else:
                frame = end_card

            frame_path = os.path.join(tmp_dir, f"frame_{frame_num:05d}.png")
            frame.save(frame_path, "PNG")
            frame_num += 1

        # ----- Stitch with ffmpeg -----
        SHORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = SHORTS_DIR / f"{date_str}.mp4"

        total_duration = (4 * PANEL_DURATION) + END_CARD_DURATION
        if verbose:
            print(f"\n  Total frames: {frame_num}")
            print(f"  Duration: ~{total_duration}s")
            print(f"  Stitching with ffmpeg...")

        cmd = [
            ffmpeg_path,
            "-y",                          # Overwrite output
            "-framerate", str(fps),
            "-i", os.path.join(tmp_dir, "frame_%05d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",         # Compatibility
            "-preset", "medium",
            "-crf", "23",                  # Good quality
            "-movflags", "+faststart",     # Web-friendly
            str(output_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            print(f"  ERROR: ffmpeg failed:\n{result.stderr[-500:]}")
            return None

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        if verbose:
            print(f"\n  Video saved: {output_path}")
            print(f"  File size: {file_size_mb:.1f} MB")
            print(f"  Resolution: {VIDEO_WIDTH}x{VIDEO_HEIGHT}")
            print(f"  Duration: ~{total_duration}s")

        return output_path

    finally:
        # Clean up temp frames
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if verbose:
            print(f"  Cleaned up {frame_num} temp frames.")


def generate_all(fps=FPS_DEFAULT):
    """Generate videos for all cached strips that have panels."""
    cache_root = STRIPS_DIR / "cache"
    if not cache_root.exists():
        print("No cache directory found.")
        return

    dates = sorted(
        d.name for d in cache_root.iterdir()
        if d.is_dir() and (d / "script.json").exists() and (d / "panel_1.png").exists()
    )

    if not dates:
        print("No cached strips with panels found.")
        return

    print(f"Found {len(dates)} strips to process.\n")
    results = {"success": [], "failed": []}

    for date_str in dates:
        # Skip if video already exists
        output = SHORTS_DIR / f"{date_str}.mp4"
        if output.exists():
            print(f"  [SKIP] {date_str} -- video already exists")
            results["success"].append(date_str)
            continue

        result = generate_video(date_str, fps=fps)
        if result:
            results["success"].append(date_str)
        else:
            results["failed"].append(date_str)

    print(f"\n{'='*60}")
    print(f"  Results: {len(results['success'])} success, {len(results['failed'])} failed")
    if results["failed"]:
        print(f"  Failed: {', '.join(results['failed'])}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube Shorts videos from cached Lotus Lane comic strips"
    )
    parser.add_argument(
        "--date",
        help="Strip date to generate video for (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="generate_all",
        help="Generate videos for all cached strips",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=FPS_DEFAULT,
        help=f"Frames per second (default: {FPS_DEFAULT})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing videos",
    )

    args = parser.parse_args()

    if not args.date and not args.generate_all:
        parser.error("Specify --date YYYY-MM-DD or --all")

    # Pre-flight check
    if not check_ffmpeg():
        print("ERROR: ffmpeg is not installed or not on PATH.")
        print("\nInstall ffmpeg:")
        print("  Windows: winget install ffmpeg  OR  choco install ffmpeg")
        print("  macOS:   brew install ffmpeg")
        print("  Linux:   sudo apt install ffmpeg")
        sys.exit(1)

    if args.generate_all:
        generate_all(fps=args.fps)
    else:
        if args.force:
            output = SHORTS_DIR / f"{args.date}.mp4"
            if output.exists():
                output.unlink()
        generate_video(args.date, fps=args.fps)


if __name__ == "__main__":
    main()
