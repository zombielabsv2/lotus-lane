"""
Daimoku Daily — Subscriber management utilities.

The subscribe form uses direct Supabase REST API calls from frontend JavaScript
(with the publishable/anon key). This module provides utilities for:
- Manual subscriber management
- Unsubscribe processing
- Subscriber stats
- Growth dashboard (--dashboard mode)
"""

import argparse
import os
from datetime import datetime, timedelta, timezone

import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def list_subscribers(active_only: bool = True) -> list[dict]:
    """List all subscribers."""
    params = {"select": "*", "order": "subscribed_at.desc"}
    if active_only:
        params["active"] = "eq.true"

    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/daimoku_subscribers",
        headers=_headers(),
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def unsubscribe(email: str) -> bool:
    """Deactivate a subscriber by email."""
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/daimoku_subscribers",
        headers={**_headers(), "Prefer": "return=minimal"},
        params={"email": f"eq.{email}"},
        json={"active": False},
        timeout=30,
    )
    return resp.status_code in (200, 204)


def get_stats() -> dict:
    """Get subscriber statistics."""
    all_subs = list_subscribers(active_only=False)
    active = [s for s in all_subs if s.get("active")]
    inactive = [s for s in all_subs if not s.get("active")]

    # Frequency breakdown
    freq_counts = {}
    for s in active:
        freq = s.get("frequency", "weekly")
        freq_counts[freq] = freq_counts.get(freq, 0) + 1

    # Challenge breakdown
    challenge_counts = {}
    for s in active:
        for c in s.get("challenges", []):
            challenge_counts[c] = challenge_counts.get(c, 0) + 1

    return {
        "total": len(all_subs),
        "active": len(active),
        "inactive": len(inactive),
        "by_frequency": freq_counts,
        "by_challenge": dict(sorted(challenge_counts.items(), key=lambda x: -x[1])),
    }


def _supabase_get(endpoint: str, params: dict = None) -> list:
    """GET from Supabase REST API with error handling."""
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{endpoint}",
        headers=_headers(),
        params=params or {},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _supabase_count(endpoint: str, params: dict = None) -> int:
    """Get exact count from Supabase using Prefer: count=exact."""
    headers = {**_headers(), "Prefer": "count=exact", "Range": "0-0"}
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{endpoint}",
        headers=headers,
        params=params or {},
        timeout=30,
    )
    resp.raise_for_status()
    count_str = resp.headers.get("content-range", "0/0").split("/")[-1]
    return int(count_str) if count_str != "*" else 0


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def get_content_subscriber_count() -> int:
    """Count active content subscribers (new-strip notification list)."""
    return _supabase_count("content_subscribers", {"active": "eq.true"})


def get_recent_signups(days: int = 7) -> list[dict]:
    """Get subscribers who signed up in the last N days."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return _supabase_get("daimoku_subscribers", {
        "subscribed_at": f"gte.{since}",
        "order": "subscribed_at.desc",
        "select": "name,email,challenges,frequency,subscribed_at",
    })


def get_email_delivery_stats(days: int = 7) -> dict:
    """
    Get email delivery stats from daimoku_email_log for the last N days.
    Returns counts of sent vs failed.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    logs = _supabase_get("daimoku_email_log", {
        "sent_at": f"gte.{since}",
        "select": "status,challenge_category",
    })

    sent = 0
    failed = 0
    welcome = 0
    regular = 0
    for log in logs:
        status = log.get("status", "")
        cat = log.get("challenge_category", "")
        if status == "sent":
            sent += 1
        else:
            failed += 1
        if cat.startswith("welcome_"):
            welcome += 1
        else:
            regular += 1

    return {
        "total": len(logs),
        "sent": sent,
        "failed": failed,
        "welcome_emails": welcome,
        "regular_emails": regular,
    }


def get_welcome_sequence_progress() -> dict:
    """
    Analyze welcome sequence progress across all active subscribers.
    Returns counts: step_1, step_2, step_3, completed, not_started.
    """
    subscribers = _supabase_get("daimoku_subscribers", {
        "active": "eq.true",
        "select": "id",
    })

    if not subscribers:
        return {"not_started": 0, "step_1": 0, "step_2": 0, "step_3": 0, "completed": 0}

    # Get all welcome logs in one query
    welcome_logs = _supabase_get("daimoku_email_log", {
        "challenge_category": "like.welcome_%",
        "status": "eq.sent",
        "select": "subscriber_id,challenge_category",
    })

    # Build per-subscriber completion sets
    sub_progress = {}
    for log in welcome_logs:
        sid = log.get("subscriber_id")
        cat = log.get("challenge_category", "")
        if sid not in sub_progress:
            sub_progress[sid] = set()
        if cat in ("welcome_1", "welcome_2", "welcome_3"):
            sub_progress[sid].add(cat)

    counts = {"not_started": 0, "step_1": 0, "step_2": 0, "step_3": 0, "completed": 0}
    for sub in subscribers:
        sid = sub["id"]
        steps = sub_progress.get(sid, set())
        n = len(steps)
        if n == 0:
            counts["not_started"] += 1
        elif n == 1:
            counts["step_1"] += 1  # completed step 1, waiting for step 2
        elif n == 2:
            counts["step_2"] += 1  # completed steps 1-2, waiting for step 3
        elif n >= 3:
            counts["completed"] += 1

    return counts


