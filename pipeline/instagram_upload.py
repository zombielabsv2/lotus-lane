#!/usr/bin/env python3
"""
Upload comic strip images and Reels to Instagram via Meta Graph API.

First-time setup:
    python pipeline/instagram_upload.py --auth
    (Prints instructions for Meta Graph API setup)

Token refresh (every ~60 days):
    python pipeline/instagram_upload.py --refresh-token

Usage:
    python pipeline/instagram_upload.py --date 2026-03-31 --type image
    python pipeline/instagram_upload.py --date 2026-03-31 --type reels
    python pipeline/instagram_upload.py --latest
    python pipeline/instagram_upload.py --all
    python pipeline/instagram_upload.py --pending
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).parent.parent
STRIPS_DIR = PROJECT_ROOT / "strips"
SHORTS_DIR = PROJECT_ROOT / "shorts"
STRIPS_JSON = PROJECT_ROOT / "strips.json"
TOKEN_FILE = PROJECT_ROOT / ".instagram_token.json"

# Meta Graph API
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# GitHub Pages base URLs for publicly accessible media
GITHUB_PAGES_BASE = "https://thelotuslane.in"
IMAGE_URL_TEMPLATE = f"{GITHUB_PAGES_BASE}/strips/{{date}}.png"
VIDEO_URL_TEMPLATE = f"{GITHUB_PAGES_BASE}/shorts/{{date}}.mp4"

# Base hashtags (max 30 total)
BASE_HASHTAGS = [
    "#NichirenBuddhism", "#BuddhistWisdom", "#Motivation", "#DailyWisdom",
    "#ComicStrip", "#LifeAdvice", "#Buddhism", "#NamMyohoRengeKyo",
    "#SelfImprovement", "#Mindfulness", "#InnerPeace", "#SpiritualGrowth",
    "#PositiveThinking", "#MentalHealth", "#DailyMotivation",
]

# Category-specific hashtags
CATEGORY_HASHTAGS = {
    "work-stress": ["#WorkLifeBalance", "#BurnoutRecovery", "#CareerGrowth", "#WorkStress", "#ProfessionalGrowth"],
    "relationships": ["#RelationshipAdvice", "#LoveAndLife", "#HealthyRelationships", "#HeartToHeart", "#TrueConnection"],
    "family": ["#FamilyFirst", "#FamilyBonds", "#FamilyLove", "#ParentingJourney", "#FamilyValues"],
    "health": ["#HealthJourney", "#MentalHealthMatters", "#WellnessJourney", "#HealingJourney", "#ChronicIllness"],
    "finances": ["#FinancialWellness", "#MoneyMindset", "#FinancialFreedom", "#DebtFree", "#MoneyWisdom"],
    "self-doubt": ["#SelfLove", "#YouAreEnough", "#OvercomeFear", "#BelieveInYourself", "#GrowthMindset"],
    "grief-loss": ["#GriefJourney", "#HealingHeart", "#RememberingLove", "#CopingWithLoss", "#GriefSupport"],
    "perseverance": ["#NeverGiveUp", "#KeepGoing", "#Perseverance", "#Resilience", "#InnerStrength"],
}

# Reels processing poll settings
REELS_POLL_INTERVAL_SEC = 5
REELS_POLL_MAX_ATTEMPTS = 60  # 5 minutes max wait


def print_auth_instructions():
    """Print step-by-step instructions for Meta Graph API setup."""
    print("""
==========================================================
  Instagram Graph API Setup -- The Lotus Lane
==========================================================

STEP 1: Instagram Business Account
  - Convert your Instagram account to a Business or Creator account
  - Go to Instagram Settings -> Account -> Switch to Professional Account
  - Link it to a Facebook Page you manage

STEP 2: Create a Meta Developer App
  - Go to https://developers.facebook.com/apps/
  - Click "Create App" -> Select "Business" type
  - Add the "Instagram Graph API" product
  - In App Settings -> Basic, note your App ID and App Secret

STEP 3: Get Permissions
  - In your app dashboard, go to Instagram Graph API -> Permissions
  - Request these permissions:
    - instagram_basic
    - instagram_content_publish
    - pages_read_engagement
  - For development/testing, add yourself as a test user

STEP 4: Get Your Instagram User ID
  - Use the Graph API Explorer: https://developers.facebook.com/tools/explorer/
  - Select your app, get a User Access Token with the permissions above
  - Query: GET /me/accounts -- find your Facebook Page ID
  - Query: GET /{page-id}?fields=instagram_business_account
  - The "id" inside instagram_business_account is your IG User ID

STEP 5: Generate a Long-Lived Token
  a) Get a short-lived User Access Token from Graph API Explorer
  b) Exchange it for a long-lived token (60 days):

     curl "https://graph.facebook.com/v21.0/oauth/access_token?\\
       grant_type=fb_exchange_token&\\
       client_id=YOUR_APP_ID&\\
       client_secret=YOUR_APP_SECRET&\\
       fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"

  c) Save the result:

