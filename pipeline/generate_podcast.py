"""Generate one Lotus Lane Daily podcast episode.

Pipeline:
    1. Load wisdom/cache/{slug}.json (or other source)
    2. Strip HTML to spoken-text body
    3. Wrap with intro + outro template
    4. Call OpenAI tts-1-hd (voice=nova) → MP3
    5. Upload MP3 to gs://lotus-lane-content/podcast/{slug}.mp3
    6. Insert row in public.podcast_episodes (Supabase)

Default mode is DRY-RUN — generates the script + estimates cost without
calling TTS, uploading, or writing to Supabase. Pass --live to run for real.
Universal-framing rule: no "Nichiren", "daimoku", "SGI" in spoken text;
quote attributions in the source content stay as-is.

Usage:
    python pipeline/generate_podcast.py --slug burnout-recovery
    python pipeline/generate_podcast.py --slug burnout-recovery --live
    python pipeline/generate_podcast.py --pick-next --live
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

GCS_BUCKET = "lotus-lane-podcast"
GCS_PREFIX = ""
PUBLIC_BASE_URL = f"https://storage.googleapis.com/{GCS_BUCKET}"

VOICE_MODEL = "openai:tts-1-hd:nova"
OPENAI_TTS_PRICE_PER_CHAR = 30 / 1_000_000  # $30/M chars

INTRO_TEMPLATE = (
    "Welcome to Lotus Lane Daily. I'm glad you're here.\n\n"
    "Today's wisdom is for anyone {intro_subject}.\n\n"
)
OUTRO = (
    "\n\nThat's the wisdom for today. "
    "If something here landed for you, share it with one person who might "
    "need to hear it too. Take it slow. I'll see you tomorrow on Lotus Lane Daily."
)

INTRO_SUBJECTS: dict[str, str] = {
    "burnout-recovery": "running on empty",
    "anxiety-insomnia": "lying awake at 3am with a racing mind",
    "anger-you-cant-control": "carrying anger they can't put down",
    "caregiver-burden": "looking after someone they love and disappearing inside it",
    "chronic-illness": "living inside a body that won't cooperate",
    "comparison-trap": "stuck watching everyone else's life and feeling behind",
    "dealing-with-jealousy": "noticing jealousy and not knowing where to put it",
    "depression-fog": "going through the days inside a fog",
    "divorce": "in the middle of an ending they didn't fully choose",
    "feeling-like-a-failure": "feeling like they should be further along by now",
    "financial-anxiety": "carrying money worry into every quiet moment",
    "how-to-forgive": "trying to forgive someone they're not sure deserves it",
    "loneliness-despite-everything": "lonely in the middle of a full life",
    "overcoming-imposter-syndrome": "convinced they don't really belong here",
    "parenting-is-breaking-me": "loving their kids and quietly falling apart",
    "rejection": "still flinching from a no that didn't break them but did mark them",
    "relationship-falling-apart": "watching a relationship slowly come undone",
    "sidelined-at-work": "doing the work and watching someone else get the credit",
}


def _strip_html(html: str) -> str:
    """HTML body → spoken text. Preserves italics inline (TTS reads naturally)."""
    text = html
    # Headers become paragraph breaks with a slight pause cue
    text = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n\n\1.\n\n", text, flags=re.S | re.I)
    # Paragraphs and line breaks
    text = re.sub(r"</?p[^>]*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    # Strip remaining tags but keep the inner text (em, strong, etc.)
    text = re.sub(r"<[^>]+>", "", text)
    # HTML entities
    replacements = {
        "&ldquo;": '"', "&rdquo;": '"', "&lsquo;": "'", "&rsquo;": "'",
        "&hellip;": "...", "&mdash;": "—", "&ndash;": "–",
        "&amp;": "&", "&nbsp;": " ", "&quot;": '"', "&#39;": "'",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def load_wisdom_cache(slug: str) -> dict:
    cache_path = REPO_ROOT / "wisdom" / "cache" / f"{slug}.json"
    if not cache_path.exists():
        raise FileNotFoundError(f"Wisdom cache not found: {cache_path}")
    return json.loads(cache_path.read_text(encoding="utf-8"))


def load_wisdom_meta(slug: str) -> dict:
    """Pull title + meta description from the rendered HTML page."""
    page = REPO_ROOT / "wisdom" / f"{slug}.html"
    html = page.read_text(encoding="utf-8")
    title_m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    desc_m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
    title = title_m.group(1) if title_m else slug
    title = title.replace(" | The Lotus Lane", "").strip()
    description = desc_m.group(1) if desc_m else ""
    return {"title": title, "description": description}


def build_script(slug: str, body_html: str) -> str:
    intro = INTRO_TEMPLATE.format(
        intro_subject=INTRO_SUBJECTS.get(slug, "going through something hard"),
    )
    body = _strip_html(body_html)
    return intro + body + OUTRO


def already_published(slug: str) -> bool:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return False
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/podcast_episodes",
        headers=_supabase_headers(),
        params={"slug": f"eq.{slug}", "select": "id"},
        timeout=15,
    )
    r.raise_for_status()
    return len(r.json()) > 0


def next_episode_number() -> int:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/podcast_episodes",
        headers=_supabase_headers(),
        params={"select": "episode_number", "order": "episode_number.desc", "limit": "1"},
        timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    return (rows[0]["episode_number"] + 1) if rows else 1


def pick_next_unpublished_slug() -> str | None:
    """Pick first wisdom slug not yet in podcast_episodes."""
    cache_dir = REPO_ROOT / "wisdom" / "cache"
    candidates = sorted(p.stem for p in cache_dir.glob("*.json"))
    for slug in candidates:
        if not already_published(slug):
            return slug
    return None


TTS_CHUNK_LIMIT = 3800  # OpenAI hard limit is 4096; leave headroom


def _chunk_text(text: str, limit: int = TTS_CHUNK_LIMIT) -> list[str]:
    """Split on paragraph boundaries, packing chunks up to `limit` chars."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = (current + "\n\n" + para).strip() if current else para
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # Paragraph itself longer than limit — split on sentence boundaries
        if len(para) > limit:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current = ""
            for s in sentences:
                cand2 = (current + " " + s).strip() if current else s
                if len(cand2) <= limit:
                    current = cand2
                else:
                    if current:
                        chunks.append(current)
                    current = s
        else:
            current = para
    if current:
        chunks.append(current)
    return chunks


