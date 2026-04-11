#!/usr/bin/env python3
"""
Post Lotus Lane comic strips to Reddit — targeting universal human struggle subreddits.

Strategy: lead with the PROBLEM, not the tradition. A comic strip about dealing
with envy, attributed to "a 13th-century philosopher," lands differently than
"Nichiren Daishonin says..." in r/selfimprovement.

First-time setup:
    python pipeline/reddit_upload.py --auth
    (Requires Reddit app credentials — create at https://www.reddit.com/prefs/apps)

Usage:
    python pipeline/reddit_upload.py --date 2026-04-10
    python pipeline/reddit_upload.py --latest
    python pipeline/reddit_upload.py --pending
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

STRIPS_JSON = Path(__file__).parent.parent / "strips.json"
TOKEN_FILE = Path(__file__).parent.parent / ".reddit_token.json"

# Reddit API
AUTH_URL = "https://www.reddit.com/api/v1/authorize"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"
USER_AGENT = "TheLotusLane/1.0 (by /u/TheLotusLane)"

SITE_URL = "https://thelotuslane.in"

# Target subreddits mapped by strip category — universal human struggle subs
# NOT Buddhist subreddits (those audiences will find us organically)
CATEGORY_SUBREDDITS = {
    "work-stress": ["selfimprovement", "getdisciplined", "careerguidance"],
    "relationships": ["selfimprovement", "DecidingToBeBetter", "relationship_advice"],
    "family": ["selfimprovement", "DecidingToBeBetter", "Parenting"],
    "health": ["selfimprovement", "mentalhealth", "DecidingToBeBetter"],
    "finances": ["selfimprovement", "getdisciplined", "personalfinance"],
    "self-doubt": ["selfimprovement", "DecidingToBeBetter", "getdisciplined"],
    "grief-loss": ["selfimprovement", "GriefSupport", "DecidingToBeBetter"],
    "perseverance": ["selfimprovement", "getdisciplined", "DecidingToBeBetter"],
    "anger": ["selfimprovement", "DecidingToBeBetter", "mentalhealth"],
    "loneliness": ["selfimprovement", "DecidingToBeBetter", "mentalhealth"],
    "envy": ["selfimprovement", "DecidingToBeBetter", "Stoicism"],
}

# Default subreddit if category not mapped
DEFAULT_SUBREDDIT = "selfimprovement"


def load_reddit_credentials():
    """Load Reddit app credentials from env or token file."""
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    if client_id and client_secret:
        return client_id, client_secret

    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("client_id", ""), data.get("client_secret", "")

    raise ValueError(
        "No Reddit credentials found.\n"
        "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET,\n"
        "or run --auth to set up."
    )


def do_auth():
    """Interactive setup — saves credentials and gets initial token."""
    client_id = input("Reddit App Client ID: ").strip()
    client_secret = input("Reddit App Client Secret: ").strip()
    username = input("Reddit Username: ").strip()
    password = input("Reddit Password: ").strip()

    if not all([client_id, client_secret, username, password]):
        print("All fields required.")
        sys.exit(1)

    # Get access token via password grant (script-type app)
    response = httpx.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    tokens = response.json()

    token_data = {
        "access_token": tokens["access_token"],
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password,  # Needed for re-auth (script apps)
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nAuth successful! Token saved to {TOKEN_FILE}")


def get_access_token():
    """Get a valid access token."""
    access_token = os.environ.get("REDDIT_ACCESS_TOKEN", "")
    if access_token:
        return access_token

    if not TOKEN_FILE.exists():
        raise ValueError("No Reddit credentials. Run --auth first.")

    with open(TOKEN_FILE, encoding="utf-8") as f:
        data = json.load(f)

    # Re-authenticate (script apps use password grant, tokens expire in 1h)
    client_id = data.get("client_id", "")
    client_secret = data.get("client_secret", "")
    username = data.get("username", "")
    password = data.get("password", "")

    response = httpx.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    tokens = response.json()

    # Update saved token
    data["access_token"] = tokens["access_token"]
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return tokens["access_token"]


def build_post_title(strip):
    """Build a Reddit post title — problem-first, no Buddhist jargon."""
    topic = strip.get("topic", "")
    title = strip.get("title", "")
    message = strip.get("message", "")

    # Use strip title directly if it's already problem-first
    # Add [Comic] tag for Reddit format
    return f"[Comic] {title}"


def build_post_body(strip):
    """Build the Reddit post body — relatable, not preachy."""
    message = strip.get("message", "")
    quote = strip.get("quote", "")
    source = strip.get("source", "")
    topic = strip.get("topic", "")
    date = strip.get("date", "")
    strip_url = f"{SITE_URL}/strips/{date}.html"

    parts = []

    if message:
        parts.append(message)

    if quote:
        # Attribution: use "ancient philosopher" framing for non-Buddhist subs
        if "Ikeda" in source:
            attr = f"— {source}"
        else:
            attr = f"— From a letter written in the 1200s ({source})"
        parts.append(f'> "{quote}"\n>\n> {attr}')

    parts.append(f"[Read the full comic strip]({strip_url})")
    parts.append(
        "---\n"
        "*The Lotus Lane is a comic series about everyday people dealing with "
        "everyday struggles — and the ancient wisdom that helps them through. "
        "New strips Mon/Wed/Fri.*"
    )

    return "\n\n".join(parts)


def pick_subreddit(strip):
    """Pick the best subreddit for this strip's category."""
    category = strip.get("category", "")
    subs = CATEGORY_SUBREDDITS.get(category, [DEFAULT_SUBREDDIT])
    # Pick the first (primary) subreddit
    return subs[0]


