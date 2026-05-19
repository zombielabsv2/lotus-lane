#!/usr/bin/env python3
"""Perpetual content engine — keep the podcast pool from ever running dry.

The daily podcast cron (`generate-podcast.yml`) picks the first wisdom slug
under `wisdom/cache/*.json` that is not yet a row in Supabase
`podcast_episodes`. When every cached wisdom essay has been published, the
picker returns nothing and the podcast silently stops.

This script runs BEFORE `--pick-next` in the daily workflow. It:

  1. Counts the UNPUBLISHED buffer = cached wisdom slugs not yet in
     `podcast_episodes`.
  2. If the buffer is at or above MIN_BUFFER, exits cleanly (nothing to do).
  3. Otherwise it generates new wisdom essays until the buffer is restored,
     drawing topics in this order:
       a. The hand-curated bank: slugs defined in `config.AFFLICTION_PAGES`
          that do not yet have a `wisdom/cache/{slug}.json` file.
       b. When (a) is exhausted, fresh topics invented by Claude and appended
          to `pipeline/wisdom_topic_bank.json` (which `config.py` merges into
          `AFFLICTION_PAGES` on import) — so the engine truly never runs dry.
  4. Regenerates the wisdom HTML pages + `sitemap.xml`.

Each generated essay produces:
  - `wisdom/cache/{slug}.json`  (article body, consumed by the podcast)
  - `wisdom/{slug}.html`        (SEO landing page, consumed by the podcast meta)

Usage:
    python pipeline/ensure_wisdom_pool.py              # top up if low
    python pipeline/ensure_wisdom_pool.py --min 5      # custom buffer
    python pipeline/ensure_wisdom_pool.py --dry-run    # report only, no API
    python pipeline/ensure_wisdom_pool.py --force 3    # generate N regardless
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

sys.path.insert(0, str(REPO_ROOT))

from pipeline import config as _config
from pipeline.config import AFFLICTION_PAGES
from pipeline import generate_affliction_pages as gap

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

WISDOM_DIR = REPO_ROOT / "wisdom"
CACHE_DIR = WISDOM_DIR / "cache"
TOPIC_BANK_FILE = REPO_ROOT / "pipeline" / "wisdom_topic_bank.json"

# Keep at least this many unpublished essays ready at all times.
MIN_BUFFER = 5
# How many to top up to when we do generate (a little headroom above MIN).
TARGET_BUFFER = 8

# Valid category keys — these have Ikeda-quote theme mappings in
# generate_affliction_pages.find_relevant_quotes(). AI-generated topics must
# use only these so the "Words that help" section is never empty.
VALID_CATEGORIES = [
    "work-stress", "relationships", "family", "health", "finances",
    "self-doubt", "grief-loss", "perseverance", "anger", "loneliness",
    "envy", "chronic-illness", "caregiving", "anxiety", "divorce",
    "workplace-politics", "rejection",
]


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


def bank_topics() -> list[str]:
    """Hand-curated AFFLICTION_PAGES slugs with no cache file yet."""
    have = cached_slugs()
    return sorted(s for s in AFFLICTION_PAGES if s not in have)


def _generate_fresh_topics(n: int) -> dict[str, list]:
    """Ask Claude for `n` brand-new affliction topics not already covered.

    Returns {slug: [title, meta_description, [categories]]}. Empty on failure.
    """
    if not ANTHROPIC_API_KEY:
        print("  WARNING: ANTHROPIC_API_KEY missing — cannot invent fresh topics")
        return {}

    existing_titles = sorted(t for (t, _, _) in AFFLICTION_PAGES.values())
    existing_slugs = sorted(AFFLICTION_PAGES.keys())

    prompt = f"""You curate topics for thelotuslane.in, a website that helps people
through everyday human suffering using ancient wisdom. Each topic becomes an SEO
landing page and a podcast episode.

I need {n} BRAND-NEW affliction topics — genuine, distinct human struggles that
a real person would type into Google at 2am because they are hurting.

ALREADY COVERED (do NOT repeat these or near-duplicates):
{json.dumps(existing_slugs, indent=1)}

RULES:
1. Each topic must be a real, specific, universal human struggle — not a vague mood.
2. Must be genuinely distinct from everything already covered above.
3. Problem-first framing. No Buddhist jargon, no religious terms in titles.
4. The slug is lowercase, hyphenated, URL-safe, 2-5 words.
5. The title is plain and human ("When ...", "How to ...", or a direct phrase).
6. The meta_description is 1-2 honest sentences (max ~160 chars), no hype.
7. Pick 2-3 categories ONLY from this exact list:
{json.dumps(VALID_CATEGORIES)}

