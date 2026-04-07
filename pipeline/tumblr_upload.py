#!/usr/bin/env python3
"""
Upload comic strip images to Tumblr.

First-time setup:
    1. Register app at https://www.tumblr.com/oauth/apps
    2. python pipeline/tumblr_upload.py --auth
       (Manual copy-paste redirect flow, saves tokens)

Usage:
    python pipeline/tumblr_upload.py --date 2026-03-31
    python pipeline/tumblr_upload.py --latest
    python pipeline/tumblr_upload.py --all
    python pipeline/tumblr_upload.py --pending
"""

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

import httpx

STRIPS_DIR = Path(__file__).parent.parent / "strips"
STRIPS_JSON = Path(__file__).parent.parent / "strips.json"
TOKEN_FILE = Path(__file__).parent.parent / ".tumblr_token.json"

# Tumblr OAuth2 endpoints
AUTH_URL = "https://www.tumblr.com/oauth2/authorize"
TOKEN_URL = "https://api.tumblr.com/v2/oauth2/token"
API_BASE = "https://api.tumblr.com/v2"
REDIRECT_URI = "http://localhost:8888/callback"

# Hosted strip base URL
STRIP_BASE_URL = "https://zombielabsv2.github.io/lotus-lane/strips"

# Default tags added to every post
DEFAULT_TAGS = [
    "nichiren buddhism", "buddhism", "buddhist wisdom", "comic strip",
    "motivation", "daily wisdom", "lotus lane", "nichiren daishonin",
    "self improvement", "life advice",
]


def load_client_config():
    """Load OAuth2 client credentials from token file or environment."""
    consumer_key = os.environ.get("TUMBLR_CONSUMER_KEY", "")
    consumer_secret = os.environ.get("TUMBLR_CONSUMER_SECRET", "")
    if consumer_key and consumer_secret:
        return consumer_key, consumer_secret

    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        ck = data.get("consumer_key", "")
        cs = data.get("consumer_secret", "")
        if ck and cs:
            return ck, cs

    raise ValueError(
        "Tumblr consumer key/secret not found.\n"
        "Set TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET env vars,\n"
        "or run --auth to set up credentials."
    )


def get_blog_name():
    """Get the Tumblr blog identifier from env or token file."""
    blog = os.environ.get("TUMBLR_BLOG_NAME", "")
    if blog:
        return blog

    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        blog = data.get("blog_name", "")
        if blog:
            return blog

    raise ValueError(
        "Tumblr blog name not found.\n"
        "Set TUMBLR_BLOG_NAME env var or include blog_name in .tumblr_token.json"
    )


def do_auth():
    """Interactive OAuth2 flow — manual copy-paste redirect."""
    print("\n=== Tumblr OAuth2 Setup ===\n")
    print("1. Register your app at https://www.tumblr.com/oauth/apps")
    print("2. Set the OAuth redirect URL to: http://localhost:8888/callback")
    print()

    consumer_key = input("Consumer Key (API Key): ").strip()
    consumer_secret = input("Consumer Secret: ").strip()
    blog_name = input("Blog name (e.g. thelotuslane): ").strip()

    if not all([consumer_key, consumer_secret, blog_name]):
        print("All fields are required.")
        sys.exit(1)

    # Step 1: Build authorization URL
    auth_params = {
        "client_id": consumer_key,
        "response_type": "code",
        "scope": "write",
        "redirect_uri": REDIRECT_URI,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    print(f"\nOpen this URL in your browser:\n\n{auth_url}\n")
    print("After authorizing, you'll be redirected to a localhost URL.")
    print("Copy the FULL redirect URL and paste it below:")

    import webbrowser
    webbrowser.open(auth_url)

    redirect_url = input("\nRedirect URL: ").strip()

    # Extract authorization code from redirect URL
    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    code = params.get("code", [None])[0]

    if not code:
        print("Could not extract authorization code from URL.")
        sys.exit(1)

    # Step 2: Exchange code for tokens
    response = httpx.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": consumer_key,
        "client_secret": consumer_secret,
        "redirect_uri": REDIRECT_URI,
    }, timeout=30)

    if response.status_code >= 400:
        print(f"Token exchange failed ({response.status_code}): {response.text[:500]}")
        sys.exit(1)

    tokens = response.json()

    # Save tokens
    token_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "consumer_key": consumer_key,
        "consumer_secret": consumer_secret,
        "blog_name": blog_name,
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nAuth successful! Tokens saved to {TOKEN_FILE}")
    print(f"Blog: {blog_name}")
    print("You can now post strips with --date or --latest")