def _tts_one(text: str, out_path: Path) -> None:
    r = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "tts-1-hd",
            "voice": "nova",
            "input": text,
            "response_format": "mp3",
        },
        timeout=300,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI TTS {r.status_code}: {r.text[:300]}")
    out_path.write_bytes(r.content)


def synthesize_tts(text: str, out_path: Path) -> None:
    """Chunked TTS: splits on paragraph boundaries, then concatenates MP3s."""
    chunks = _chunk_text(text)
    if len(chunks) == 1:
        _tts_one(chunks[0], out_path)
        return
    from pydub import AudioSegment  # imported here so dry-run doesn't need it

    parts_dir = out_path.parent / f"_parts_{out_path.stem}"
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for i, chunk in enumerate(chunks, 1):
        part_path = parts_dir / f"part_{i:02d}.mp3"
        print(f"      chunk {i}/{len(chunks)} ({len(chunk)} chars)...")
        _tts_one(chunk, part_path)
        parts.append(part_path)

    combined = AudioSegment.empty()
    for p in parts:
        combined += AudioSegment.from_mp3(p)
    combined.export(out_path, format="mp3", bitrate="128k")

    # Clean up part files
    for p in parts:
        p.unlink()
    parts_dir.rmdir()


def _gsutil_cmd() -> str:
    """Locate gsutil — Windows uses .cmd wrapper, Linux/Mac uses bare binary."""
    if os.name == "nt":
        for c in ("gsutil.cmd", "gsutil"):
            for p in os.environ.get("PATH", "").split(os.pathsep):
                full = Path(p) / c
                if full.exists():
                    return str(full)
        # Fallback to known gcloud SDK location
        sdk = Path.home() / "AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/gsutil.cmd"
        if sdk.exists():
            return str(sdk)
    return "gsutil"


def upload_to_gcs(local: Path, gcs_object: str) -> str:
    """Upload via gsutil (already authenticated). Returns public URL.

    Bucket has uniform bucket-level access + public IAM grant, so no
    per-object ACL needed.
    """
    gsutil = _gsutil_cmd()
    dest = f"gs://{GCS_BUCKET}/{gcs_object}"
    subprocess.run(
        [gsutil, "-h", "Content-Type:audio/mpeg", "cp", str(local), dest],
        check=True,
        capture_output=True,
    )
    return f"https://storage.googleapis.com/{GCS_BUCKET}/{gcs_object}"


