"""Generate Lotus Lane Daily podcast RSS feed.

Pulls all rows from public.podcast_episodes and writes podcast.xml
to the repo root for GitHub Pages serving at:

    https://thelotuslane.in/podcast.xml

Apple-Podcasts-compliant: includes itunes namespace, owner, category,
explicit flag, episode metadata, and absolute enclosure URLs.

Usage:
    python pipeline/generate_podcast_feed.py
    python pipeline/generate_podcast_feed.py --out podcast.xml
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

SITE_URL = "https://thelotuslane.in"
COVER_URL = "https://storage.googleapis.com/lotus-lane-podcast/cover.png"
OWNER_NAME = "The Lotus Lane"
OWNER_EMAIL = "jindal.rahul@gmail.com"
TITLE = "Lotus Lane Daily"
SUBTITLE = "Wisdom for what you're going through"
DESCRIPTION = (
    "Daily wisdom drawn from centuries of philosophical writing, applied to the "
    "things that actually keep us up at night — burnout, anxiety, loneliness, "
    "loss, comparison. Short, honest, listenable. New episode every weekday."
)
LANGUAGE = "en-IN"
CATEGORY = "Religion & Spirituality"
SUBCATEGORY = "Buddhism"
EXPLICIT = "false"
COPYRIGHT = "© The Lotus Lane"


def fetch_episodes() -> list[dict]:
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY missing")
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/podcast_episodes",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        },
        params={"select": "*", "order": "episode_number.desc"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _fmt_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _attr(value: str) -> str:
    """XML attribute value with quotes — escapes & < > and the quote char."""
    return quoteattr(value)


def render_feed(episodes: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"',
        '     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"',
        '     xmlns:content="http://purl.org/rss/1.0/modules/content/"',
        '     xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        f"    <title>{escape(TITLE)}</title>",
        f"    <link>{SITE_URL}</link>",
        f"    <atom:link href={_attr(SITE_URL + '/podcast.xml')} rel=\"self\" type=\"application/rss+xml\" />",
        f"    <language>{LANGUAGE}</language>",
        f"    <copyright>{escape(COPYRIGHT)}</copyright>",
        f"    <description>{escape(DESCRIPTION)}</description>",
        f"    <itunes:summary>{escape(DESCRIPTION)}</itunes:summary>",
        f"    <itunes:subtitle>{escape(SUBTITLE)}</itunes:subtitle>",
        f"    <itunes:author>{escape(OWNER_NAME)}</itunes:author>",
        f"    <itunes:explicit>{EXPLICIT}</itunes:explicit>",
        f"    <itunes:type>episodic</itunes:type>",
        "    <itunes:owner>",
        f"      <itunes:name>{escape(OWNER_NAME)}</itunes:name>",
        f"      <itunes:email>{escape(OWNER_EMAIL)}</itunes:email>",
        "    </itunes:owner>",
        f"    <itunes:image href={_attr(COVER_URL)} />",
        f"    <image><url>{escape(COVER_URL)}</url><title>{escape(TITLE)}</title><link>{escape(SITE_URL)}</link></image>",
        f"    <itunes:category text={_attr(CATEGORY)}>",
        f"      <itunes:category text={_attr(SUBCATEGORY)} />",
        "    </itunes:category>",
        f"    <pubDate>{format_datetime(now)}</pubDate>",
        f"    <lastBuildDate>{format_datetime(now)}</lastBuildDate>",
    ]

    for ep in episodes:
        published = datetime.fromisoformat(ep["published_at"].replace("Z", "+00:00"))
        guid = ep["audio_url"]
        episode_page_url = f"{SITE_URL}/wisdom/{ep['slug']}.html"
        lines += [
            "    <item>",
            f"      <title>{escape(ep['title'])}</title>",
            f"      <link>{escape(episode_page_url)}</link>",
            f"      <guid isPermaLink=\"false\">{escape(guid)}</guid>",
            f"      <pubDate>{format_datetime(published)}</pubDate>",
            f"      <description>{escape(ep['description'])}</description>",
            f"      <itunes:summary>{escape(ep['description'])}</itunes:summary>",
            f"      <itunes:author>{escape(OWNER_NAME)}</itunes:author>",
            f"      <itunes:explicit>{EXPLICIT}</itunes:explicit>",
            f"      <itunes:duration>{_fmt_duration(ep['duration_seconds'])}</itunes:duration>",
            f"      <itunes:episode>{ep['episode_number']}</itunes:episode>",
            f"      <itunes:episodeType>full</itunes:episodeType>",
            f"      <enclosure url={_attr(ep['audio_url'])} length=\"{ep['audio_size_bytes']}\" type=\"audio/mpeg\" />",
            "    </item>",
        ]

    lines += ["  </channel>", "</rss>"]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(REPO_ROOT / "podcast.xml"))
    args = p.parse_args()

    episodes = fetch_episodes()
    xml = render_feed(episodes)
    Path(args.out).write_text(xml, encoding="utf-8")
    print(f"OK {args.out} ({len(episodes)} episodes, {len(xml):,} bytes)")


if __name__ == "__main__":
    main()
