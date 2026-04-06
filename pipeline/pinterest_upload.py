#!/usr/bin/env python3
"""
Pin Lotus Lane comic strips to Pinterest.

First-time setup:
    python pipeline/pinterest_upload.py --auth
    (Opens browser for Pinterest OAuth2, saves refresh token)

Usage:
    python pipeline/pinterest_upload.py --date 2026-03-31
    python pipeline/pinterest_upload.py --latest
    python pipeline/pinterest_upload.py --all
    python pipeline/pinterest_upload.py --pending
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

STRIPS_JSON = Path(__file__).parent.parent / "strips.json"
TOKEN_FILE = Path(__file__).parent.parent / ".pinterest_token.json"

# Pinterest API v5 endpoints
AUTH_URL = "https://www.pinterest.com/oauth/"
TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
PINS_URL = "https://api.pinterest.com/v5/pins"
SCOPES = "boards:read,pins:read,pins:write"

# Where strip images are hosted
IMAGE_BASE_URL = "https://zombielabsv2.github.io/lotus-lane/strips"
SITE_URL = "https://zombielabsv2.github.io/lotus-lane/"

# Pinterest redirect URI for manual copy-paste flow
REDIRECT_URI = "https://localhost/"

# Base hashtags for all pins
BASE_HASHTAGS = [
    "#NichirenBuddhism", "#BuddhistWisdom", "#Motivation", "#DailyWisdom",
    "#ComicStrip", "#LifeAdvice", "#SelfImprovement", "#Mindfulness",
    "#InnerPeace", "#TheLotusLane",
]

# Category-specific hashtags mapped from strip tags
TAG_HASHTAGS = {
    "work-stress": ["#WorkLifeBalance", "#CareerAdvice", "#BurnoutRecovery", "#ProfessionalGrowth"],
    "relationships": ["#RelationshipAdvice", "#LoveAndLife", "#HealthyRelationships"],
    "family": ["#FamilyLife", "#ParentingWisdom", "#FamilyBonds"],
    "health": ["#MentalHealth", "#WellnessJourney", "#SelfCare", "#HealthyMind"],
    "finances": ["#FinancialWellness", "#MoneyMindset", "#FinancialPeace"],
    "self-doubt": ["#SelfConfidence", "#OvercomingFear", "#BelieveInYourself", "#GrowthMindset"],
    "grief-loss": ["#GriefSupport", "#HealingJourney", "#CopingWithLoss"],
    "perseverance": ["#NeverGiveUp", "#Resilience", "#KeepGoing", "#InnerStrength"],
    "resilience": ["#NeverGiveUp", "#Resilience", "#InnerStrength"],
    "acceptance": ["#Acceptance", "#InnerPeace", "#LetGo"],
    "transformation": ["#Transformation", "#PersonalGrowth", "#ChangeYourLife"],
    "vulnerability": ["#Vulnerability", "#EmotionalIntelligence", "#AuthenticLiving"],
    "hope": ["#Hope", "#Optimism", "#BrighterDays"],
    "inner-strength": ["#InnerStrength", "#SelfBelief", "#Empowerment"],
    "self-care": ["#SelfCare", "#MentalHealthMatters", "#TakeCareOfYourself"],
    "career-growth": ["#CareerGrowth", "#ProfessionalDevelopment", "#Ambition"],
    "parenting": ["#Parenting", "#ParentingTips", "#MindfulParenting"],
    "family-bonds": ["#FamilyLove", "#FamilyFirst"],
    "family-support": ["#FamilySupport", "#Caregiving"],
    "self-reflection": ["#SelfReflection", "#SelfAwareness", "#Introspection"],
}


def load_pinterest_credentials():
    """Load Pinterest app credentials from token file or environment."""
    app_id = os.environ.get("PINTEREST_APP_ID", "")
    app_secret = os.environ.get("PINTEREST_APP_SECRET", "")

    if app_id and app_secret:
        return app_id, app_secret

    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("app_id", ""), data.get("app_secret", "")

    raise ValueError(
        "No Pinterest credentials found.\n"
        "Set PINTEREST_APP_ID and PINTEREST_APP_SECRET environment variables,\n"
        "or run --auth to complete the OAuth2 setup."
    )


def do_auth():
    """Interactive OAuth2 flow -- opens browser, saves refresh token."""
    app_id = os.environ.get("PINTEREST_APP_ID", "")
    app_secret = os.environ.get("PINTEREST_APP_SECRET", "")

    if not app_id:
        app_id = input("Pinterest App ID: ").strip()
    if not app_secret:
        app_secret = input("Pinterest App Secret: ").strip()

    if not app_id or not app_secret:
        print("ERROR: App ID and App Secret are required.")
        sys.exit(1)

    # Step 1: Build authorization URL
    auth_params = {
        "client_id": app_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "response_type": "code",
        "state": "lotuslane",
    }
    auth_url = f"{AUTH_URL}?{urlencode(auth_params)}"

    print(f"\nOpen this URL in your browser:\n\n{auth_url}\n")
    print("After authorizing, you'll be redirected to a localhost URL.")
    print("Copy the FULL redirect URL and paste it below.")
    print("(It will look like: https://localhost/?code=XXXXX&state=lotuslane)\n")

    import webbrowser
    webbrowser.open(auth_url)

    redirect_url = input("Paste the redirect URL: ").strip()

    # Extract authorization code from redirect URL
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)

    if "code" not in params:
        # Maybe they pasted just the code
        code = redirect_url
    else:
        code = params["code"][0]

    # Step 2: Exchange code for tokens
    import base64
    credentials = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()

    response = httpx.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )

    if response.status_code >= 400:
        print(f"Auth error {response.status_code}: {response.text}")
        response.raise_for_status()

    tokens = response.json()

    # Save tokens
    token_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "app_id": app_id,
        "app_secret": app_secret,
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nAuth successful! Tokens saved to {TOKEN_FILE}")
    print("You can now pin strips with --date, --latest, or --all")


def refresh_access_token(refresh_token, app_id, app_secret):
    """Refresh an expired access token."""
    import base64
    credentials = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()

    response = httpx.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_access_token():
    """Get a valid access token, refreshing if needed."""
    # Try environment variables first (for GitHub Actions)
    access_token = os.environ.get("PINTEREST_ACCESS_TOKEN", "")
    if access_token:
        return access_token

    # Try token file
    if not TOKEN_FILE.exists():
        # Check if we have refresh token in env
        refresh_token = os.environ.get("PINTEREST_REFRESH_TOKEN", "")
        app_id = os.environ.get("PINTEREST_APP_ID", "")
        app_secret = os.environ.get("PINTEREST_APP_SECRET", "")
        if all([refresh_token, app_id, app_secret]):
            tokens = refresh_access_token(refresh_token, app_id, app_secret)
            return tokens["access_token"]
        raise ValueError("No Pinterest credentials found. Run --auth first.")

    with open(TOKEN_FILE, encoding="utf-8") as f:
        data = json.load(f)

    # Try stored access token first via a quick API call
    access_token = data.get("access_token", "")
    if access_token:
        test = httpx.get(
            "https://api.pinterest.com/v5/user_account",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if test.status_code == 200:
            return access_token

    # Access token expired — refresh it
    refresh_token = data.get("refresh_token", "")
    app_id = data.get("app_id", "")
    app_secret = data.get("app_secret", "")

    if not all([refresh_token, app_id, app_secret]):
        raise ValueError("Incomplete token data. Run --auth again.")

    tokens = refresh_access_token(refresh_token, app_id, app_secret)

    # Update saved tokens
    data["access_token"] = tokens["access_token"]
    if "refresh_token" in tokens:
        data["refresh_token"] = tokens["refresh_token"]
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return tokens["access_token"]


def get_board_id():
    """Get the Pinterest board ID from environment or prompt."""
    board_id = os.environ.get("PINTEREST_BOARD_ID", "")
    if not board_id:
        # Check token file for saved board_id
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, encoding="utf-8") as f:
                data = json.load(f)
            board_id = data.get("board_id", "")
        if not board_id:
            raise ValueError(
                "PINTEREST_BOARD_ID not set.\n"
                "Set it as an environment variable or add board_id to .pinterest_token.json"
            )
    return board_id


def get_strip_data(date_str):
    """Get strip metadata from strips.json."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    for s in strips:
        if s["date"] == date_str:
            return s
    return None


