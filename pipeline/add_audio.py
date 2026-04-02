#!/usr/bin/env python3
"""
Add Indian English TTS narration to YouTube Shorts videos.
Uses edge-tts (free Microsoft voices) — no API key needed.

Voices:
  - en-IN-NeerjaExpressiveNeural (female, expressive)
  - en-IN-PrabhatNeural (male)

Usage:
    python pipeline/add_audio.py --date 2026-03-31
    python pipeline/add_audio.py --all
"""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts

STRIPS_DIR = Path(__file__).parent.parent / "strips"
SHORTS_DIR = Path(__file__).parent.parent / "shorts"

# Find ffmpeg
def _find_ffmpeg():
    """Find ffmpeg binary, checking WinGet install paths."""
    import shutil
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    # WinGet install path
    winget_path = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    for p in winget_path.rglob("ffmpeg.exe"):
        return str(p)
    return "ffmpeg"  # Hope for the best

FFMPEG = _find_ffmpeg()
FFPROBE = str(Path(FFMPEG).parent / "ffprobe") if FFMPEG != "ffmpeg" else "ffprobe"

# Voice mapping — alternate or assign by character
VOICES = {
    "female": "en-IN-NeerjaExpressiveNeural",
    "male": "en-IN-PrabhatNeural",
}

# Known character genders (core cast)
CHAR_GENDER = {
    "meera": "female", "sudha": "female", "priya": "female",
    "arjun": "male", "vikram": "male", "prabhat": "male",
    "hiren": "male", "raj": "male", "amit": "male",
}


def get_voice(speaker_name):
    """Pick a voice based on character name."""
    name_lower = speaker_name.lower().strip()
    gender = CHAR_GENDER.get(name_lower, None)
    if gender:
        return VOICES[gender]
    # Guess: common Indian female names
    female_hints = ["a", "i", "ee", "ya", "ta", "na", "sha", "ha"]
    if any(name_lower.endswith(h) for h in female_hints):
        return VOICES["female"]
    return VOICES["male"]


def build_narration_script(script_data):
    """Build a narration script from the strip's dialogue."""
    lines = []

    for panel in script_data.get("panels", []):
        for dialogue_line in panel.get("dialogue", []):
            parts = dialogue_line.split(": ", 1)
            if len(parts) == 2:
                speaker, text = parts
                # Clean up stage directions
                speaker = speaker.strip()
                text = text.strip()
                if text.startswith("("):
                    # It's a stage direction like "(thinking) ..."
                    paren_end = text.find(")")
                    if paren_end > 0:
                        text = text[paren_end + 1:].strip()
                if text:
                    lines.append({"speaker": speaker, "text": text, "voice": get_voice(speaker)})
            else:
                lines.append({"speaker": "", "text": dialogue_line, "voice": VOICES["female"]})

    # Add the Nichiren quote at the end
    quote = script_data.get("nichiren_quote", "")
    if quote:
        lines.append({
            "speaker": "narrator",
            "text": quote,
            "voice": VOICES["female"],
        })

    return lines


async def generate_audio_segment(text, voice, output_path):
    """Generate a single TTS audio segment."""
    communicate = edge_tts.Communicate(text, voice, rate="-5%")
    await communicate.save(str(output_path))


async def generate_narration(script_data, output_dir):
    """Generate all audio segments for a strip."""
    lines = build_narration_script(script_data)
    segment_files = []

    for i, line in enumerate(lines):
        seg_path = output_dir / f"seg_{i:03d}.mp3"
        try:
            await generate_audio_segment(line["text"], line["voice"], seg_path)
            segment_files.append(seg_path)
        except Exception as e:
            print(f"    TTS error for segment {i}: {e}")

    return segment_files


def concat_audio_segments(segment_files, output_path, silence_gap=0.8):
    """Concatenate audio segments with silence gaps using ffmpeg."""
    if not segment_files:
        return False

    # Build ffmpeg filter to add silence between segments
    inputs = []
    filter_parts = []

    for i, seg in enumerate(segment_files):
        inputs.extend(["-i", str(seg)])

    # Create silence
    n = len(segment_files)
    filter_str = ""
    for i in range(n):
        filter_str += f"[{i}:a]aresample=44100[a{i}];"

    # Add silence between segments
    concat_inputs = ""
    for i in range(n):
        # Add segment
        concat_inputs += f"[a{i}]"
        # Add silence gap (except after last)
        if i < n - 1:
            filter_str += f"aevalsrc=0:d={silence_gap}[sil{i}];"
            concat_inputs += f"[sil{i}]"

    total_parts = n + (n - 1)  # segments + silences
    filter_str += f"{concat_inputs}concat=n={total_parts}:v=0:a=1[out]"

    cmd = [FFMPEG, "-y"] + inputs + [
        "-filter_complex", filter_str,
        "-map", "[out]",
        "-acodec", "aac",
        "-b:a", "128k",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ffmpeg concat error: {result.stderr[:200]}")
        return False
    return True


def merge_audio_video(video_path, audio_path, output_path):
    """Merge audio track with video, adjusting audio length to match video."""
    # Get video duration
    probe = subprocess.run(
        [FFPROBE, "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    video_duration = float(probe.stdout.strip()) if probe.stdout.strip() else 40.0

    cmd = [
        FFMPEG, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def process_date(date_str, force=False):
    """Add audio to a video for a given date."""
    cache_dir = STRIPS_DIR / "cache" / date_str
    script_path = cache_dir / "script.json"
    video_path = SHORTS_DIR / f"{date_str}.mp4"
    output_path = SHORTS_DIR / f"{date_str}_narrated.mp4"

    if output_path.exists() and not force:
        print(f"  [{date_str}] Narrated video already exists, skipping")
        return

    if not script_path.exists():
        print(f"  [{date_str}] No script.json found")
        return

    if not video_path.exists():
        print(f"  [{date_str}] No video found — generate video first")
        return

    print(f"  [{date_str}] Generating narration...")

    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    script_data = data.get("script", data)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Generate TTS segments
        segments = asyncio.run(generate_narration(script_data, tmpdir))
        if not segments:
            print(f"  [{date_str}] No audio segments generated")
            return

        print(f"  [{date_str}] Generated {len(segments)} audio segments")

        # Concat segments
        full_audio = tmpdir / "narration.m4a"
        if not concat_audio_segments(segments, full_audio):
            print(f"  [{date_str}] Failed to concat audio")
            return

        # Merge with video
        if merge_audio_video(video_path, full_audio, output_path):
            print(f"  [{date_str}] Done! {output_path}")
        else:
            print(f"  [{date_str}] Failed to merge audio+video")


def main():
    parser = argparse.ArgumentParser(description="Add TTS narration to Lotus Lane shorts")
    parser.add_argument("--date", help="Date of the strip (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Process all cached strips")
    parser.add_argument("--force", action="store_true", help="Overwrite existing narrated videos")
    args = parser.parse_args()

    if args.all:
        cache_root = STRIPS_DIR / "cache"
        dates = sorted(d.name for d in cache_root.iterdir() if d.is_dir())
        for date_str in dates:
            process_date(date_str, force=args.force)
    elif args.date:
        process_date(args.date, force=args.force)
    else:
        print("Specify --date or --all")


if __name__ == "__main__":
    main()