def get_access_token():
    """Get a valid access token, refreshing if needed."""
    # Try environment variable first (for GitHub Actions)
    env_token = os.environ.get("TUMBLR_ACCESS_TOKEN", "")
    if env_token:
        return env_token

    # Try token file
    if not TOKEN_FILE.exists():
        raise ValueError("No Tumblr credentials found. Run --auth first.")

    with open(TOKEN_FILE, encoding="utf-8") as f:
        data = json.load(f)

    access_token = data.get("access_token", "")
    if not access_token:
        raise ValueError("No access_token in token file. Run --auth again.")

    # Test if token is still valid
    test_resp = httpx.get(
        f"{API_BASE}/user/info",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )

    if test_resp.status_code == 200:
        return access_token

    # Token expired — try refresh
    refresh_token = data.get("refresh_token", "")
    consumer_key = data.get("consumer_key", "")
    consumer_secret = data.get("consumer_secret", "")

    if not all([refresh_token, consumer_key, consumer_secret]):
        raise ValueError("Token expired and no refresh credentials available. Run --auth again.")

    print("  Access token expired, refreshing...")
    response = httpx.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": consumer_key,
        "client_secret": consumer_secret,
    }, timeout=30)

    if response.status_code >= 400:
        raise ValueError(
            f"Token refresh failed ({response.status_code}): {response.text[:300]}\n"
            "Run --auth again."
        )

    tokens = response.json()
    data["access_token"] = tokens["access_token"]
    if tokens.get("refresh_token"):
        data["refresh_token"] = tokens["refresh_token"]

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("  Token refreshed successfully.")
    return tokens["access_token"]


def get_strip_data(date_str):
    """Get strip metadata from strips.json."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    for s in strips:
        if s["date"] == date_str:
            return s
    return None


def save_tumblr_post_id(date_str, post_id):
    """Save the Tumblr post ID back to strips.json for upload tracking."""
    from pipeline.utils import safe_update_strips, update_distribution_status

    def _update(strips):
        for s in strips:
            if s["date"] == date_str:
                s["tumblr_post_id"] = post_id
                break

    safe_update_strips(_update)
    update_distribution_status(date_str, "tumblr", "uploaded", platform_id=post_id)

    print(f"  [{date_str}] Saved tumblr_post_id={post_id} to strips.json")


def get_pending_strips():
    """Get strips that have images but haven't been posted to Tumblr."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    pending = []
    for s in strips:
        image_path = STRIPS_DIR / f"{s['date']}.png"
        if image_path.exists() and not s.get("tumblr_post_id"):
            pending.append(s)

    return pending