Return ONLY a JSON object, no prose, mapping slug -> [title, meta_description, [categories]]:
{{
  "example-slug": ["Example Title", "An honest one-line description.", ["self-doubt", "anxiety"]]
}}"""

    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=90,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"  fresh-topic generation failed: {e}")
        return {}

    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        print("  fresh-topic response had no JSON object")
        return {}
    try:
        raw = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        print(f"  fresh-topic JSON parse failed: {e}")
        return {}

    cleaned: dict[str, list] = {}
    for slug, entry in raw.items():
        slug = re.sub(r"[^a-z0-9-]", "", slug.lower())
        if not slug or slug in AFFLICTION_PAGES or slug in cleaned:
            continue
        if not (isinstance(entry, list) and len(entry) == 3):
            continue
        title, desc, cats = entry
        cats = [c for c in cats if c in VALID_CATEGORIES] or ["self-doubt"]
        cleaned[slug] = [str(title).strip(), str(desc).strip(), cats]
    return cleaned


def _append_to_topic_bank(topics: dict[str, list]) -> None:
    """Persist AI-invented topics so config.py picks them up on next import."""
    bank: dict[str, list] = {}
    if TOPIC_BANK_FILE.exists():
        try:
            bank = json.loads(TOPIC_BANK_FILE.read_text(encoding="utf-8"))
        except Exception:
            bank = {}
    bank.update(topics)
    TOPIC_BANK_FILE.write_text(
        json.dumps(bank, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # Make them live for the rest of THIS process too.
    for slug, entry in topics.items():
        AFFLICTION_PAGES.setdefault(slug, (entry[0], entry[1], list(entry[2])))


def _build_one_page(slug: str) -> bool:
    """Generate cache JSON + HTML for one slug. Returns True on success."""
    title, meta_desc, categories = AFFLICTION_PAGES[slug]
    strips = gap.load_strips()
    ikeda = gap.load_ikeda_quotes()
    content_struggles = gap.load_content_struggles()
    podcast_episodes = gap.load_podcast_episodes()

    html = gap.generate_affliction_page(
        slug, title, meta_desc, categories, strips, ikeda,
        content_struggles=content_struggles,
        podcast_episodes=podcast_episodes,
        generate_articles=True,
    )
    cache_file = CACHE_DIR / f"{slug}.json"
    if not cache_file.exists():
        print(f"  ERROR: article generation produced no cache for {slug}")
        return False
    (WISDOM_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
    print(f"  generated wisdom/{slug}.html + cache/{slug}.json")
    return True


def _regenerate_all_pages_and_sitemap() -> None:
    """Re-render every affliction page (so cross-links/index update) + sitemap."""
    import subprocess
    print("  re-rendering all affliction pages + index...")
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "pipeline" / "generate_affliction_pages.py")],
        check=True, cwd=str(REPO_ROOT),
    )
    print("  regenerating sitemap.xml...")
    try:
        from pipeline import generate_pages
        strips = generate_pages.load_strips() if hasattr(generate_pages, "load_strips") else json.loads((REPO_ROOT / "strips.json").read_text(encoding="utf-8"))
        generate_pages.generate_sitemap(strips)
    except Exception as e:
        print(f"  sitemap regen via generate_pages failed ({e}); skipping")


def topup(min_buffer: int, target: int, dry_run: bool, force: int = 0) -> int:
    """Restore the unpublished buffer. Returns number of essays generated."""
    count, unpub = unpublished_buffer()
    print(f"Unpublished wisdom buffer: {count} (min={min_buffer}, target={target})")
    if unpub:
        print(f"  ready slugs: {', '.join(unpub)}")

    if force > 0:
        need = force
        print(f"  --force {force}: generating {need} regardless of buffer")
    elif count >= min_buffer:
        print("Buffer healthy — nothing to generate.")
        return 0
    else:
        need = target - count
        print(f"Buffer low — need to generate {need} new essay(s).")

    if dry_run:
        bank = bank_topics()
        print(f"DRY RUN: would generate {need}. Bank has {len(bank)} unused "
              f"hand-curated topic(s){': ' + ', '.join(bank[:need]) if bank else ''}.")
        if need > len(bank):
            print(f"  ...then {need - len(bank)} would be invented fresh via Claude.")
        return 0

    generated = 0
    while generated < need:
        bank = bank_topics()
        if not bank:
            # Hand-curated bank exhausted — invent fresh topics via Claude.
            fresh_needed = need - generated
            print(f"  hand-curated bank empty — inventing {fresh_needed} fresh topic(s)...")
            fresh = _generate_fresh_topics(fresh_needed)
            if not fresh:
                print("  could not invent fresh topics — stopping early.")
                break
            _append_to_topic_bank(fresh)
            print(f"  added {len(fresh)} fresh topic(s) to wisdom_topic_bank.json: "
                  f"{', '.join(fresh.keys())}")
            bank = bank_topics()
            if not bank:
                print("  fresh topics did not register — stopping early.")
                break

        slug = bank[0]
        print(f"[{generated + 1}/{need}] building '{slug}'...")
        if _build_one_page(slug):
            generated += 1
        else:
            # Generation failed (e.g. API error). Stop rather than spin.
            print("  generation failed — stopping early to avoid a spin loop.")
            break

    if generated:
        _regenerate_all_pages_and_sitemap()
        new_count, _ = unpublished_buffer()
        print(f"Done. Generated {generated} essay(s). Buffer is now {new_count}.")
    else:
        print("No essays generated.")
    return generated


def main() -> None:
    p = argparse.ArgumentParser(description="Keep the podcast wisdom pool full.")
    p.add_argument("--min", type=int, default=MIN_BUFFER,
                   help=f"Minimum unpublished buffer (default {MIN_BUFFER})")
    p.add_argument("--target", type=int, default=TARGET_BUFFER,
                   help=f"Buffer to top up to when generating (default {TARGET_BUFFER})")
    p.add_argument("--dry-run", action="store_true",
                   help="Report only — no API calls, no files written")
    p.add_argument("--force", type=int, default=0, metavar="N",
                   help="Generate exactly N new essays regardless of buffer")
    args = p.parse_args()

    target = max(args.target, args.min)
    topup(args.min, target, args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