STEP 6: Save Credentials
  Option A -- Environment variables:
    export INSTAGRAM_ACCESS_TOKEN="your-long-lived-token"
    export INSTAGRAM_USER_ID="your-ig-user-id"
    export META_APP_ID="your-app-id"
    export META_APP_SECRET="your-app-secret"

  Option B -- Token file (auto-created by --refresh-token):
    Save to .instagram_token.json:
    {
      "access_token": "your-long-lived-token",
      "user_id": "your-ig-user-id",
      "app_id": "your-app-id",
      "app_secret": "your-app-secret"
    }

STEP 7: Refresh Token Before Expiry
  Long-lived tokens expire in 60 days. Refresh with:
    python pipeline/instagram_upload.py --refresh-token

  Or set up a cron/GitHub Action to refresh monthly.

==========================================================
  After setup, test with:
    python pipeline/instagram_upload.py --date 2026-04-01 --type image
==========================================================
""")


def load_credentials():
    """Load Instagram API credentials from token file or environment."""
    # Try token file first
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        access_token = data.get("access_token", "")
        user_id = data.get("user_id", "")
        app_id = data.get("app_id", "")
        app_secret = data.get("app_secret", "")
        if access_token and user_id:
            return access_token, user_id, app_id, app_secret

    # Fall back to environment variables
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
    user_id = os.environ.get("INSTAGRAM_USER_ID", "")
    app_id = os.environ.get("META_APP_ID", "")
    app_secret = os.environ.get("META_APP_SECRET", "")

    if not access_token or not user_id:
        raise ValueError(
            "No Instagram credentials found.\n"
            "Run --auth for setup instructions, then set env vars or create .instagram_token.json"
        )

    return access_token, user_id, app_id, app_secret


def save_token(access_token, user_id=None, app_id=None, app_secret=None):
    """Save credentials to .instagram_token.json."""
    data = {}
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            data = json.load(f)

    data["access_token"] = access_token
    if user_id:
        data["user_id"] = user_id
    if app_id:
        data["app_id"] = app_id
    if app_secret:
        data["app_secret"] = app_secret

    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  Token saved to {TOKEN_FILE}")


def refresh_token():
    """Exchange current long-lived token for a new long-lived token."""
    access_token, user_id, app_id, app_secret = load_credentials()

    if not app_id or not app_secret:
        raise ValueError(
            "META_APP_ID and META_APP_SECRET required for token refresh.\n"
            "Set them in environment or .instagram_token.json"
        )

    print("  Refreshing Instagram access token...")

    response = httpx.get(
        f"{GRAPH_API_BASE}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": access_token,
        },
        timeout=30,
    )

    if response.status_code >= 400:
        print(f"  Token refresh failed ({response.status_code}): {response.text[:500]}")
        response.raise_for_status()

    result = response.json()
    new_token = result["access_token"]
    expires_in = result.get("expires_in", "unknown")

    save_token(new_token, user_id, app_id, app_secret)
    print(f"  Token refreshed successfully. Expires in {expires_in} seconds (~{int(expires_in) // 86400} days)." if isinstance(expires_in, int) else f"  Token refreshed successfully.")


def get_strip_data(date_str):
    """Get strip metadata from strips.json."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    for s in strips:
        if s["date"] == date_str:
            return s
    return None


def save_instagram_post_id(date_str, post_id):
    """Save the Instagram post ID back to strips.json for upload tracking."""
    from pipeline.utils import safe_update_strips, update_distribution_status

    def _update(strips):
        for s in strips:
            if s["date"] == date_str:
                s["instagram_post_id"] = post_id
                break

    safe_update_strips(_update)
    update_distribution_status(date_str, "instagram", "uploaded", platform_id=post_id)

    print(f"  [{date_str}] Saved instagram_post_id={post_id} to strips.json")