def show_pending():
    """Display Tumblr posting status of all strips."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    no_image = []
    pending_post = []
    posted = []

    for s in strips:
        image_path = STRIPS_DIR / f"{s['date']}.png"
        if s.get("tumblr_post_id"):
            posted.append(s)
        elif image_path.exists():
            pending_post.append(s)
        else:
            no_image.append(s)

    blog = get_blog_name() if posted else "unknown"

    print(f"\n📊 Tumblr Post Status")
    print(f"   Total strips: {len(strips)}")
    print(f"   Posted:       {len(posted)}")
    print(f"   Pending:      {len(pending_post)}")
    print(f"   No image:     {len(no_image)}")

    if pending_post:
        print(f"\n⏳ Pending post ({len(pending_post)}):")
        for s in pending_post:
            print(f"   {s['date']} - {s['title']}")

    if posted:
        print(f"\n✅ Posted ({len(posted)}):")
        for s in posted:
            print(f"   {s['date']} - {s['title']} → https://{blog}.tumblr.com/post/{s['tumblr_post_id']}")

    if no_image:
        print(f"\n🖼️  No image ({len(no_image)}):")
        for s in no_image:
            print(f"   {s['date']} - {s['title']}")

    print()


def build_npf_content(strip, image_media):
    """Build Neue Post Format (NPF) content blocks for a strip."""
    blocks = []

    # 1. Image block with the strip
    blocks.append({
        "type": "image",
        "media": [image_media],
        "alt_text": f"The Lotus Lane comic strip: {strip['title']}",
    })

    # 2. Title heading
    blocks.append({
        "type": "text",
        "text": strip["title"],
        "subtype": "heading1",
    })

    # 3. Message
    message = strip.get("message", "")
    if message:
        blocks.append({
            "type": "text",
            "text": message,
        })

    # 4. Nichiren quote (italic/indented)
    quote = strip.get("quote", "")
    if quote:
        blocks.append({
            "type": "text",
            "text": f"\u201c{quote}\u201d",
            "subtype": "indented",
            "formatting": [
                {
                    "start": 0,
                    "end": len(quote) + 2,  # +2 for curly quotes
                    "type": "italic",
                }
            ],
        })

    # 5. Source attribution
    source = strip.get("source", "Nichiren Daishonin")
    blocks.append({
        "type": "text",
        "text": f"\u2014 {source}",
        "subtype": "indented",
    })

    return blocks


def upload_image(access_token, blog, image_path):
    """Upload an image to Tumblr and return the media object for NPF.

    Uses the Tumblr content/block media upload via the post creation endpoint.
    For NPF posts, we can include the image as a URL or upload inline.
    """
    # Read the image file
    with open(image_path, "rb") as f:
        image_data = f.read()

    filename = image_path.name

    # Upload via the blog's media endpoint (undocumented but works)
    # Actually, Tumblr NPF supports inline media upload via multipart on the posts endpoint.
    # The simpler approach: use the hosted URL since strips are on GitHub Pages.
    # But we also support local upload as fallback.

    # Try the direct upload approach
    # Tumblr doesn't have a separate media upload endpoint for NPF —
    # instead we use the hosted URL from GitHub Pages.
    date_str = image_path.stem
    hosted_url = f"{STRIP_BASE_URL}/{date_str}.png"

    # Verify the hosted image exists
    try:
        head_resp = httpx.head(hosted_url, timeout=10, follow_redirects=True)
        if head_resp.status_code == 200:
            return {"type": "image/png", "url": hosted_url}
    except httpx.HTTPError:
        pass

    # Fallback: upload via Tumblr's legacy photo post isn't ideal for NPF.
    # Use the multipart content upload on the posts endpoint instead.
    # We return a placeholder that post_strip will handle via multipart.
    print(f"  Hosted image not reachable at {hosted_url}, will upload inline.")
    return {"type": "image/png", "identifier": "strip-image", "_local_path": str(image_path)}


def post_strip(date_str, force=False):
    """Post a strip to Tumblr for a given date."""
    image_path = STRIPS_DIR / f"{date_str}.png"
    if not image_path.exists():
        print(f"  [{date_str}] No image found at {image_path}")
        return False

    strip = get_strip_data(date_str)
    if not strip:
        print(f"  [{date_str}] No strip data found in strips.json")
        return False

    if not force and strip.get("tumblr_post_id"):
        print(f"  [{date_str}] Already posted (tumblr_post_id={strip['tumblr_post_id']}). Use --force to re-post.")
        return False

    print(f"  [{date_str}] Posting: {strip['title']}")

    access_token = get_access_token()
    blog = get_blog_name()

    # Build tags
    strip_tags = strip.get("tags", [])
    tags = list(dict.fromkeys(strip_tags + DEFAULT_TAGS))  # deduplicate, preserve order

    # Try hosted URL first
    hosted_url = f"{STRIP_BASE_URL}/{date_str}.png"
    use_hosted = False

    try:
        head_resp = httpx.head(hosted_url, timeout=10, follow_redirects=True)
        if head_resp.status_code == 200:
            use_hosted = True
    except httpx.HTTPError:
        pass

    if use_hosted:
        # Use NPF with hosted image URL
        image_media = {"type": "image/png", "url": hosted_url}
        content_blocks = build_npf_content(strip, image_media)

        post_body = {
            "content": content_blocks,
            "tags": ",".join(tags),
            "state": "published",
        }

        response = httpx.post(
            f"{API_BASE}/blog/{blog}/posts",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=post_body,
            timeout=60,
        )
    else:
        # Upload image inline via multipart form
        print(f"  [{date_str}] Hosted image not available, uploading inline...")
        image_media = {"type": "image/png", "identifier": "strip-image"}
        content_blocks = build_npf_content(strip, image_media)

        post_data = {
            "content": content_blocks,
            "tags": ",".join(tags),
            "state": "published",
        }

        with open(image_path, "rb") as f:
            image_data = f.read()

        # Tumblr NPF multipart: JSON body as "json" part, image as "strip-image" part
        response = httpx.post(
            f"{API_BASE}/blog/{blog}/posts",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
            data={"json": json.dumps(post_data)},
            files={"strip-image": (f"{date_str}.png", image_data, "image/png")},
            timeout=60,
        )

    if response.status_code >= 400:
        print(f"  Tumblr API error {response.status_code}: {response.text[:500]}")
        response.raise_for_status()

    result = response.json()
    post_id = str(result.get("response", {}).get("id", "unknown"))

    print(f"  [{date_str}] Posted! https://{blog}.tumblr.com/post/{post_id}")

    if post_id != "unknown":
        save_tumblr_post_id(date_str, post_id)

    return True


def get_latest_date():
    """Get the most recent strip date."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    strips.sort(key=lambda s: s["date"], reverse=True)
    return strips[0]["date"] if strips else None


