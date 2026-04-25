#!/usr/bin/env python3
"""
Upload YouTube Shorts from generated videos.

First-time setup:
    python pipeline/youtube_upload.py --auth
    (Opens browser for Google OAuth2, saves refresh token)

Usage:
    python pipeline/youtube_upload.py --date 2026-03-31
    python pipeline/youtube_upload.py --latest
    python pipeline/youtube_upload.py --all
    python pipeline/youtube_upload.py --pending
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

# Add project root to path so `from pipeline.utils import ...` works
sys.path.insert(0, str(Path(__file__).parent.parent))

STRIPS_DIR = Path(__file__).parent.parent / "strips"
SHORTS_DIR = Path(__file__).parent.parent / "shorts"
REELS_DIR = Path(__file__).parent.parent / "reels"
STRIPS_JSON = Path(__file__).parent.parent / "strips.json"
TOKEN_FILE = Path(__file__).parent.parent / ".youtube_token.json"
CLIENT_SECRET_FILE = Path(__file__).parent.parent / "client_secret.json"

# YouTube API endpoints
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
VIDEOS_API_URL = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_API_URL = "https://www.googleapis.com/youtube/v3/channels"
SCOPES = "https://www.googleapis.com/auth/youtube"

# Channel guard — refresh tokens bound to the wrong Google account silently route
# uploads to a personal channel. The handle below is The Lotus Lane's public channel
# (rahul@karibykriti.com → @thelotuslane_ND). Any --auth run that picks a different
# Google account in the browser will fail this check before uploading.
# Override only if the canonical channel handle changes.
EXPECTED_CHANNEL_HANDLE = os.environ.get("YOUTUBE_EXPECTED_CHANNEL_HANDLE", "thelotuslane_ND")


def assert_authenticated_channel(access_token):
    """Fail loudly if the token is bound to a channel other than EXPECTED_CHANNEL_HANDLE.

    Why: on 2026-04-17 a refresh-token rotation under the wrong Google session
    silently routed three uploads to @zombielab123 (jindal.rahul@gmail.com's default
    channel). This guard catches the mistake on the next run, not three weeks later.
    """
    response = httpx.get(
        CHANNELS_API_URL,
        params={"part": "snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        raise RuntimeError("YouTube channels.list returned no channel for this token")
    snippet = items[0]["snippet"]
    handle = (snippet.get("customUrl") or "").lstrip("@")
    if handle.lower() != EXPECTED_CHANNEL_HANDLE.lower():
        raise RuntimeError(
            f"YouTube channel mismatch: token authenticates as @{handle} "
            f"({snippet.get('title')}), expected @{EXPECTED_CHANNEL_HANDLE}. "
            "Re-run `python pipeline/youtube_upload.py --auth` while signed into "
            "the correct Google account, then update the YOUTUBE_REFRESH_TOKEN secret."
        )
    return items[0]["id"], snippet.get("title", "")


def load_client_config():
    """Load OAuth2 client config from client_secret.json."""
    if not CLIENT_SECRET_FILE.exists():
        # Try environment variables (for GitHub Actions)
        client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
        if client_id and client_secret:
            return client_id, client_secret
        raise FileNotFoundError(
            f"client_secret.json not found at {CLIENT_SECRET_FILE}\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials"
        )

    with open(CLIENT_SECRET_FILE) as f:
        data = json.load(f)

    # Handle both "installed" and "web" client types
    config = data.get("installed", data.get("web", {}))
    if not config.get("client_id") or not config.get("client_secret"):
        raise ValueError(
            f"OAuth client config missing client_id/client_secret in {CLIENT_SECRET_FILE}. "
            "Expected 'installed' or 'web' key with credentials."
        )
    return config["client_id"], config["client_secret"]


def do_auth():
    """Interactive OAuth2 flow — opens browser, saves refresh token."""
    client_id, client_secret = load_client_config()

    # Step 1: Get authorization code via browser
    auth_params = {
        "client_id": client_id,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        "scope": SCOPES,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{AUTH_URL}?{'&'.join(f'{k}={v}' for k, v in auth_params.items())}"

    print(f"\nOpen this URL in your browser:\n\n{auth_url}\n")
    print("After authorizing, paste the authorization code below:")

    import webbrowser
    webbrowser.open(auth_url)

    code = input("\nAuthorization code: ").strip()

    # Step 2: Exchange code for tokens
    response = httpx.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
    })
    response.raise_for_status()
    tokens = response.json()

    # Verify the issued token resolves to the expected channel BEFORE saving.
    # Saving a wrong-account token is what caused the 2026-04-17 misroute.
    try:
        channel_id, channel_title = assert_authenticated_channel(tokens["access_token"])
    except RuntimeError as e:
        print(f"\nABORT: {e}")
        print("Token NOT saved. Re-run --auth in a browser session signed into the correct Google account.")
        sys.exit(1)

    # Save refresh token
    token_data = {
        "refresh_token": tokens["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
        "channel_id": channel_id,
        "channel_title": channel_title,
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nAuth successful! Token bound to: {channel_title} (@{EXPECTED_CHANNEL_HANDLE}, id={channel_id})")
    print(f"Refresh token saved to {TOKEN_FILE}")
    print("You can now upload videos with --date or --latest")


def get_access_token():
    """Get a fresh access token using the stored refresh token."""
    # Try token file first
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        refresh_token = data["refresh_token"]
        client_id = data["client_id"]
        client_secret = data["client_secret"]
    else:
        # Try environment variables (for GitHub Actions)
        refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
        client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
        if not all([refresh_token, client_id, client_secret]):
            raise ValueError("No YouTube credentials found. Run --auth first.")

    response = httpx.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    if response.status_code >= 400:
        # Surface the actual Google error so we can diagnose without pulling logs.
        # Common causes: invalid_grant (refresh token revoked/expired — user must
        # re-run `youtube_upload.py --auth` and update the GitHub secret).
        print(f"  OAuth token refresh FAILED ({response.status_code}): {response.text}", file=sys.stderr)
    response.raise_for_status()
    access_token = response.json()["access_token"]

    # Guard runs once per process — _channel_verified caches the result so we don't
    # burn quota on every upload in --all / --swap-old loops.
    if not getattr(get_access_token, "_channel_verified", False):
        channel_id, channel_title = assert_authenticated_channel(access_token)
        print(f"  YouTube auth OK — channel: {channel_title} (@{EXPECTED_CHANNEL_HANDLE})")
        get_access_token._channel_verified = True

    return access_token


def get_strip_data(date_str):
    """Get strip metadata from strips.json."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    for s in strips:
        if s["date"] == date_str:
            return s
    return None


