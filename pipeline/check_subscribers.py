"""
Daimoku Daily — new-subscriber notification.

Two modes:
  --single EMAIL : fetch one subscriber's row + total count, email Rahul.
                   Fired by welcome-new-subscriber.yml (which is in turn
                   fired by a Supabase Database Webhook on insert into
                   daimoku_subscribers via repository_dispatch).
  (no args)      : legacy poll mode — kept for ad-hoc workflow_dispatch
                   catch-up only. The 6-hourly cron was removed
                   2026-04-27 in favor of the event-driven webhook path.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx


SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }


def get_recent_subscribers(hours=6):
    """Get subscribers who signed up in the last N hours (poll mode)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    response = httpx.get(
        f"{SUPABASE_URL}/rest/v1/daimoku_subscribers",
        headers=_headers(),
        params={
            "subscribed_at": f"gte.{since}",
            "order": "subscribed_at.desc",
            "select": "name,email,challenges,frequency,subscribed_at",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_subscriber_by_email(email: str) -> dict | None:
    """Fetch one subscriber row by email. Returns None if not found."""
    response = httpx.get(
        f"{SUPABASE_URL}/rest/v1/daimoku_subscribers",
        headers=_headers(),
        params={
            "email": f"eq.{email}",
            "select": "name,email,challenges,frequency,subscribed_at,confirmed",
            "limit": 1,
        },
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def get_total_count():
    """Get total active subscriber count."""
    response = httpx.get(
        f"{SUPABASE_URL}/rest/v1/daimoku_subscribers",
        headers={**_headers(), "Prefer": "count=exact", "Range": "0-0"},
        params={"active": "eq.true"},
        timeout=30,
    )
    response.raise_for_status()
    count = response.headers.get("content-range", "0/0").split("/")[-1]
    return int(count) if count != "*" else 0


def _build_table_rows(subs):
    rows = ""
    for s in subs:
        challenges = ", ".join(s.get("challenges", []) or [])
        rows += f"""
        <tr>
            <td style="padding:8px; border-bottom:1px solid #eee;">{s.get('name', 'N/A')}</td>
            <td style="padding:8px; border-bottom:1px solid #eee;">{s.get('email', '')}</td>
            <td style="padding:8px; border-bottom:1px solid #eee;">{challenges}</td>
            <td style="padding:8px; border-bottom:1px solid #eee;">{s.get('frequency', 'weekly')}</td>
        </tr>"""
    return rows


def send_notification(new_subs, total):
    """Email notification about new subscribers via Resend API."""
    if not RESEND_API_KEY or not NOTIFY_EMAIL:
        print("RESEND_API_KEY or NOTIFY_EMAIL not set, skipping notification")
        return

    rows = _build_table_rows(new_subs)
    n = len(new_subs)
    plural = "s" if n != 1 else ""

    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #c0392b;">{n} New Daimoku Daily Subscriber{plural}!</h2>
        <p style="color: #666;">Total active subscribers: <strong>{total}</strong></p>

        <table style="width:100%; border-collapse:collapse; margin-top:16px;">
            <tr style="background:#f5f2ed;">
                <th style="padding:8px; text-align:left;">Name</th>
                <th style="padding:8px; text-align:left;">Email</th>
                <th style="padding:8px; text-align:left;">Challenges</th>
                <th style="padding:8px; text-align:left;">Frequency</th>
            </tr>
            {rows}
        </table>
    </div>
    """

    subject = f"Daimoku Daily: {n} new subscriber{plural} (total: {total})"

    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={
            "from": "Lotus Lane Bot <notifications@rxjapps.in>",
            "to": [NOTIFY_EMAIL],
            "subject": subject,
            "html": html,
        },
        timeout=30,
    )

    if resp.status_code == 200:
        print(f"Notification sent to {NOTIFY_EMAIL}")
    else:
        print(f"Failed to send notification: {resp.status_code} {resp.text}")


def notify_single(email: str) -> int:
    """Notify Rahul about ONE new subscriber identified by email.

    Returns 0 on success (subscriber found + notification dispatched or
    credentials missing), 1 on lookup failure (subscriber not in table).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("SUPABASE_URL/SUPABASE_SERVICE_KEY missing — skipping notify")
        return 0

    sub = get_subscriber_by_email(email)
    if not sub:
        # Webhook fired for a row that vanished (delete race) or we were
        # called with a stale email. Don't fail the workflow over it —
        # the welcome step is the load-bearing one.
        print(f"[notify] subscriber not found for {email}; skipping")
        return 0

    total = get_total_count()
    print(f"[notify] new signup: {sub.get('name', '?')} <{email}>, total active={total}")
    send_notification([sub], total)
    return 0


def poll_mode():
    new_subs = get_recent_subscribers(hours=6)

    if not new_subs:
        print("No new subscribers in the last 6 hours")
        return

    total = get_total_count()
    print(f"{len(new_subs)} new subscriber(s), {total} total")

    for s in new_subs:
        print(f"  - {s.get('name')}: {', '.join(s.get('challenges', []) or [])}")

    send_notification(new_subs, total)


def main():
    parser = argparse.ArgumentParser(description="Daimoku Daily new-subscriber notification")
    parser.add_argument("--single", metavar="EMAIL",
                        help="Notify Rahul about ONE subscriber (event-driven mode)")
    args = parser.parse_args()

    if args.single:
        sys.exit(notify_single(args.single))
    else:
        poll_mode()


if __name__ == "__main__":
    main()