def dashboard():
    """Print a comprehensive subscriber growth dashboard."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("=" * 60)
        print("  DAIMOKU DAILY — Subscriber Growth Dashboard")
        print("=" * 60)
        print()
        print("  [!] Credentials not configured.")
        print("      Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        print("      environment variables to enable the dashboard.")
        print()
        return

    print("=" * 60)
    print("  DAIMOKU DAILY — Subscriber Growth Dashboard")
    print("=" * 60)

    # ---- Section 1: Total subscribers ----
    stats = get_stats()
    try:
        content_count = get_content_subscriber_count()
    except Exception:
        content_count = None

    print()
    print("  SUBSCRIBERS")
    print("  " + "-" * 40)
    print(f"    Daimoku Daily (active):  {stats['active']}")
    print(f"    Daimoku Daily (inactive): {stats['inactive']}")
    if content_count is not None:
        print(f"    Content subscribers:      {content_count}")
    else:
        print(f"    Content subscribers:      (table not found)")
    print(f"    Total all-time signups:  {stats['total']}")

    # ---- Section 2: Frequency breakdown ----
    print()
    print("  BY FREQUENCY")
    print("  " + "-" * 40)
    freq_map = stats.get("by_frequency", {})
    for freq in ["daily", "thrice_weekly", "weekly"]:
        count = freq_map.get(freq, 0)
        label = {"daily": "Daily", "thrice_weekly": "3x/week (Mon/Wed/Fri)", "weekly": "Weekly (Monday)"}
        print(f"    {label.get(freq, freq):30s} {count}")
    # Any other frequencies
    for freq, count in freq_map.items():
        if freq not in ("daily", "thrice_weekly", "weekly"):
            print(f"    {freq:30s} {count}")

    # ---- Section 3: Challenge breakdown ----
    print()
    print("  BY CHALLENGE")
    print("  " + "-" * 40)
    challenges = stats.get("by_challenge", {})
    if challenges:
        for challenge, count in challenges.items():
            print(f"    {challenge:30s} {count}")
    else:
        print("    (no subscribers yet)")

    # ---- Section 4: Recent signups (last 7 days) ----
    print()
    print("  RECENT SIGNUPS (last 7 days)")
    print("  " + "-" * 40)
    try:
        recent = get_recent_signups(days=7)
        if recent:
            for s in recent:
                dt_str = s.get("subscribed_at", "")[:10]
                challenges_str = ", ".join(s.get("challenges", []))
                print(f"    {dt_str}  {s.get('name', 'N/A'):20s} {s.get('frequency', 'weekly'):15s} [{challenges_str}]")
        else:
            print("    (none)")
    except Exception as e:
        print(f"    (error: {e})")

    # ---- Section 5: Email delivery stats (last 7 days) ----
    print()
    print("  EMAIL DELIVERY (last 7 days)")
    print("  " + "-" * 40)
    try:
        delivery = get_email_delivery_stats(days=7)
        print(f"    Total emails:    {delivery['total']}")
        print(f"    Sent OK:         {delivery['sent']}")
        print(f"    Failed:          {delivery['failed']}")
        print(f"    Welcome emails:  {delivery['welcome_emails']}")
        print(f"    Regular emails:  {delivery['regular_emails']}")
        if delivery["total"] > 0:
            rate = delivery["sent"] / delivery["total"] * 100
            print(f"    Success rate:    {rate:.1f}%")
    except Exception as e:
        print(f"    (error: {e})")

    # ---- Section 6: Welcome sequence progress ----
    print()
    print("  WELCOME SEQUENCE PROGRESS")
    print("  " + "-" * 40)
    try:
        progress = get_welcome_sequence_progress()
        print(f"    Not started:     {progress['not_started']}")
        print(f"    After step 1:    {progress['step_1']}")
        print(f"    After step 2:    {progress['step_2']}")
        print(f"    Completed (3/3): {progress['completed']}")
    except Exception as e:
        print(f"    (error: {e})")

    print()
    print("=" * 60)


def main():
    """Print subscriber stats (basic mode) or full dashboard."""
    parser = argparse.ArgumentParser(description="Daimoku Daily subscriber tools")
    parser.add_argument("--dashboard", action="store_true",
                        help="Show comprehensive subscriber growth dashboard")
    args = parser.parse_args()

    if args.dashboard:
        dashboard()
        return

    # Original basic stats mode
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables")
        return

    stats = get_stats()
    print(f"Daimoku Daily Subscribers")
    print(f"  Total: {stats['total']}")
    print(f"  Active: {stats['active']}")
    print(f"  Inactive: {stats['inactive']}")
    print(f"\n  By frequency:")
    for freq, count in stats["by_frequency"].items():
        print(f"    {freq}: {count}")
    print(f"\n  By challenge:")
    for challenge, count in stats["by_challenge"].items():
        print(f"    {challenge}: {count}")

    if stats["active"] > 0:
        print(f"\n  Active subscribers:")
        for s in list_subscribers():
            challenges = ", ".join(s.get("challenges", []))
            print(f"    {s['name']} ({s['email']}) — {s['frequency']} — [{challenges}]")


if __name__ == "__main__":
    main()
