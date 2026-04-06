#!/usr/bin/env python3
"""
The Lotus Lane -- YouTube Shorts Video Generator (Audio-First Architecture)

Generates 30-60 second vertical videos (1080x1920) from cached comic strip
panels and scripts. Audio narration is generated FIRST, then video frames
are rendered to match audio timing exactly.

Pipeline:
    1. Generate TTS audio for all dialogue (edge-tts, Indian English voices)
    2. Measure audio durations -> calculate panel timings
    3. Render video frames synchronized to audio
    4. Merge audio + video with ffmpeg

Requirements:
    - ffmpeg (found via WinGet paths or PATH)
    - edge-tts, pydub, Pillow

Usage:
    python pipeline/video_generator.py --date 2026-03-31
    python pipeline/video_generator.py --all
    python pipeline/video_generator.py --date 2026-03-31 --fps 30
"""

import argparse
import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# pydub import deferred until ffmpeg path is configured (see _init_pydub)
AudioSegment = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS_DEFAULT = 24

# Ken Burns
KB_ZOOM_START = 1.0
KB_ZOOM_END = 1.05

# Layout: panel image in top ~65%, dialogue text below in dark band
PANEL_TOP_MARGIN = 60
PANEL_DISPLAY_SIZE = 960  # square panel rendered at this size

# Text area below the panel image
TEXT_AREA_TOP = PANEL_TOP_MARGIN + PANEL_DISPLAY_SIZE + 30  # 30px gap below panel
TEXT_MARGIN_X = 60  # generous margins on each side
TEXT_MAX_WIDTH = VIDEO_WIDTH - 2 * TEXT_MARGIN_X  # 960px

# Font sizes
SPEAKER_FONT_SIZE = 34
DIALOGUE_FONT_SIZE = 32
ENDCARD_QUOTE_SIZE = 38
ENDCARD_SOURCE_SIZE = 26
ENDCARD_BRAND_SIZE = 28
ENDCARD_MSG_SIZE = 30

# Colors
BG_COLOR = (24, 22, 28)
SPEAKER_COLOR = (220, 185, 100)  # Gold/amber for speaker name
DIALOGUE_COLOR = (255, 255, 255)  # White for dialogue
TEXT_BG_COLOR = (15, 13, 18, 200)  # Dark semi-transparent
ENDCARD_BG = (30, 27, 35)
ENDCARD_ACCENT = (200, 170, 100)
ENDCARD_TEXT = (240, 235, 225)
ENDCARD_DIM = (160, 155, 145)

# Timing
SILENCE_BETWEEN_LINES_MS = 500     # 0.5s between dialogue lines in a panel
SILENCE_BETWEEN_PANELS_MS = 800    # 0.8s between panels
PANEL_BUFFER_SECONDS = 1.5         # extra time after audio for reading
MIN_PANEL_DURATION = 5.0           # minimum seconds per panel
END_CARD_DURATION = 4.0            # end card always 4 seconds
FADE_DURATION = 0.5                # cross-fade between panels

# TTS voices
VOICES = {
    "female": "en-IN-NeerjaExpressiveNeural",
    "male": "en-IN-PrabhatNeural",
}

CHAR_GENDER = {
    "meera": "female", "sudha": "female", "priya": "female",
    "arjun": "male", "vikram": "male", "prabhat": "male",
    "hiren": "male", "raj": "male", "amit": "male",
}

PROJECT_ROOT = Path(__file__).parent.parent
STRIPS_DIR = PROJECT_ROOT / "strips"
SHORTS_DIR = PROJECT_ROOT / "shorts"
FONTS_DIR = Path(__file__).parent / "fonts"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _find_ffmpeg():
    """Find ffmpeg binary. Checks PATH then WinGet install paths."""
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


def check_ffmpeg():
    """Public wrapper for _find_ffmpeg. Returns ffmpeg path or None."""
    return _find_ffmpeg()


def _init_pydub():
    """Configure pydub to use the ffmpeg we found, then import AudioSegment."""
    global AudioSegment
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        ffmpeg_dir = str(Path(ffmpeg).parent)
        # Set environment so pydub finds ffmpeg/ffprobe
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    from pydub import AudioSegment as _AS
    AudioSegment = _AS