def save_youtube_id(date_str, video_id):
    """Save the YouTube video ID back to strips.json for upload tracking."""
    from pipeline.utils import safe_update_strips, update_distribution_status

    def _update(strips):
        for s in strips:
            if s["date"] == date_str:
                s["youtube_id"] = video_id
                break

    safe_update_strips(_update)
    update_distribution_status(date_str, "youtube", "uploaded", platform_id=video_id)

    print(f"  [{date_str}] Saved youtube_id={video_id} to strips.json")


def get_pending_shorts():
    """Get strips that have videos generated but not yet uploaded to YouTube."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    pending = []
    for s in strips:
        video_path = SHORTS_DIR / f"{s['date']}.mp4"
        if video_path.exists() and not s.get("youtube_id"):
            pending.append(s)

    return pending


def show_pending():
    """Display pending shorts that have videos but haven't been uploaded."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    no_video = []
    pending_upload = []
    uploaded = []

    for s in strips:
        video_path = SHORTS_DIR / f"{s['date']}.mp4"
        if s.get("youtube_id"):
            uploaded.append(s)
        elif video_path.exists():
            pending_upload.append(s)
        else:
            no_video.append(s)

    print(f"\n📊 YouTube Shorts Status")
    print(f"   Total strips: {len(strips)}")
    print(f"   Uploaded:     {len(uploaded)}")
    print(f"   Pending:      {len(pending_upload)}")
    print(f"   No video:     {len(no_video)}")

    if pending_upload:
        print(f"\n⏳ Pending upload ({len(pending_upload)}):")
        for s in pending_upload:
            print(f"   {s['date']} - {s['title']}")

    if uploaded:
        print(f"\n✅ Uploaded ({len(uploaded)}):")
        for s in uploaded:
            print(f"   {s['date']} - {s['title']} → https://youtube.com/shorts/{s['youtube_id']}")

    if no_video:
        print(f"\n🎬 No video generated ({len(no_video)}):")
        for s in no_video:
            print(f"   {s['date']} - {s['title']}")

    print()