def save_pin_id(date_str, pin_id):
    """Save the Pinterest pin ID back to strips.json for tracking."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    for s in strips:
        if s["date"] == date_str:
            s["pinterest_pin_id"] = pin_id
            break

    with open(STRIPS_JSON, "w", encoding="utf-8") as f:
        json.dump(strips, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"  [{date_str}] Saved pinterest_pin_id={pin_id} to strips.json")


def build_hashtags(strip):
    """Build a curated hashtag string from strip tags and category."""
    hashtags = list(BASE_HASHTAGS)

    # Add category-specific hashtags
    category = strip.get("category", "")
    if category in TAG_HASHTAGS:
        hashtags.extend(TAG_HASHTAGS[category])

    # Add tag-specific hashtags
    for tag in strip.get("tags", []):
        if tag in TAG_HASHTAGS:
            for h in TAG_HASHTAGS[tag]:
                if h not in hashtags:
                    hashtags.append(h)

    # Pinterest allows up to 20 hashtags — keep it under that
    return " ".join(hashtags[:20])


def build_pin_description(strip):
    """Build a Pinterest-optimized description with message, quote, and hashtags."""
    parts = []

    # Lead with the strip's message
    message = strip.get("message", "")
    if message:
        parts.append(message)

    # Add the Nichiren quote
    quote = strip.get("quote", "")
    source = strip.get("source", "Nichiren Daishonin")
    if quote:
        parts.append(f'"{quote}" -- {source}')

    # Series tagline
    parts.append("The Lotus Lane: Buddhist wisdom for everyday struggles.")
    parts.append("New strips every Mon, Wed, Fri.")

    # Hashtags for Pinterest SEO
    hashtags = build_hashtags(strip)
    parts.append(hashtags)

    return "\n\n".join(parts)


def create_pin(date_str, force=False):
    """Create a Pinterest pin for a given strip date."""
    strip = get_strip_data(date_str)
    if not strip:
        print(f"  [{date_str}] No strip data found in strips.json")
        return False

    if not force and strip.get("pinterest_pin_id"):
        print(f"  [{date_str}] Already pinned (pinterest_pin_id={strip['pinterest_pin_id']}). Use --force to re-pin.")
        return False

    print(f"  [{date_str}] Pinning: {strip['title']}")

    access_token = get_access_token()
    board_id = get_board_id()

    # Build pin title
    title = f"{strip['title']} | The Lotus Lane"
    if len(title) > 100:
        title = f"{strip['title'][:90]} | Lotus Lane"

    # Build description
    description = build_pin_description(strip)

    # Image URL on GitHub Pages
    image_url = f"{IMAGE_BASE_URL}/{date_str}.png"

    # Pinterest API v5 pin creation
    pin_data = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "link": SITE_URL,
        "media_source": {
            "source_type": "image_url",
            "url": image_url,
        },
    }

    response = httpx.post(
        PINS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=pin_data,
        timeout=30,
    )

    if response.status_code >= 400:
        print(f"  Pinterest API error {response.status_code}: {response.text[:500]}")
        response.raise_for_status()

    result = response.json()
    pin_id = result.get("id", "unknown")
    print(f"  [{date_str}] Pinned! https://www.pinterest.com/pin/{pin_id}/")

    # Save pin ID back to strips.json
    if pin_id != "unknown":
        save_pin_id(date_str, pin_id)

    return True


def get_pending_pins():
    """Get strips that haven't been pinned to Pinterest yet."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    return [s for s in strips if not s.get("pinterest_pin_id")]


