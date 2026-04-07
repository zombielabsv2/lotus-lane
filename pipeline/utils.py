"""Shared utilities for The Lotus Lane pipeline.

Provides atomic file operations and common helpers used across
upload scripts (YouTube, Pinterest, Instagram, Tumblr).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

STRIPS_JSON = Path(__file__).parent.parent / "strips.json"


def safe_update_strips(update_fn):
    """Atomically read-modify-write strips.json.

    1. Reads strips.json
    2. Calls update_fn(data) to modify the list in-place (or return new list)
    3. Writes to strips.json.tmp first
    4. Renames tmp to strips.json (atomic on most filesystems)

    Args:
        update_fn: callable that takes the strips list and modifies it in-place.
                   May optionally return a new list to replace the original.

    Returns:
        The (possibly modified) strips list.
    """
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    result = update_fn(strips)
    if result is not None:
        strips = result

    tmp_path = STRIPS_JSON.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(strips, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Atomic rename (on Windows, need to remove target first)
    if os.name == "nt" and STRIPS_JSON.exists():
        os.replace(str(tmp_path), str(STRIPS_JSON))
    else:
        os.replace(str(tmp_path), str(STRIPS_JSON))

    return strips


def update_distribution_status(date_str, platform, status, platform_id=None, error=None):
    """Update the distribution status for a strip on a given platform.

    Args:
        date_str: Strip date (e.g., "2026-04-07")
        platform: Platform name ("youtube", "pinterest", "instagram", "tumblr")
        status: Status string ("uploaded", "failed", "pending")
        platform_id: Optional platform-specific ID (video ID, pin ID, etc.)
        error: Optional error message for failed uploads
    """
    def _update(strips):
        for s in strips:
            if s["date"] == date_str:
                if "distribution" not in s:
                    s["distribution"] = {}
                entry = {"status": status}
                if platform_id:
                    entry["id"] = platform_id
                if error:
                    entry["error"] = error
                if status == "uploaded":
                    entry["uploaded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                s["distribution"][platform] = entry
                break

    safe_update_strips(_update)


def get_strip_data(date_str):
    """Get strip metadata from strips.json."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    for s in strips:
        if s["date"] == date_str:
            return s
    return None


def get_latest_date():
    """Get the most recent strip date."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    strips.sort(key=lambda s: s["date"], reverse=True)
    return strips[0]["date"] if strips else None