def _category_hashtags(category):
    """Return category-specific hashtags for YouTube description."""
    mapping = {
        "work-stress": "#CareerAdvice #BurnoutRecovery #WorkLifeBalance",
        "relationships": "#Relationships #LifeAdvice #LoveAndWisdom",
        "family": "#FamilyLife #Parenting #FamilyWisdom",
        "health": "#MentalHealth #InnerPeace #Healing",
        "finances": "#FinancialWisdom #MoneyMindset #Abundance",
        "self-doubt": "#SelfBelief #OvercomingFear #Confidence",
        "grief-loss": "#GriefSupport #HealingJourney #Resilience",
        "perseverance": "#NeverGiveUp #Persistence #KeepGoing",
    }
    return mapping.get(category, "#LifeLessons #WisdomQuotes")


def build_video_metadata(strip):
    """Build YouTube video metadata from strip data.

    Titles and descriptions lead with the human problem, not the Buddhist tradition.
    The algorithm surfaces Shorts based on interest, not subscribers — universal
    framing reaches the billions who search for help, not just practitioners.
    """
    title = f"{strip['title']} | The Lotus Lane"
    if len(title) > 100:
        title = f"{strip['title'][:90]} | Lotus Lane"

    category = strip.get("category", "")
    topic = strip.get("topic", "")
    strip_tags = strip.get("tags", [])

    # Tags: lead with universal human struggles, Buddhist terms secondary
    tags = strip_tags + [
        # Universal discovery (what people search for)
        "motivation", "life advice", "daily motivation",
        "self improvement", "mindfulness", "inner peace",
        "wisdom quotes", "life lessons", "mental health",
        "dealing with anger", "overcoming jealousy", "grief support",
        "how to forgive", "self doubt", "anxiety help",
        "positive thinking", "spiritual growth",
        # Source tradition (secondary discovery)
        "buddhist wisdom", "ancient wisdom", "eastern philosophy",
        # Format
        "comic strip", "indian animation", "motivational shorts",
        "the lotus lane", "shorts",
    ]

    # Add topic-specific tags for search (YouTube max 30 chars per tag)
    if topic and len(topic) <= 30:
        tags.insert(0, topic)
        tags.insert(1, topic.replace(" ", ""))

    cat_hashtags = _category_hashtags(category)
    description = (
        f"{strip.get('message', '')}\n\n"
        f'"{strip.get("quote", "")}"\n'
        f"- {strip.get('source', '')}\n\n"
        f"The Lotus Lane: stories about everyday struggles and the ancient wisdom "
        f"that helps. New episodes every Mon, Wed, Fri.\n\n"
        f"Read the full strip: https://thelotuslane.in/strips/{strip.get('date', '')}.html\n\n"
        f"#Shorts #Wisdom #LifeAdvice {cat_hashtags}\n"
        f"#Motivation #DailyWisdom #TheLotusLane"
    )

    # YouTube rules: each tag ≤30 chars, total serialized tag string ≤500 chars.
    # Multi-word tags get wrapped in quotes by the API (+2 chars each); commas
    # separate tags (+1 between each). Stay under 480 for safety.
    filtered_tags = [
        t for t in dict.fromkeys(tags)
        if len(t) <= 30 and t.replace(" ", "").replace("-", "").isalnum()
    ]
    safe_tags: list[str] = []
    total = 0
    for t in filtered_tags:
        cost = len(t) + (2 if " " in t else 0)
        if safe_tags:
            cost += 1  # comma separator
        if total + cost > 480:
            continue
        safe_tags.append(t)
        total += cost
        if len(safe_tags) >= 30:
            break

    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": safe_tags,
            "categoryId": "27",  # Education (better for seekers)
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "shorts": {"shortsOverlayOptIn": True},
        },
    }