def build_caption(strip):
    """Build an Instagram-optimized caption from strip metadata."""
    title = strip.get("title", "")
    message = strip.get("message", "")
    quote = strip.get("quote", "")
    source = strip.get("source", "Nichiren Daishonin")
    category = strip.get("category", "")

    # Build caption parts
    parts = []

    # Title as first line (bold effect with caps or emoji-free emphasis)
    if title:
        parts.append(title)

    # Message
    if message:
        parts.append(f"\n{message}")

    # Nichiren quote
    if quote:
        parts.append(f'\n"{quote}"')
        parts.append(f"-- {source}")

    # Website
    parts.append("\nThe Lotus Lane: Buddhist wisdom for everyday struggles.")
    parts.append("New strips every Mon, Wed, Fri.")
    parts.append(f"\n{GITHUB_PAGES_BASE}")

    # Hashtags (max 30 total)
    hashtags = list(BASE_HASHTAGS)
    category_tags = CATEGORY_HASHTAGS.get(category, [])
    # Add category-specific tags up to 30 total
    for tag in category_tags:
        if len(hashtags) >= 30:
            break
        if tag not in hashtags:
            hashtags.append(tag)

    # Add generic filler tags if under 30
    filler = ["#TheLotusLane", "#BuddhistComics", "#WisdomComics", "#IndianComics",
              "#AnimatedWisdom", "#DailyInspiration", "#SpiritualAwakening",
              "#ZenWisdom", "#Encouragement", "#LifeLessons",
              "#Dharma", "#LotusLane", "#BuddhistArt", "#ComicArt", "#WebComic"]
    for tag in filler:
        if len(hashtags) >= 30:
            break
        if tag not in hashtags:
            hashtags.append(tag)

    parts.append("\n" + " ".join(hashtags[:30]))

    return "\n".join(parts)


def post_image(date_str, force=False):
    """Post a strip image to Instagram."""
    strip = get_strip_data(date_str)
    if not strip:
        print(f"  [{date_str}] No strip data found in strips.json")
        return False

    if not force and strip.get("instagram_post_id"):
        print(f"  [{date_str}] Already posted (instagram_post_id={strip['instagram_post_id']}). Use --force to re-post.")
        return False

    access_token, user_id, _, _ = load_credentials()
    image_url = IMAGE_URL_TEMPLATE.format(date=date_str)
    caption = build_caption(strip)

    print(f"  [{date_str}] Posting image: {strip['title']}")
    print(f"  [{date_str}] Image URL: {image_url}")

    # Step 1: Create media container
    response = httpx.post(
        f"{GRAPH_API_BASE}/{user_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=60,
    )

    if response.status_code >= 400:
        print(f"  [{date_str}] Create container failed ({response.status_code}): {response.text[:500]}")
        response.raise_for_status()

    creation_id = response.json()["id"]
    print(f"  [{date_str}] Container created: {creation_id}")

    # Step 2: Publish
    publish_response = httpx.post(
        f"{GRAPH_API_BASE}/{user_id}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": access_token,
        },
        timeout=60,
    )

    if publish_response.status_code >= 400:
        print(f"  [{date_str}] Publish failed ({publish_response.status_code}): {publish_response.text[:500]}")
        publish_response.raise_for_status()

    post_id = publish_response.json()["id"]
    print(f"  [{date_str}] Published! Post ID: {post_id}")

    save_instagram_post_id(date_str, post_id)
    return True


def post_reels(date_str, force=False):
    """Post a Reel to Instagram using a publicly hosted video."""
    strip = get_strip_data(date_str)
    if not strip:
        print(f"  [{date_str}] No strip data found in strips.json")
        return False

    if not force and strip.get("instagram_post_id"):
        print(f"  [{date_str}] Already posted (instagram_post_id={strip['instagram_post_id']}). Use --force to re-post.")
        return False

    access_token, user_id, _, _ = load_credentials()
    video_url = VIDEO_URL_TEMPLATE.format(date=date_str)
    caption = build_caption(strip)

    print(f"  [{date_str}] Posting Reel: {strip['title']}")
    print(f"  [{date_str}] Video URL: {video_url}")

    # Step 1: Create Reels container
    response = httpx.post(
        f"{GRAPH_API_BASE}/{user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=60,
    )

    if response.status_code >= 400:
        print(f"  [{date_str}] Create Reels container failed ({response.status_code}): {response.text[:500]}")
        response.raise_for_status()

    creation_id = response.json()["id"]
    print(f"  [{date_str}] Reels container created: {creation_id}")

    # Step 2: Wait for video processing
    print(f"  [{date_str}] Waiting for video processing...", end="", flush=True)
    for attempt in range(REELS_POLL_MAX_ATTEMPTS):
        time.sleep(REELS_POLL_INTERVAL_SEC)

        status_response = httpx.get(
            f"{GRAPH_API_BASE}/{creation_id}",
            params={
                "fields": "status_code",
                "access_token": access_token,
            },
            timeout=30,
        )

        if status_response.status_code >= 400:
            print(f"\n  [{date_str}] Status check failed ({status_response.status_code}): {status_response.text[:300]}")
            status_response.raise_for_status()

        status_code = status_response.json().get("status_code", "")

        if status_code == "FINISHED":
            print(" done!")
            break
        elif status_code == "ERROR":
            error_msg = status_response.json().get("status", "Unknown error")
            print(f"\n  [{date_str}] Video processing failed: {error_msg}")
            return False
        else:
            print(".", end="", flush=True)
    else:
        print(f"\n  [{date_str}] Video processing timed out after {REELS_POLL_MAX_ATTEMPTS * REELS_POLL_INTERVAL_SEC}s")
        return False

    # Step 3: Publish
    publish_response = httpx.post(
        f"{GRAPH_API_BASE}/{user_id}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": access_token,
        },
        timeout=60,
    )

    if publish_response.status_code >= 400:
        print(f"  [{date_str}] Publish failed ({publish_response.status_code}): {publish_response.text[:500]}")
        publish_response.raise_for_status()

    post_id = publish_response.json()["id"]
    print(f"  [{date_str}] Reel published! Post ID: {post_id}")

    save_instagram_post_id(date_str, post_id)
    return True