def main():
    parser = argparse.ArgumentParser(description="Post Lotus Lane strips to Tumblr")
    parser.add_argument("--auth", action="store_true", help="Run OAuth2 setup")
    parser.add_argument("--date", help="Post strip for specific date")
    parser.add_argument("--latest", action="store_true", help="Post the latest strip")
    parser.add_argument("--all", action="store_true", help="Post all unposted strips")
    parser.add_argument("--pending", action="store_true", help="Show posting status of all strips")
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
        if date_str:
            post_strip(date_str, force=args.force)
        else:
            print("No strips found")
    elif args.date:
        post_strip(args.date, force=args.force)
    elif args.all:
        pending = get_pending_strips()
        if not pending:
            print("  All strips already posted to Tumblr.")
            return

        print(f"  {len(pending)} strip(s) to post...")
        posted = 0
        failures = []

        for strip in pending:
            date_str = strip["date"]
            try:
                result = post_strip(date_str, force=args.force)
                if result:
                    posted += 1
            except httpx.HTTPStatusError as e:
                error_text = str(e.response.text) if hasattr(e, "response") else str(e)
                if "rate_limit" in error_text.lower() or e.response.status_code == 429:
                    print(f"\n  Tumblr rate limit reached. Stopping. Will retry later.")
                    break
                print(f"  FAILED [{date_str}]: {e}")
                failures.append(date_str)
            except Exception as e:
                print(f"  FAILED [{date_str}]: {e}")
                failures.append(date_str)

        print(f"\n  Posted {posted} strip(s) this run.")
        if failures:
            print(f"  {len(failures)} failure(s): {', '.join(failures)}")
            sys.exit(1)
    else:
        print("Specify --auth, --date, --latest, --all, or --pending")


if __name__ == "__main__":
    main()