def upload_video(date_str, force=False):
    """Upload a video for a given date to YouTube."""
    video_path = SHORTS_DIR / f"{date_str}.mp4"
    if not video_path.exists():
        print(f"  [{date_str}] No video found at {video_path}")
        return False

    strip = get_strip_data(date_str)
    if not strip:
        print(f"  [{date_str}] No strip data found in strips.json")
        return False

    if not force and strip.get("youtube_id"):
        print(f"  [{date_str}] Already uploaded (youtube_id={strip['youtube_id']}). Use --force to re-upload.")
        return False

    print(f"  [{date_str}] Uploading: {strip['title']}")

    access_token = get_access_token()
    metadata = build_video_metadata(strip)

    # Resumable upload — Step 1: Initiate
    init_response = httpx.post(
        f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(video_path.stat().st_size),
        },
        json=metadata,
        timeout=30,
    )
    if init_response.status_code >= 400:
        print(f"  YouTube API error {init_response.status_code}: {init_response.text[:500]}")
        init_response.raise_for_status()
    upload_url = init_response.headers["Location"]

    # Step 2: Upload the video file
    with open(video_path, "rb") as f:
        video_data = f.read()

    upload_response = httpx.put(
        upload_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "video/mp4",
            "Content-Length": str(len(video_data)),
        },
        content=video_data,
        timeout=300,
    )
    upload_response.raise_for_status()
    result = upload_response.json()

    video_id = result.get("id", "unknown")
    print(f"  [{date_str}] Uploaded! https://youtube.com/shorts/{video_id}")

    # Save youtube_id back to strips.json for tracking
    if video_id != "unknown":
        save_youtube_id(date_str, video_id)

    return True


def upload_hook_reel(date_str, force=False):
    """Upload a hook reel for a given date to YouTube."""
    video_path = REELS_DIR / f"{date_str}.mp4"
    if not video_path.exists():
        print(f"  [{date_str}] No hook reel at {video_path}")
        return False

    strip = get_strip_data(date_str)
    if not strip:
        print(f"  [{date_str}] No strip data in strips.json")
        return False

    if not force and strip.get("youtube_hook_reel_id"):
        print(f"  [{date_str}] Hook reel already uploaded (youtube_hook_reel_id={strip['youtube_hook_reel_id']})")
        return False

    print(f"  [{date_str}] Uploading hook reel: {strip['title']}")

    access_token = get_access_token()
    metadata = build_video_metadata(strip)

    # Resumable upload
    init_response = httpx.post(
        f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(video_path.stat().st_size),
        },
        json=metadata,
        timeout=30,
    )
    if init_response.status_code >= 400:
        print(f"  YouTube API error {init_response.status_code}: {init_response.text[:500]}")
        init_response.raise_for_status()
    upload_url = init_response.headers["Location"]

    with open(video_path, "rb") as f:
        video_data = f.read()

    upload_response = httpx.put(
        upload_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "video/mp4",
            "Content-Length": str(len(video_data)),
        },
        content=video_data,
        timeout=300,
    )
    upload_response.raise_for_status()
    result = upload_response.json()

    video_id = result.get("id", "unknown")
    print(f"  [{date_str}] Uploaded! https://youtube.com/shorts/{video_id}")

    if video_id != "unknown":
        from pipeline.utils import safe_update_strips
        def _update(strips):
            for s in strips:
                if s["date"] == date_str:
                    s["youtube_hook_reel_id"] = video_id
                    break
        safe_update_strips(_update)
        print(f"  [{date_str}] Saved youtube_hook_reel_id={video_id}")

    return True