def post_strip(date_str, post_type="reels", force=False):
    """Post a strip to Instagram (image or reels)."""
    if post_type == "image":
        return post_image(date_str, force=force)
    else:
        return post_reels(date_str, force=force)


def get_pending_posts():
    """Get strips that don't have instagram_post_id in strips.json."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    pending = []
    for s in strips:
        if not s.get("instagram_post_id"):
            pending.append(s)

    return pending


def show_pending():
    """Display Instagram post status of all strips."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    posted = []
    pending = []

    for s in strips:
        if s.get("instagram_post_id"):
            posted.append(s)
        else:
            pending.append(s)

    print(f"\nInstagram Post Status")
    print(f"   Total strips: {len(strips)}")
    print(f"   Posted:       {len(posted)}")
    print(f"   Pending:      {len(pending)}")

    if pending:
        print(f"\n   Pending ({len(pending)}):")
        for s in pending:
            has_video = (SHORTS_DIR / f"{s['date']}.mp4").exists()
            video_tag = " [video]" if has_video else " [image only]"
            print(f"   {s['date']} - {s['title']}{video_tag}")

    if posted:
        print(f"\n   Posted ({len(posted)}):")
        for s in posted:
            print(f"   {s['date']} - {s['title']} -> {s['instagram_post_id']}")

    print()


def get_latest_date():
    """Get the most recent strip date."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    strips.sort(key=lambda s: s["date"], reverse=True)
    return strips[0]["date"] if strips else None


def main():
    parser = argparse.ArgumentParser(description="Upload Lotus Lane strips to Instagram")
    parser.add_argument("--auth", action="store_true", help="Print Meta Graph API setup instructions")
    parser.add_argument("--date", help="Post strip for specific date")
    parser.add_argument("--latest", action="store_true", help="Post the latest strip")
    parser.add_argument("--all", action="store_true", help="Post all strips without instagram_post_id")
    parser.add_argument("--pending", action="store_true", help="Show Instagram post status of all strips")
    parser.add_argument("--type", choices=["image", "reels"], default="reels",
                        help="Post type: image or reels (default: reels)")
    parser.add_argument("--force", action="store_true", help="Re-post even if already posted")
    parser.add_argument("--refresh-token", action="store_true", help="Refresh long-lived access token")
    args = parser.parse_args()

    if args.auth:
        print_auth_instructions()
        return

    if args.refresh_token:
        refresh_token()
        return

    if args.pending:
        show_pending()
        return

    if args.latest:
        date_str = get_latest_date()
        if date_str:
            post_strip(date_str, post_type=args.type, force=args.force)
        else:
            print("No strips found")
    elif args.date:
        post_strip(args.date, post_type=args.type, force=args.force)
    elif args.all:
        pending = get_pending_posts()
        if not pending:
            print("  All strips already posted to Instagram.")
            return

        max_per_run = 10  # Instagram rate limits are more generous than YouTube
        posted = 0
        failures = []

        print(f"  {len(pending)} strips pending. Posting up to {max_per_run}...")

        for strip in pending[:max_per_run]:
            date_str = strip["date"]
            try:
                # Use reels if video exists, otherwise image
                has_video = (SHORTS_DIR / f"{date_str}.mp4").exists()
                effective_type = args.type
                if effective_type == "reels" and not has_video:
                    effective_type = "image"

                result = post_strip(date_str, post_type=effective_type, force=args.force)
                if result:
                    posted += 1
            except httpx.HTTPStatusError as e:
                error_text = e.response.text[:300] if e.response else str(e)
                if "rate limit" in error_text.lower() or e.response.status_code == 429:
                    print(f"\n  Instagram rate limit reached. Stopping. Will retry later.")
                    break
                print(f"  FAILED [{date_str}]: {error_text}")
                failures.append(date_str)
            except Exception as e:
                print(f"  FAILED [{date_str}]: {e}")
                failures.append(date_str)

        remaining = len(pending) - posted - len(failures)
        print(f"\n  Posted {posted} strip(s) this run. {remaining} remaining.")
        if failures:
            print(f"  {len(failures)} failure(s): {', '.join(failures)}")
            sys.exit(1)
    else:
        print("Specify --auth, --date, --latest, --all, --pending, or --refresh-token")


if __name__ == "__main__":
    main()