def gcs_object_exists(gcs_object: str) -> bool:
    """Check if an MP3 already lives in the bucket (idempotency)."""
    url = f"https://storage.googleapis.com/{GCS_BUCKET}/{gcs_object}"
    try:
        r = httpx.head(url, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def estimate_duration_seconds(char_count: int) -> int:
    # OpenAI tts-1-hd nova averages ~14 chars/second when read
    return max(60, int(char_count / 14))


def insert_episode_row(payload: dict) -> dict:
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/podcast_episodes",
        headers=_supabase_headers(),
        json=payload,
        timeout=15,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase insert failed {r.status_code}: {r.text}")
    return r.json()[0]


def run(slug: str, live: bool) -> None:
    if live and not OPENAI_API_KEY:
        sys.exit("OPENAI_API_KEY missing")
    if live and not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY missing")

    if live and already_published(slug):
        sys.exit(f"Already published: {slug}")

    cache = load_wisdom_cache(slug)
    meta = load_wisdom_meta(slug)
    script = build_script(slug, cache["article_html"])
    chars = len(script)
    cost = round(chars * OPENAI_TTS_PRICE_PER_CHAR, 5)
    duration = estimate_duration_seconds(chars)

    print(f"slug:        {slug}")
    print(f"title:       {meta['title']}")
    print(f"description: {meta['description']}")
    print(f"chars:       {chars:,} (~{duration}s = {duration//60}:{duration%60:02d})")
    print(f"cost:        ${cost:.5f}")
    print(f"---script preview (first 240 chars)---")
    print(script[:240] + "...")

    if not live:
        print("\nDRY RUN. Add --live to actually generate + upload.")
        return

    out_dir = REPO_ROOT / "podcast" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = out_dir / f"{slug}.mp3"
    gcs_object = f"{slug}.mp3"

    if gcs_object_exists(gcs_object):
        print("\n[1/3] MP3 already in GCS — skipping TTS (idempotent retry)")
        # Pull file size from HEAD so the row carries accurate bytes
        head = httpx.head(f"https://storage.googleapis.com/{GCS_BUCKET}/{gcs_object}", timeout=10)
        file_size = int(head.headers.get("Content-Length", "0"))
        audio_url = f"https://storage.googleapis.com/{GCS_BUCKET}/{gcs_object}"
        print(f"      {file_size/1024:.1f} KB at {audio_url}")
    else:
        print("\n[1/3] Synthesizing audio via OpenAI tts-1-hd nova...")
        synthesize_tts(script, mp3_path)
        file_size = mp3_path.stat().st_size
        print(f"      {file_size/1024:.1f} KB -> {mp3_path}")

        print("[2/3] Uploading to GCS...")
        audio_url = upload_to_gcs(mp3_path, gcs_object)
        print(f"      {audio_url}")

    print("[3/3] Inserting Supabase row...")
    ep_num = next_episode_number()
    row = insert_episode_row({
        "slug": slug,
        "source_type": "wisdom",
        "episode_number": ep_num,
        "title": meta["title"],
        "description": meta["description"],
        "audio_url": audio_url,
        "audio_size_bytes": file_size,
        "duration_seconds": duration,
        "voice_model": VOICE_MODEL,
        "script_chars": chars,
        "cost_usd": cost,
        "published_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"      ep #{row['episode_number']} id={row['id']}")
    print("\nDONE.")


def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="Wisdom slug to generate")
    g.add_argument("--pick-next", action="store_true", help="Pick first unpublished slug")
    p.add_argument("--live", action="store_true", help="Actually generate + upload + write")
    args = p.parse_args()

    if args.pick_next:
        if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
            sys.exit("--pick-next requires SUPABASE_URL / SUPABASE_SERVICE_KEY")
        slug = pick_next_unpublished_slug()
        if not slug:
            sys.exit("No unpublished wisdom slugs remaining")
        print(f"picked: {slug}")
    else:
        slug = args.slug

    run(slug, args.live)


if __name__ == "__main__":
    main()