def submit_post(strip, subreddit=None, force=False):
    """Submit a strip as a link post to Reddit."""
    date_str = strip.get("date", "")

    if not force and strip.get("reddit_post_id"):
        print(f"  [{date_str}] Already posted (reddit_post_id={strip['reddit_post_id']})")
        return False

    if subreddit is None:
        subreddit = pick_subreddit(strip)

    title = build_post_title(strip)
    body = build_post_body(strip)

    print(f"  [{date_str}] Posting to r/{subreddit}: {title}")

    access_token = get_access_token()

    response = httpx.post(
        f"{API_BASE}/api/submit",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
        },
        data={
            "kind": "self",  # Text post with body
            "sr": subreddit,
            "title": title,
            "text": body,
            "sendreplies": "true",
        },
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()

    # Extract post ID
    post_data = result.get("json", {}).get("data", {})
    post_id = post_data.get("id", "")
    post_url = post_data.get("url", "")

    if post_id:
        print(f"  [{date_str}] Posted! {post_url}")
        save_reddit_id(date_str, post_id, subreddit)
    else:
        errors = result.get("json", {}).get("errors", [])
        if errors:
            print(f"  [{date_str}] Reddit errors: {errors}")
            return False

    return True


def save_reddit_id(date_str, post_id, subreddit):
    """Save Reddit post ID back to strips.json."""
    from pipeline.utils import safe_update_strips, update_distribution_status

    def _update(strips):
        for s in strips:
            if s["date"] == date_str:
                s["reddit_post_id"] = post_id
                s["reddit_subreddit"] = subreddit
                break

    safe_update_strips(_update)
    update_distribution_status(date_str, "reddit", "uploaded", platform_id=post_id)
    print(f"  [{date_str}] Saved reddit_post_id={post_id} to strips.json")


def get_pending():
    """Get strips not yet posted to Reddit."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    return [s for s in strips if not s.get("reddit_post_id")]


def show_pending():
    """Show Reddit post status."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    posted = [s for s in strips if s.get("reddit_post_id")]
    pending = [s for s in strips if not s.get("reddit_post_id")]

    print(f"\nReddit Post Status")
    print(f"  Total: {len(strips)}, Posted: {len(posted)}, Pending: {len(pending)}")

    if pending:
        print(f"\n  Pending ({len(pending)}):")
        for s in pending:
            sub = pick_subreddit(s)
            print(f"    {s['date']} - {s['title']} -> r/{sub}")

    if posted:
        print(f"\n  Posted ({len(posted)}):")
        for s in posted:
            sub = s.get("reddit_subreddit", "?")
            print(f"    {s['date']} - {s['title']} (r/{sub})")

    print()


def get_latest_date():
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    strips.sort(key=lambda s: s["date"], reverse=True)
    return strips[0]["date"] if strips else None


def main():
    parser = argparse.ArgumentParser(description="Post Lotus Lane strips to Reddit")
    parser.add_argument("--auth", action="store_true", help="Set up Reddit credentials")
    parser.add_argument("--date", help="Post strip for specific date")
    parser.add_argument("--latest", action="store_true", help="Post the latest strip")
    parser.add_argument("--all", action="store_true", help="Post all un-posted strips")
    parser.add_argument("--pending", action="store_true", help="Show post status")
    parser.add_argument("--subreddit", help="Override target subreddit")
    parser.add_argument("--force", action="store_true", help="Re-post even if already posted")
    args = parser.parse_args()

    if args.auth:
        do_auth()
        return

    if args.pending:
        show_pending()
        return

    if args.latest:
        date_str = get_latest_date()
        if not date_str:
            print("No strips found")
            return
        strip = next(s for s in json.loads(STRIPS_JSON.read_text()) if s["date"] == date_str)
        submit_post(strip, subreddit=args.subreddit, force=args.force)

    elif args.date:
        strips = json.loads(STRIPS_JSON.read_text())
        strip = next((s for s in strips if s["date"] == args.date), None)
        if not strip:
            print(f"No strip for {args.date}")
            return
        submit_post(strip, subreddit=args.subreddit, force=args.force)

    elif args.all:
        pending = get_pending()
        if not pending:
            print("All strips already posted!")
            return

        print(f"  Posting {len(pending)} strip(s)...")
        posted_count = 0
        for strip in pending:
            try:
                if submit_post(strip, subreddit=args.subreddit, force=args.force):
                    posted_count += 1
                    # Reddit rate limit: 10 min between posts for new accounts
                    time.sleep(10)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    print(f"\n  Reddit rate limit. Stopping. Retry later.")
                    break
                print(f"  FAILED [{strip['date']}]: {e}")
            except Exception as e:
                print(f"  FAILED [{strip['date']}]: {e}")

        print(f"\n  Posted {posted_count} strip(s).")
    else:
        print("Specify --auth, --date, --latest, --all, or --pending")


if __name__ == "__main__":
    main()