def delete_video(youtube_id):
    """Delete a video from YouTube by ID."""
    access_token = get_access_token()
    response = httpx.delete(
        f"https://www.googleapis.com/youtube/v3/videos?id={youtube_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if response.status_code == 204:
        return True
    elif response.status_code == 404:
        print(f"    Video {youtube_id} already deleted or not found")
        return True
    else:
        print(f"    Delete failed ({response.status_code}): {response.text[:200]}")
        response.raise_for_status()
    return False


def swap_old_videos(max_per_run=5):
    """Delete old YouTube videos and re-upload with new text rendering.

    Processes strips flagged with youtube_needs_reupload=True.
    Deletes old video, uploads new one, clears the flag.
    """
    from pipeline.utils import safe_update_strips

    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    to_swap = [s for s in strips if s.get("youtube_needs_reupload")]
    if not to_swap:
        print("  No videos need swapping.")
        return

    print(f"  {len(to_swap)} videos flagged for swap. Processing up to {max_per_run}...")
    swapped = 0

    for strip in to_swap[:max_per_run]:
        date_str = strip["date"]
        old_id = strip.get("youtube_id", "")
        video_path = SHORTS_DIR / f"{date_str}.mp4"

        if not video_path.exists():
            print(f"  [{date_str}] SKIP — no video file")
            continue

        # Step 1: Upload new video FIRST (so old one stays if upload fails)
        print(f"  [{date_str}] Uploading new version...")

        def _clear_yt_id(strips, _ds=date_str):
            for s in strips:
                if s["date"] == _ds:
                    s["youtube_id"] = None
                    break
        safe_update_strips(_clear_yt_id)

        try:
            upload_video(date_str)
        except httpx.HTTPStatusError as e:
            if "uploadLimitExceeded" in str(e.response.text):
                # Restore old ID since upload failed
                def _restore(strips, _ds=date_str, _oid=old_id):
                    for s in strips:
                        if s["date"] == _ds:
                            s["youtube_id"] = _oid
                            break
                safe_update_strips(_restore)
                print(f"\n  YouTube daily limit reached after {swapped} swaps. Will continue tomorrow.")
                break
            # Restore old ID on other failures too
            def _restore(strips, _ds=date_str, _oid=old_id):
                for s in strips:
                    if s["date"] == _ds:
                        s["youtube_id"] = _oid
                        break
            safe_update_strips(_restore)
            print(f"  [{date_str}] Upload failed: {e}")
            continue
        except Exception as e:
            def _restore(strips, _ds=date_str, _oid=old_id):
                for s in strips:
                    if s["date"] == _ds:
                        s["youtube_id"] = _oid
                        break
            safe_update_strips(_restore)
            print(f"  [{date_str}] Upload failed: {e}")
            continue

        # Step 2: Delete old video AFTER successful upload
        if old_id:
            print(f"  [{date_str}] Deleting old video {old_id}...")
            try:
                delete_video(old_id)
            except Exception as e:
                print(f"  [{date_str}] Warning: delete failed ({e}) — old video may remain")

        # Step 3: Clear swap flag
        def _clear_flag(strips, _ds=date_str):
            for s in strips:
                if s["date"] == _ds:
                    s.pop("youtube_needs_reupload", None)
                    break
        safe_update_strips(_clear_flag)
        swapped += 1

    remaining = len(to_swap) - swapped
    print(f"\n  Swapped {swapped} video(s). {remaining} remaining.")


def pull_view_counts():
    """Fetch YouTube view counts for all strips with youtube_id and update strips.json.

    Uses the YouTube Data API v3 videos.list endpoint (part=statistics).
    Batches up to 50 IDs per request to minimize quota usage (1 unit per call).
    """
    from datetime import datetime, timezone
    from pipeline.utils import safe_update_strips

    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    # Collect all strips that have a youtube_id
    yt_strips = [(i, s["youtube_id"]) for i, s in enumerate(strips) if s.get("youtube_id")]
    if not yt_strips:
        print("  No strips with youtube_id found.")
        return

    print(f"  Fetching view counts for {len(yt_strips)} video(s)...")

    access_token = get_access_token()

    # Build a map of youtube_id -> view count from API responses
    view_counts = {}  # youtube_id -> int view count

    # Batch into groups of 50 (YouTube API max per request)
    batch_size = 50
    yt_ids = [yt_id for _, yt_id in yt_strips]

    for batch_start in range(0, len(yt_ids), batch_size):
        batch = yt_ids[batch_start:batch_start + batch_size]
        ids_param = ",".join(batch)

        response = httpx.get(
            VIDEOS_API_URL,
            params={
                "id": ids_param,
                "part": "statistics",
            },
            headers={
                "Authorization": f"Bearer {access_token}",
            },
            timeout=30,
        )
        if response.status_code >= 400:
            print(f"  YouTube API error {response.status_code}: {response.text[:500]}")
            response.raise_for_status()

        data = response.json()
        for item in data.get("items", []):
            video_id = item["id"]
            stats = item.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            view_counts[video_id] = views

    # Update strips.json with view counts
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = 0

    def _update_views(strips_data):
        nonlocal updated
        for s in strips_data:
            yt_id = s.get("youtube_id")
            if yt_id and yt_id in view_counts:
                s["youtube_views"] = view_counts[yt_id]
                s["youtube_views_updated_at"] = now_iso
                updated += 1

    safe_update_strips(_update_views)

    print(f"  Updated view counts for {updated} video(s).")
    # Print summary
    for yt_id, views in sorted(view_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"    {yt_id}: {views:,} views")


def get_latest_date():
    """Get the most recent strip date."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    strips.sort(key=lambda s: s["date"], reverse=True)
    return strips[0]["date"] if strips else None


def main():
    parser = argparse.ArgumentParser(description="Upload Lotus Lane shorts to YouTube")
    parser.add_argument("--auth", action="store_true", help="Run OAuth2 setup")
    parser.add_argument("--date", help="Upload video for specific date")
    parser.add_argument("--latest", action="store_true", help="Upload the latest video")
    parser.add_argument("--all", action="store_true", help="Upload all videos")
    parser.add_argument("--pending", action="store_true", help="Show upload status of all shorts")
    parser.add_argument("--force", action="store_true", help="Re-upload even if already uploaded")
    parser.add_argument("--hook-reels", action="store_true",
                        help="Upload hook reels from reels/ directory (5/day)")
    parser.add_argument("--swap-old", action="store_true",
                        help="Delete old YouTube videos and re-upload with new text (5/day)")
    parser.add_argument("--views", action="store_true",
                        help="Pull YouTube view counts for all uploaded videos")
    args = parser.parse_args()

    if args.auth:
        do_auth()
        return

    if args.pending:
        show_pending()
        return

    if args.hook_reels:
        max_per_run = 5
        uploaded = 0
        with open(STRIPS_JSON, "r", encoding="utf-8") as f:
            strips = json.load(f)
        pending = [s for s in strips
                   if not s.get("youtube_hook_reel_id")
                   and (REELS_DIR / f"{s['date']}.mp4").exists()]
        pending.sort(key=lambda s: s["date"], reverse=True)  # newest first

        print(f"  {len(pending)} hook reels pending upload. Uploading up to {max_per_run}...")
        for strip in pending[:max_per_run]:
            try:
                result = upload_hook_reel(strip["date"], force=args.force)
                if result:
                    uploaded += 1
            except httpx.HTTPStatusError as e:
                if "uploadLimitExceeded" in str(e.response.text):
                    print(f"\n  YouTube daily limit reached. Stopping.")
                    break
                print(f"  FAILED [{strip['date']}]: {e}")
            except Exception as e:
                print(f"  FAILED [{strip['date']}]: {e}")
        print(f"\n  Uploaded {uploaded} hook reel(s). {len(pending) - uploaded} remaining.")
        return

    if args.swap_old:
        swap_old_videos()
        return

    if args.views:
        pull_view_counts()
        return

    if args.latest:
        date_str = get_latest_date()
        if date_str:
            upload_video(date_str, force=args.force)
        else:
            print("No strips found")
    elif args.date:
        upload_video(args.date, force=args.force)
    elif args.all:
        max_per_run = 5  # stay well under YouTube's daily limit (~6)
        uploaded = 0
        failures = []
        # Upload newest-first so recent strips publish fastest; older backlog
        # (Jan/Feb strips with MP4 but no youtube_id) drains over subsequent
        # daily runs. No date cutoff — the pending-upload queue drives itself empty.
        for f in sorted(SHORTS_DIR.glob("*.mp4"), reverse=True):
            date_str = f.stem.replace("_narrated", "")
            try:
                result = upload_video(date_str, force=args.force)
                if result:
                    uploaded += 1
                if uploaded >= max_per_run:
                    print(f"\n  Reached daily limit ({max_per_run} uploads). Remaining will retry tomorrow.")
                    break
            except httpx.HTTPStatusError as e:
                if "uploadLimitExceeded" in str(e.response.text):
                    print(f"\n  YouTube daily upload limit reached. Stopping. Will retry tomorrow.")
                    break
                print(f"  FAILED [{date_str}]: {e}")
                failures.append(date_str)
            except Exception as e:
                print(f"  FAILED [{date_str}]: {e}")
                failures.append(date_str)
        print(f"\n  Uploaded {uploaded} video(s) this run.")
        if failures:
            print(f"  {len(failures)} failure(s): {', '.join(failures)}")
            sys.exit(1)
    else:
        print("Specify --auth, --date, --latest, --all, --pending, or --views")


if __name__ == "__main__":
    main()