def _load_font(size, bold=False):
    """Load a font with fallback chain. Prefers ComicNeue."""
    candidates = [
        FONTS_DIR / ("ComicNeue-Bold.ttf" if bold else "ComicNeue-Regular.ttf"),
        FONTS_DIR / ("Nunito-Bold.ttf" if bold else "Nunito-Regular.ttf"),
        Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(str(p), size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


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
            # Handle single word wider than max_width
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _get_voice(speaker_name):
    """Pick a TTS voice based on character name."""
    name_lower = speaker_name.lower().strip()
    gender = CHAR_GENDER.get(name_lower, None)
    if gender:
        return VOICES[gender]
    # Heuristic: common Indian female name endings
    female_hints = ["a", "i", "ee", "ya", "ta", "na", "sha", "ha"]
    if any(name_lower.endswith(h) for h in female_hints):
        return VOICES["female"]
    return VOICES["male"]


def _clean_dialogue_text(text):
    """Remove stage directions in parentheses from dialogue text."""
    cleaned = text.strip()
    # Remove leading parenthetical like "(sighs)" or "(thinking)"
    while cleaned.startswith("("):
        paren_end = cleaned.find(")")
        if paren_end > 0:
            cleaned = cleaned[paren_end + 1:].strip()
        else:
            break
    # Remove trailing ellipsis that might truncate
    return cleaned


def _parse_dialogue_line(line):
    """Parse 'Speaker: (action) text' into (speaker, clean_text)."""
    parts = line.split(": ", 1)
    if len(parts) == 2:
        speaker = parts[0].strip()
        text = _clean_dialogue_text(parts[1])
        # Clean parenthetical from speaker name too
        if "(" in speaker:
            speaker = speaker.split("(")[0].strip()
        return speaker, text
    return None, line.strip()


# ---------------------------------------------------------------------------
# Step 1: Generate TTS audio
# ---------------------------------------------------------------------------

async def _generate_tts_segment(text, voice, output_path, rate="-5%"):
    """Generate a single TTS audio file. Returns True on success."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(str(output_path))
        return True
    except Exception as e:
        print(f"    TTS error: {e}")
        return False


def _make_silence(duration_ms, sample_rate=44100):
    """Create a silent AudioSegment of the given duration."""
    return AudioSegment.silent(duration=duration_ms, frame_rate=sample_rate)


async def generate_all_audio(script_data, tmp_dir, verbose=True):
    """Generate TTS for all dialogue + end card quote.

    Returns:
        dict with:
            - full_audio_path: path to concatenated audio file
            - panel_timings: list of (start_sec, end_sec) for each panel's audio
            - end_card_audio_start: start time of end card narration
            - total_duration_sec: total audio duration
        or None on failure
    """
    panels = script_data.get("panels", [])
    nichiren_quote = script_data.get("nichiren_quote", "")

    # Collect all segments: (panel_idx, speaker, text, voice, audio_path)
    segments = []
    seg_idx = 0

    for panel_idx, panel in enumerate(panels):
        for dialogue_line in panel.get("dialogue", []):
            speaker, text = _parse_dialogue_line(dialogue_line)
            if not text:
                continue
            voice = _get_voice(speaker) if speaker else VOICES["female"]
            seg_path = Path(tmp_dir) / f"seg_{seg_idx:03d}.mp3"
            segments.append({
                "panel_idx": panel_idx,
                "speaker": speaker,
                "text": text,
                "voice": voice,
                "path": seg_path,
                "type": "dialogue",
            })
            seg_idx += 1

    # End card narration (Nichiren quote)
    if nichiren_quote:
        seg_path = Path(tmp_dir) / f"seg_{seg_idx:03d}.mp3"
        segments.append({
            "panel_idx": -1,  # end card
            "speaker": "narrator",
            "text": nichiren_quote,
            "voice": VOICES["female"],
            "path": seg_path,
            "type": "endcard",
        })
        seg_idx += 1

    if not segments:
        print("    No dialogue segments found!")
        return None

    # Generate all TTS segments
    if verbose:
        print(f"  Generating TTS for {len(segments)} dialogue segments...")

    for seg in segments:
        success = await _generate_tts_segment(seg["text"], seg["voice"], seg["path"])
        if not success:
            print(f"    Failed to generate TTS for: {seg['text'][:50]}")
            return None
        # Load audio to get duration
        try:
            audio = AudioSegment.from_file(str(seg["path"]))
            seg["duration_ms"] = len(audio)
            seg["audio"] = audio
        except Exception as e:
            print(f"    Failed to load audio segment: {e}")
            return None

    if verbose:
        for seg in segments:
            dur = seg["duration_ms"] / 1000
            print(f"    [{seg['type']}] {seg.get('speaker', '?')}: {dur:.1f}s - {seg['text'][:60]}")

    # Concatenate audio with proper silences
    full_audio = AudioSegment.empty()
    panel_timings = []  # (start_ms, end_ms) for each panel
    current_ms = 0

    # Group segments by panel
    panel_segments = {}
    endcard_segments = []
    for seg in segments:
        if seg["type"] == "endcard":
            endcard_segments.append(seg)
        else:
            pidx = seg["panel_idx"]
            if pidx not in panel_segments:
                panel_segments[pidx] = []
            panel_segments[pidx].append(seg)

    # Build audio for panels 0-3
    for panel_idx in range(4):
        panel_start_ms = current_ms
        panel_segs = panel_segments.get(panel_idx, [])

        for i, seg in enumerate(panel_segs):
            full_audio += seg["audio"]
            current_ms += seg["duration_ms"]

            # Add silence between dialogue lines within the same panel
            if i < len(panel_segs) - 1:
                silence = _make_silence(SILENCE_BETWEEN_LINES_MS)
                full_audio += silence
                current_ms += SILENCE_BETWEEN_LINES_MS

        panel_end_ms = current_ms
        panel_timings.append((panel_start_ms, panel_end_ms))

        # Add silence between panels (except after last panel)
        if panel_idx < 3:
            silence = _make_silence(SILENCE_BETWEEN_PANELS_MS)
            full_audio += silence
            current_ms += SILENCE_BETWEEN_PANELS_MS

    # Add silence before end card narration
    endcard_audio_start_ms = current_ms
    if endcard_segments:
        silence = _make_silence(SILENCE_BETWEEN_PANELS_MS)
        full_audio += silence
        current_ms += SILENCE_BETWEEN_PANELS_MS
        endcard_audio_start_ms = current_ms

        for seg in endcard_segments:
            full_audio += seg["audio"]
            current_ms += seg["duration_ms"]

    # Pad end with a bit of silence
    full_audio += _make_silence(500)
    current_ms += 500

    # Export full audio
    full_audio_path = Path(tmp_dir) / "full_narration.m4a"
    full_audio.export(str(full_audio_path), format="ipod", bitrate="128k")

    total_duration_sec = current_ms / 1000.0
    if verbose:
        print(f"\n  Total audio duration: {total_duration_sec:.1f}s")
        for i, (s, e) in enumerate(panel_timings):
            print(f"    Panel {i+1}: {s/1000:.1f}s - {e/1000:.1f}s ({(e-s)/1000:.1f}s)")
        print(f"    End card narration starts: {endcard_audio_start_ms/1000:.1f}s")

    return {
        "full_audio_path": full_audio_path,
        "panel_timings": panel_timings,  # list of (start_ms, end_ms)
        "endcard_audio_start_ms": endcard_audio_start_ms,
        "total_duration_ms": current_ms,
    }


# ---------------------------------------------------------------------------
# Step 2: Calculate panel durations from audio
# ---------------------------------------------------------------------------

def calculate_video_timings(audio_info):
    """Calculate how long each panel should display based on audio timings.

    Returns:
        list of dicts with panel_idx, start_sec, duration_sec, audio_start_sec, audio_end_sec
        + end_card entry
    """
    panel_timings = audio_info["panel_timings"]
    endcard_audio_start_ms = audio_info["endcard_audio_start_ms"]
    total_audio_ms = audio_info["total_duration_ms"]

    video_sections = []
    current_video_sec = 0.0

    for i, (audio_start_ms, audio_end_ms) in enumerate(panel_timings):
        audio_dur_sec = (audio_end_ms - audio_start_ms) / 1000.0
        # Panel stays on screen for audio duration + buffer, minimum MIN_PANEL_DURATION
        panel_dur = max(audio_dur_sec + PANEL_BUFFER_SECONDS, MIN_PANEL_DURATION)

        video_sections.append({
            "type": "panel",
            "panel_idx": i,
            "video_start_sec": current_video_sec,
            "duration_sec": panel_dur,
            "audio_start_ms": audio_start_ms,
            "audio_end_ms": audio_end_ms,
        })
        current_video_sec += panel_dur

    # End card
    endcard_audio_dur = (total_audio_ms - endcard_audio_start_ms) / 1000.0
    endcard_dur = max(END_CARD_DURATION, endcard_audio_dur + 1.0)
    video_sections.append({
        "type": "endcard",
        "panel_idx": -1,
        "video_start_sec": current_video_sec,
        "duration_sec": endcard_dur,
        "audio_start_ms": endcard_audio_start_ms,
        "audio_end_ms": total_audio_ms,
    })
    current_video_sec += endcard_dur

    return video_sections, current_video_sec


# ---------------------------------------------------------------------------
# Step 3: Render video frames
# ---------------------------------------------------------------------------

def _ken_burns_crop(panel_img, progress):
    """Apply a gentle zoom-in Ken Burns effect to a panel image."""
    w, h = panel_img.size
    t = 0.5 - 0.5 * math.cos(math.pi * progress)
    zoom = KB_ZOOM_START + (KB_ZOOM_END - KB_ZOOM_START) * t

    crop_w = w / zoom
    crop_h = h / zoom
    drift_x = 0.5 + 0.02 * t
    drift_y = 0.5 - 0.01 * t
    left = (w - crop_w) * drift_x
    top = (h - crop_h) * drift_y
    right = left + crop_w
    bottom = top + crop_h

    cropped = panel_img.crop((int(left), int(top), int(right), int(bottom)))
    return cropped.resize((PANEL_DISPLAY_SIZE, PANEL_DISPLAY_SIZE), Image.LANCZOS)


def _compose_panel_frame(panel_img_kb, dialogue_lines, font_speaker, font_dialogue,
                        prerendered_text=None):
    """Compose a single video frame: dark bg + panel image in top area + text below.

    If prerendered_text (PIL Image) is provided, it is pasted directly instead of
    rendering text with Pillow. This is the Playwright path — much better typography.
    """
    frame = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (*BG_COLOR, 255))

    # Place panel image centered, near top
    panel_x = (VIDEO_WIDTH - PANEL_DISPLAY_SIZE) // 2
    panel_rgba = panel_img_kb.convert("RGBA")
    frame.paste(panel_rgba, (panel_x, PANEL_TOP_MARGIN))

    if prerendered_text is not None:
        # Paste the pre-rendered Playwright text overlay
        text_img = prerendered_text.convert("RGBA")
        # Center horizontally, place at TEXT_AREA_TOP
        tx = (VIDEO_WIDTH - text_img.width) // 2
        frame.paste(text_img, (tx, TEXT_AREA_TOP), text_img)
        return frame.convert("RGB")

    if not dialogue_lines:
        return frame.convert("RGB")

    # Fallback: Pillow text rendering (kept for backward compatibility)
    rendered_lines = []
    for line in dialogue_lines:
        speaker, text = _parse_dialogue_line(line)
        if not text:
            continue
        if speaker:
            speaker_prefix = f"{speaker}: "
            sp_bbox = font_speaker.getbbox(speaker_prefix)
            speaker_width = sp_bbox[2] - sp_bbox[0]
        else:
            speaker_prefix = ""
            speaker_width = 0

        first_line_width = TEXT_MAX_WIDTH - speaker_width
        remaining_width = TEXT_MAX_WIDTH
        wrapped = _wrap_text(text, font_dialogue, first_line_width)
        if len(wrapped) > 1:
            words = text.split()
            lines_out = []
            current = ""
            tmp_img = Image.new("RGB", (1, 1))
            tmp_draw = ImageDraw.Draw(tmp_img)
            is_first = True
            max_w = first_line_width if is_first else remaining_width
            for word in words:
                test_str = f"{current} {word}".strip()
                bbox = tmp_draw.textbbox((0, 0), test_str, font=font_dialogue)
                w = bbox[2] - bbox[0]
                if w <= max_w:
                    current = test_str
                else:
                    if current:
                        lines_out.append(current)
                    current = word
                    is_first = False
                    max_w = remaining_width
            if current:
                lines_out.append(current)
            wrapped = lines_out if lines_out else [text]
        for i, wline in enumerate(wrapped):
            rendered_lines.append((speaker if i == 0 else None, wline))

    if not rendered_lines:
        return frame.convert("RGB")

    line_height = DIALOGUE_FONT_SIZE + 14
    total_text_height = len(rendered_lines) * line_height + 20
    text_band_y = TEXT_AREA_TOP
    text_band_height = total_text_height

    overlay = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    band_left = TEXT_MARGIN_X - 15
    band_right = VIDEO_WIDTH - TEXT_MARGIN_X + 15
    overlay_draw.rounded_rectangle(
        [band_left, text_band_y - 10, band_right, text_band_y + text_band_height + 10],
        radius=16, fill=TEXT_BG_COLOR,
    )
    frame = Image.alpha_composite(frame, overlay)

    draw = ImageDraw.Draw(frame)
    text_y = text_band_y + 10
    for speaker, wline in rendered_lines:
        x = TEXT_MARGIN_X
        if speaker:
            speaker_text = f"{speaker}: "
            draw.text((x, text_y), speaker_text, fill=SPEAKER_COLOR, font=font_speaker)
            sp_bbox = draw.textbbox((0, 0), speaker_text, font=font_speaker)
            x += sp_bbox[2] - sp_bbox[0]
        draw.text((x, text_y), wline, fill=DIALOGUE_COLOR, font=font_dialogue)
        text_y += line_height

    return frame.convert("RGB")


def _compose_end_card(nichiren_quote, source, message, title):
    """Create the branded end card frame with Nichiren quote.

    Uses Playwright HTML/CSS rendering for beautiful typography.
    Falls back to Pillow if Playwright is unavailable.
    """
    try:
        try:
            from pipeline.playwright_renderer import render_video_endcard
        except ImportError:
            from playwright_renderer import render_video_endcard
        return render_video_endcard(
            {"nichiren_quote": nichiren_quote, "source": source,
             "message": message, "title": title},
            VIDEO_WIDTH, VIDEO_HEIGHT,
        )
    except Exception:
        pass

    # Fallback: Pillow rendering
    frame = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), ENDCARD_BG)
    draw = ImageDraw.Draw(frame)
    font_quote = _load_font(ENDCARD_QUOTE_SIZE, bold=False)
    font_source = _load_font(ENDCARD_SOURCE_SIZE, bold=False)
    font_brand = _load_font(ENDCARD_BRAND_SIZE, bold=True)
    font_msg = _load_font(ENDCARD_MSG_SIZE, bold=False)

    y = 500
    line_w = 200
    line_x = (VIDEO_WIDTH - line_w) // 2
    draw.line([(line_x, y), (line_x + line_w, y)], fill=ENDCARD_ACCENT, width=2)
    y += 40

    if nichiren_quote:
        quote_wrapped = _wrap_text(f'"{nichiren_quote}"', font_quote, 900)
        for wline in quote_wrapped:
            bbox = draw.textbbox((0, 0), wline, font=font_quote)
            w = bbox[2] - bbox[0]
            draw.text(((VIDEO_WIDTH - w) // 2, y), wline, fill=ENDCARD_TEXT, font=font_quote)
            y += int(ENDCARD_QUOTE_SIZE * 1.5)
        y += 10

    if source:
        source_text = f"-- {source}"
        bbox = draw.textbbox((0, 0), source_text, font=font_source)
        w = bbox[2] - bbox[0]
        draw.text(((VIDEO_WIDTH - w) // 2, y), source_text, fill=ENDCARD_DIM, font=font_source)
        y += 60

    if message:
        y += 20
        msg_wrapped = _wrap_text(message, font_msg, 860)
        for wline in msg_wrapped:
            bbox = draw.textbbox((0, 0), wline, font=font_msg)
            w = bbox[2] - bbox[0]
            draw.text(((VIDEO_WIDTH - w) // 2, y), wline, fill=ENDCARD_DIM, font=font_msg)
            y += int(ENDCARD_MSG_SIZE * 1.5)

    y += 40
    draw.line([(line_x, y), (line_x + line_w, y)], fill=ENDCARD_ACCENT, width=2)

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


def _blend_frames(frame_a, frame_b, alpha):
    """Blend two frames. alpha=0.0 -> frame_a, alpha=1.0 -> frame_b."""
    return Image.blend(frame_a, frame_b, alpha)


def render_video_frames(script_data, panel_images, video_sections, total_video_sec,
                         fps, tmp_dir, verbose=True):
    """Render all video frames to disk, synchronized with audio timings.

    Returns:
        Number of frames generated
    """
    font_speaker = _load_font(SPEAKER_FONT_SIZE, bold=True)
    font_dialogue = _load_font(DIALOGUE_FONT_SIZE, bold=False)
    panels_data = script_data["panels"]

    total_frames = int(total_video_sec * fps)
    fade_frames = int(FADE_DURATION * fps)
    frame_num = 0

    # Pre-render dialogue overlays via Playwright (once per panel, reused per frame)
    prerendered_overlays = {}
    try:
        # Support running as script or module
        try:
            from pipeline.playwright_renderer import render_video_dialogue, PlaywrightBrowser
        except ImportError:
            from playwright_renderer import render_video_dialogue, PlaywrightBrowser
        if verbose:
            print("  Pre-rendering dialogue overlays with Playwright...")
        with PlaywrightBrowser() as browser:
            for pidx, pdata in enumerate(panels_data):
                dialogue = pdata.get("dialogue", [])
                if dialogue:
                    prerendered_overlays[pidx] = render_video_dialogue(
                        dialogue, VIDEO_WIDTH, browser
                    )
        if verbose:
            print(f"  Pre-rendered {len(prerendered_overlays)} dialogue overlays")
    except Exception as e:
        if verbose:
            print(f"  Playwright text rendering failed ({e}), falling back to Pillow")

    # Pre-compose end card (static)
    end_card = _compose_end_card(
        script_data.get("nichiren_quote", ""),
        script_data.get("source", ""),
        script_data.get("message", ""),
        script_data.get("title", ""),
    )

    for section_idx, section in enumerate(video_sections):
        section_frames = int(section["duration_sec"] * fps)

        if section["type"] == "panel":
            pidx = section["panel_idx"]
            panel_img = panel_images[pidx]
            dialogue = panels_data[pidx].get("dialogue", [])
            prerendered_text = prerendered_overlays.get(pidx)

            if verbose:
                print(f"  Panel {pidx+1}/4: {section_frames} frames ({section['duration_sec']:.1f}s)")

            for f_idx in range(section_frames):
                progress = f_idx / max(section_frames - 1, 1)

                # Ken Burns
                kb_img = _ken_burns_crop(panel_img, progress)

                # Show dialogue after a brief delay (0.3s)
                delay_frames = int(0.3 * fps)
                show_text = f_idx >= delay_frames

                frame = _compose_panel_frame(
                    kb_img,
                    dialogue if show_text and not prerendered_text else [],
                    font_speaker, font_dialogue,
                    prerendered_text=prerendered_text if show_text else None,
                )

                # Cross-fade to next section in last FADE_DURATION seconds
                if section_idx < len(video_sections) - 1 and f_idx >= section_frames - fade_frames:
                    next_section = video_sections[section_idx + 1]
                    if next_section["type"] == "panel":
                        next_pidx = next_section["panel_idx"]
                        next_kb = _ken_burns_crop(panel_images[next_pidx], 0.0)
                        next_frame = _compose_panel_frame(next_kb, [], font_speaker, font_dialogue)
                    else:
                        next_frame = end_card

                    fade_progress = (f_idx - (section_frames - fade_frames)) / fade_frames
                    frame = _blend_frames(frame, next_frame, fade_progress)

                frame_path = os.path.join(tmp_dir, f"frame_{frame_num:05d}.png")
                frame.save(frame_path, "PNG")
                frame_num += 1

        elif section["type"] == "endcard":
            if verbose:
                print(f"  End card: {section_frames} frames ({section['duration_sec']:.1f}s)")

            for f_idx in range(section_frames):
                frame_path = os.path.join(tmp_dir, f"frame_{frame_num:05d}.png")
                end_card.save(frame_path, "PNG")
                frame_num += 1

    return frame_num


# ---------------------------------------------------------------------------
# Step 4: Merge audio + video with ffmpeg
# ---------------------------------------------------------------------------

def stitch_video(tmp_dir, audio_path, output_path, fps, total_video_sec, ffmpeg_path, verbose=True):
    """Stitch frames into video and merge with audio using ffmpeg.

    Uses a two-pass approach:
    1. Encode frames to silent video
    2. Merge video + audio
    """
    SHORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Single ffmpeg command: frames + audio -> final video
    cmd = [
        ffmpeg_path,
        "-y",
        "-framerate", str(fps),
        "-i", os.path.join(tmp_dir, "frame_%05d.png"),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]

    if verbose:
        print(f"\n  Stitching with ffmpeg...")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        print(f"  ERROR: ffmpeg failed:\n{result.stderr[-800:]}")
        return False

    return True


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def generate_video(date_str, fps=FPS_DEFAULT, verbose=True):
    """Generate a YouTube Shorts video with synchronized TTS narration.

    Audio-first pipeline:
    1. Generate TTS audio for all dialogue
    2. Calculate panel durations from audio lengths
    3. Render video frames matched to audio timing
    4. Merge audio + video with ffmpeg

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

    # Initialize pydub with correct ffmpeg path (lazy import, also sets PATH)
    _init_pydub()

    ffmpeg_path = _find_ffmpeg()
    if not ffmpeg_path:
        print("  ERROR: ffmpeg not found.")
        print("  Install: winget install ffmpeg  OR  choco install ffmpeg")
        return None

    # Load data
    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    script = data["script"]
    panel_images = [Image.open(p).convert("RGB") for p in panel_paths]

    if verbose:
        print(f"\n{'='*60}")
        print(f"  The Lotus Lane -- Audio-First Video Generator")
        print(f"  Date: {date_str}")
        print(f"  Title: {script.get('title', 'Untitled')}")
        print(f"  FPS: {fps}")
        print(f"{'='*60}\n")

    tmp_dir = tempfile.mkdtemp(prefix="lotus_shorts_")

    try:
        # ----- Step 1: Generate TTS audio -----
        if verbose:
            print("  [Step 1] Generating TTS audio...")

        audio_info = asyncio.run(generate_all_audio(script, tmp_dir, verbose=verbose))
        if not audio_info:
            print("  ERROR: Audio generation failed")
            return None

        # ----- Step 2: Calculate panel durations -----
        if verbose:
            print("\n  [Step 2] Calculating panel timings from audio...")

        video_sections, total_video_sec = calculate_video_timings(audio_info)

        if verbose:
            print(f"\n  Video sections:")
            for sec in video_sections:
                stype = sec['type']
                dur = sec['duration_sec']
                print(f"    {stype} (panel {sec['panel_idx']+1 if stype == 'panel' else 'end'}): {dur:.1f}s")
            print(f"  Total video duration: {total_video_sec:.1f}s")

        # ----- Step 3: Render video frames -----
        if verbose:
            print(f"\n  [Step 3] Rendering {int(total_video_sec * fps)} frames...")

        frame_count = render_video_frames(
            script, panel_images, video_sections, total_video_sec,
            fps, tmp_dir, verbose=verbose,
        )

        # ----- Step 4: Merge audio + video -----
        if verbose:
            print(f"\n  [Step 4] Merging audio + video...")

        output_path = SHORTS_DIR / f"{date_str}.mp4"
        success = stitch_video(
            tmp_dir, audio_info["full_audio_path"], output_path,
            fps, total_video_sec, ffmpeg_path, verbose=verbose,
        )

        if not success:
            return None

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        if verbose:
            print(f"\n  Video saved: {output_path}")
            print(f"  File size: {file_size_mb:.1f} MB")
            print(f"  Resolution: {VIDEO_WIDTH}x{VIDEO_HEIGHT}")
            print(f"  Duration: ~{total_video_sec:.1f}s")

        return output_path

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if verbose:
            print(f"  Cleaned up temp directory.")


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
        output = SHORTS_DIR / f"{date_str}.mp4"
        if output.exists():
            print(f"  [SKIP] {date_str} -- video already exists (use --force to overwrite)")
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
        description="Generate YouTube Shorts videos with synchronized TTS narration"
    )
    parser.add_argument("--date", help="Strip date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", dest="generate_all",
                        help="Generate videos for all cached strips")
    parser.add_argument("--fps", type=int, default=FPS_DEFAULT,
                        help=f"Frames per second (default: {FPS_DEFAULT})")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing videos")

    args = parser.parse_args()

    if not args.date and not args.generate_all:
        parser.error("Specify --date YYYY-MM-DD or --all")

    if not _find_ffmpeg():
        print("ERROR: ffmpeg not found.")
        print("Install: winget install ffmpeg  OR  choco install ffmpeg")
        sys.exit(1)

    if args.generate_all:
        generate_all(fps=args.fps)
    else:
        if args.force:
            output = SHORTS_DIR / f"{args.date}.mp4"
            if output.exists():
                output.unlink()
            # Also remove old narrated version if it exists
            narrated = SHORTS_DIR / f"{args.date}_narrated.mp4"
            if narrated.exists():
                narrated.unlink()
        generate_video(args.date, fps=args.fps)


if __name__ == "__main__":
    main()