def show_pending():
    """Display Pinterest pin status of all strips."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    pinned = []
    pending = []

    for s in strips:
        if s.get("pinterest_pin_id"):
            pinned.append(s)
        else:
            pending.append(s)

    print(f"\nPinterest Pin Status")
    print(f"   Total strips: {len(strips)}")
    print(f"   Pinned:       {len(pinned)}")
    print(f"   Pending:      {len(pending)}")

    if pending:
        print(f"\n   Pending ({len(pending)}):")
        for s in pending:
            print(f"   {s['date']} - {s['title']}")

    if pinned:
        print(f"\n   Pinned ({len(pinned)}):")
        for s in pinned:
            pin_url = f"https://www.pinterest.com/pin/{s['pinterest_pin_id']}/"
            print(f"   {s['date']} - {s['title']} -> {pin_url}")

    print()


def get_latest_date():
    """Get the most recent strip date."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    strips.sort(key=lambda s: s["date"], reverse=True)
    return strips[0]["date"] if strips else None


def main():
    parser = argparse.ArgumentParser(description="Pin Lotus Lane comic strips to Pinterest")
    parser.add_argument("--auth", action="store_true", help="Run OAuth2 setup")
    parser.add_argument("--date", help="Pin strip for specific date")
    parser.add_argument("--latest", action="store_true", help="Pin the latest strip")
    parser.add_argument("--all", action="store_true", help="Pin all strips without a pinterest_pin_id")
    parser.add_argument("--pending", action="store_true", help="Show pin status of all strips")
    parser.add_argument("--force", action="store_true", help="Re-pin even if already pinned")
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
            create_pin(date_str, force=args.force)
        else:
            print("No strips found")
    elif args.date:
        create_pin(args.date, force=args.force)
    elif args.all:
        pending = get_pending_pins()
        if not pending:
            print("All strips are already pinned!")
            return

        print(f"  Pinning {len(pending)} strip(s)...")
        pinned = 0
        failures = []

        for strip in pending:
            date_str = strip["date"]
            try:
                result = create_pin(date_str, force=args.force)
                if result:
                    pinned += 1
                    # Rate limit: 2-second delay between pins
                    time.sleep(2)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    print(f"\n  Pinterest rate limit hit. Stopping. Will retry later.")
                    break
                print(f"  FAILED [{date_str}]: {e}")
                failures.append(date_str)
            except Exception as e:
                print(f"  FAILED [{date_str}]: {e}")
                failures.append(date_str)

        print(f"\n  Pinned {pinned} strip(s) this run.")
        if failures:
            print(f"  {len(failures)} failure(s): {', '.join(failures)}")
            sys.exit(1)
    else:
        print("Specify --auth, --date, --latest, --all, or --pending")


if __name__ == "__main__":
    main()
