#!/usr/bin/env python3
"""Wisdom pool monitor — alert before the podcast runs out of content.

The daily podcast cron (`generate-podcast.yml`) picks the first wisdom slug
under `wisdom/cache/*.json` that is not yet a row in Supabase
`podcast_episodes`. When the unpublished buffer runs low, the podcast will
eventually have nothing left to publish.

This script is a MONITOR ONLY. It does NOT generate content and never calls
the Anthropic API. Lotus Lane wisdom essays are authored in Claude Code (on
the Claude subscription / Opus), not by an unattended cron paying per-token
API credits — an automated workflow cannot use the subscription, so any
cron-side generation would necessarily bill API credits, which we don't want.

When the unpublished buffer drops to or below the threshold, this emails
Rahul so he can refill. The refill is done in Claude Code:

  1. Author new essays as `wisdom/cache/<slug>.json` files (Claude Code
     writes the article text directly — no API call).
  2. `python pipeline/generate_affliction_pages.py`  — builds the HTML
     pages + sitemap from the cache. WITHOUT the `--with-articles` flag it
     does not call the Anthropic API; it just assembles existing content.
  3. Commit `wisdom/` + `sitemap.xml`.

Usage:
    python pipeline/ensure_wisdom_pool.py            # check; email if low
    python pipeline/ensure_wisdom_pool.py --min 7    # custom threshold
    python pipeline/ensure_wisdom_pool.py --no-alert # check + print only
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "jindal.rahul@gmail.com")

WISDOM_DIR = REPO_ROOT / "wisdom"
CACHE_DIR = WISDOM_DIR / "cache"

FROM_EMAIL = "Lotus Lane Bot <notifications@rxjapps.in>"

# Email Rahul once the unpublished buffer is at or below this many essays.
# 7 leaves about a week of daily-cadence runway to refill via Claude Code.
MIN_BUFFER = 7


def _supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def published_slugs() -> set[str]:
    """Slugs already in podcast_episodes. Empty set if Supabase unreachable."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        print("  WARNING: Supabase creds missing — treating all slugs as unpublished")
        return set()
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/podcast_episodes",
        headers=_supabase_headers(),
        params={"select": "slug"},
        timeout=20,
    )
    r.raise_for_status()
    return {row["slug"] for row in r.json()}


def cached_slugs() -> set[str]:
    """Slugs that already have a wisdom/cache/{slug}.json file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return {p.stem for p in CACHE_DIR.glob("*.json")}


def unpublished_buffer() -> tuple[int, list[str]]:
    """How many cached essays are not yet published, and which slugs."""
    pub = published_slugs()
    unpub = sorted(s for s in cached_slugs() if s not in pub)
    return len(unpub), unpub


def _send_low_buffer_alert(count: int, unpub: list[str]) -> bool:
    """Email Rahul that the wisdom pool needs a refill. Returns True if sent."""
    if not RESEND_API_KEY:
        print("  [alert] RESEND_API_KEY not set — cannot send low-buffer email")
        return False
    ready = ", ".join(unpub) if unpub else "(none)"
    html = f"""<div style="font-family:-apple-system,Segoe UI,sans-serif;font-size:15px;color:#111;line-height:1.6">
<p>Hi Rahul,</p>
<p>The Lotus Lane podcast wisdom pool is running low — <strong>{count}</strong>
unpublished essay(s) left (about {count} day(s) of daily-cadence runway).</p>
<p>Ready to publish: {ready}</p>
<p>Refill in Claude Code (no API credits): author new
<code>wisdom/cache/&lt;slug&gt;.json</code> essays, run
<code>python pipeline/generate_affliction_pages.py</code> (no
<code>--with-articles</code> flag), then commit <code>wisdom/</code> +
<code>sitemap.xml</code>.</p>
<p>— Lotus Lane pool monitor</p>
</div>"""
    try:
        resp = httpx.post(
            "https://ejvavmpieilvigjktugh.supabase.co/functions/v1/resend-send/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "from": FROM_EMAIL,
                "to": [NOTIFY_EMAIL],
                "subject": f"Lotus Lane: wisdom pool low — {count} essay(s) left",
                "html": html,
            },
            timeout=30,
        )
        if resp.status_code >= 300:
            print(f"  [alert] Resend error {resp.status_code}: {resp.text[:300]}")
            return False
        print(f"  [alert] low-buffer email sent to {NOTIFY_EMAIL}")
        return True
    except Exception as e:
        print(f"  [alert] low-buffer email failed: {e}")
        return False


def check(min_buffer: int, send_alert: bool) -> int:
    """Report the buffer; email Rahul if it is at or below `min_buffer`.

    Returns the unpublished count. Always exits the caller cleanly — a low
    pool is a heads-up, not a build failure.
    """
    count, unpub = unpublished_buffer()
    print(f"Unpublished wisdom buffer: {count} (alert threshold: {min_buffer})")
    if unpub:
        print(f"  ready slugs: {', '.join(unpub)}")
    if count <= min_buffer:
        print("Buffer LOW — refill needed (authored in Claude Code, not via API).")
        if send_alert:
            _send_low_buffer_alert(count, unpub)
    else:
        print("Buffer healthy — nothing to do.")
    return count


def main() -> None:
    p = argparse.ArgumentParser(
        description="Monitor the podcast wisdom pool and alert when low. "
                    "Never generates content, never calls the Anthropic API.")
    p.add_argument("--min", type=int, default=MIN_BUFFER,
                   help=f"Alert when the unpublished buffer is <= this (default {MIN_BUFFER})")
    p.add_argument("--no-alert", action="store_true",
                   help="Check and print only — do not send the email")
    args = p.parse_args()
    check(args.min, send_alert=not args.no_alert)


if __name__ == "__main__":
    main()
