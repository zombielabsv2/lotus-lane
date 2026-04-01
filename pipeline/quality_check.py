"""
Quality control checks for generated comic strip panel images.

Two-tier approach:
1. Pillow-based checks (instant, free): resolution, aspect ratio, blank/dark detection
2. GPT-4o-mini vision check (~Rs. 0.002/strip): detects unwanted text baked into images

If a panel fails QC, the generator retries with a stronger prompt (up to 3 attempts).
"""

import base64
import os
from io import BytesIO

import httpx
from PIL import Image, ImageStat


# --- Tier 1: Pillow-based checks (instant, free) ---

def check_resolution(img, min_size=256):
    """Reject images that are too small."""
    if img.width < min_size or img.height < min_size:
        return False, f"Image too small: {img.width}x{img.height} (min {min_size})"
    return True, None


def check_blank_or_dark(img):
    """Reject mostly-blank or mostly-dark images."""
    stat = ImageStat.Stat(img.convert("RGB"))
    means = stat.mean  # [R, G, B] channel means
    stddevs = stat.stddev

    avg_mean = sum(means) / 3
    avg_stddev = sum(stddevs) / 3

    if avg_mean > 240 and avg_stddev < 15:
        return False, f"Image is mostly blank (mean={avg_mean:.0f}, stddev={avg_stddev:.0f})"

    if avg_mean < 20 and avg_stddev < 15:
        return False, f"Image is mostly dark (mean={avg_mean:.0f}, stddev={avg_stddev:.0f})"

    return True, None


def check_low_contrast(img):
    """Reject washed-out or low-contrast images."""
    stat = ImageStat.Stat(img.convert("RGB"))
    avg_stddev = sum(stat.stddev) / 3

    if avg_stddev < 20:
        return False, f"Image has very low contrast (stddev={avg_stddev:.0f})"

    return True, None


def check_corruption(img):
    """Verify the image can be fully loaded without errors."""
    try:
        img.load()
        return True, None
    except Exception as e:
        return False, f"Image is corrupt: {e}"


def run_pillow_checks(img):
    """Run all Pillow-based checks. Returns (passed, list_of_issues)."""
    checks = [
        check_corruption,
        check_resolution,
        check_blank_or_dark,
        check_low_contrast,
    ]

    issues = []
    for check in checks:
        passed, issue = check(img)
        if not passed:
            issues.append(issue)

    return len(issues) == 0, issues


# --- Tier 2: GPT-4o-mini vision text detection (~Rs. 0.002/strip) ---

def check_text_in_image(img, openai_api_key):
    """Use GPT-4o-mini vision to detect unwanted text in a panel image.

    Returns (has_text: bool, description: str)
    Cost: ~$0.00002 per image (~Rs. 0.002)
    """
    # Convert image to base64
    buffer = BytesIO()
    img_rgb = img.convert("RGB")
    img_rgb.save(buffer, format="JPEG", quality=80)
    b64 = base64.b64encode(buffer.getvalue()).decode()

    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 50,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Does this comic panel image contain ANY visible text, "
                                "words, letters, titles, captions, or watermarks? "
                                "Answer ONLY 'YES' or 'NO'."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "low",
                            },
                        },
                    ],
                }
            ],
        },
        timeout=30,
    )
    response.raise_for_status()
    answer = response.json()["choices"][0]["message"]["content"].strip().upper()

    has_text = "YES" in answer
    return has_text, answer


def run_full_qc(img, openai_api_key, panel_num=None):
    """Run all QC checks on a panel image.

    Returns (passed: bool, issues: list[str])
    """
    label = f"Panel {panel_num}" if panel_num else "Image"
    issues = []

    # Tier 1: Pillow checks (instant, free)
    pillow_ok, pillow_issues = run_pillow_checks(img)
    if not pillow_ok:
        issues.extend(pillow_issues)
        return False, issues

    # Tier 2: Vision text detection
    try:
        has_text, answer = check_text_in_image(img, openai_api_key)
        if has_text:
            issues.append(f"{label}: Unwanted text detected in image")
    except Exception as e:
        # Don't block on QC API failure — log but pass
        print(f"    [QC WARNING] Vision check failed for {label}: {e}")

    return len(issues) == 0, issues
