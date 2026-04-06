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

STRIPS_DIR = Path(__file__).parent.parent / "strips"
SHORTS_DIR = Path(__file__).parent.parent / "shorts"
STRIPS_JSON = Path(__file__).parent.parent / "strips.json"
TOKEN_FILE = Path(__file__).parent.parent / ".youtube_token.json"
CLIENT_SECRET_FILE = Path(__file__).parent.parent / "client_secret.json"

# YouTube API endpoints
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPES = "https://www.googleapis.com/auth/youtube.upload"


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

    # Save refresh token
    token_data = {
        "refresh_token": tokens["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nAuth successful! Refresh token saved to {TOKEN_FILE}")
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
    response.raise_for_status()
    return response.json()["access_token"]


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
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    for s in strips:
        if s["date"] == date_str:
            s["youtube_id"] = video_id
            break

    with open(STRIPS_JSON, "w", encoding="utf-8") as f:
        json.dump(strips, f, indent=2, ensure_ascii=False)
        f.write("\n")

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


def build_video_metadata(strip):
    """Build YouTube video metadata from strip data."""
    title = f"{strip['title']} | The Lotus Lane"
    if len(title) > 100:
        title = f"{strip['title'][:90]} | Lotus Lane"

    tags = strip.get("tags", []) + [
        "nichiren buddhism", "buddhist wisdom", "life advice",
        "indian comic", "motivation", "lotus lane", "shorts"
    ]

    description = (
        f"{strip.get('message', '')}\n\n"
        f'"{strip.get("quote", "")}"\n'
        f"— {strip.get('source', 'Nichiren Daishonin')}\n\n"
        f"The Lotus Lane: Buddhist wisdom for everyday struggles.\n"
        f"New strips every Mon, Wed, Fri.\n\n"
        f"Website: https://tinyurl.com/thelotuslane\n"
        f"Subscribe for daily wisdom: https://zombielabsv2.github.io/lotus-lane/subscribe.html\n\n"
        f"#NichirenBuddhism #BuddhistWisdom #LifeAdvice #Motivation #TheLotusLane #Shorts"
    )

    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags[:30],  # YouTube max 30 tags
            "categoryId": "22",  # People & Blogs
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
    args = parser.parse_args()

    if args.auth:
        do_auth()
        return

    if args.pending:
        show_pending()
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
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        max_per_run = 5  # stay well under YouTube's daily limit (~6)
        uploaded = 0
        failures = []
        for f in sorted(SHORTS_DIR.glob("*.mp4")):
            date_str = f.stem.replace("_narrated", "")
            if date_str < cutoff:
                continue  # skip videos older than 30 days
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
        print("Specify --auth, --date, --latest, --all, or --pending")


if __name__ == "__main__":
    main()
