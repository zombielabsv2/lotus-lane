"""
Daimoku Daily — Subscriber management utilities.

The subscribe form uses direct Supabase REST API calls from frontend JavaScript
(with the publishable/anon key). This module provides utilities for:
- Manual subscriber management
- Unsubscribe processing
- Subscriber stats
"""

import os
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


def main():
    """Print subscriber stats."""
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
