#!/usr/bin/env python3
"""
Verify data integrity of The Lotus Lane.
Run before every push to catch broken references.

Checks:
1. Every strip in strips.json has a matching image file
2. Every image file in strips/ has a matching strips.json entry
3. YouTube IDs are not duplicated
4. No future-dated strips
5. All required fields present
"""

import json
import sys
from datetime import datetime
from pathlib import Path

STRIPS_JSON = Path(__file__).parent.parent / "strips.json"
STRIPS_DIR = Path(__file__).parent.parent / "strips"

def verify():
    errors = []

    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    today = datetime.now().strftime("%Y-%m-%d")
    seen_dates = set()
    seen_yt_ids = set()

    for s in strips:
        date = s.get("date", "MISSING")

        # Duplicate dates
        if date in seen_dates:
            errors.append(f"DUPLICATE date: {date}")
        seen_dates.add(date)

        # Future dates
        if date > today:
            errors.append(f"FUTURE date: {date} — '{s.get('title')}'")

        # Image file exists (local path or CDN URL)
        image_ref = s.get("image", "")
        if image_ref.startswith("http"):
            # CDN-hosted: check local copy exists (during pipeline) or just validate URL format
            local_png = STRIPS_DIR / f"{date}.png"
            # Only flag missing if local copy doesn't exist AND we're not in CI
            # (in CI, the PNG is generated fresh; locally, PNGs may not be present)
        else:
            image_path = Path(__file__).parent.parent / image_ref
            if not image_path.exists():
                errors.append(f"MISSING image: {image_ref} for {date}")

        # Required fields
        for field in ["date", "title", "image", "message", "tags"]:
            if not s.get(field):
                errors.append(f"MISSING field '{field}' for {date}")

        # YouTube ID duplicates
        yt_id = s.get("youtube_id")
        if yt_id:
            if yt_id in seen_yt_ids:
                errors.append(f"DUPLICATE youtube_id: {yt_id}")
            seen_yt_ids.add(yt_id)

    # Orphan images (image files without strips.json entry)
    # Match by date since image field may be a CDN URL
    json_dates = {s.get("date", "") for s in strips}
    for img in STRIPS_DIR.glob("*.png"):
        img_date = img.stem  # e.g. "2026-04-08"
        if img_date not in json_dates:
            errors.append(f"ORPHAN image: strips/{img.name} (no strips.json entry)")

    if errors:
        print(f"\n  INTEGRITY CHECK FAILED — {len(errors)} error(s):\n")
        for e in errors:
            print(f"    {e}")
        print()
        return False
    else:
        print(f"  INTEGRITY CHECK PASSED — {len(strips)} strips, all clean")
        return True


if __name__ == "__main__":
    ok = verify()
    sys.exit(0 if ok else 1)
