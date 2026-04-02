"""
Check for new Daimoku Daily subscribers and email notification.
Runs every 6 hours via GitHub Actions.
"""

import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx


SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")


def get_recent_subscribers(hours=6):
    """Get subscribers who signed up in the last N hours."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    response = httpx.get(
        f"{SUPABASE_URL}/rest/v1/daimoku_subscribers",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        },
        params={
            "subscribed_at": f"gte.{since}",
            "order": "subscribed_at.desc",
            "select": "name,email,challenges,frequency,subscribed_at",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_total_count():
    """Get total active subscriber count."""
    response = httpx.get(
        f"{SUPABASE_URL}/rest/v1/daimoku_subscribers",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Prefer": "count=exact",
            "Range": "0-0",
        },
        params={"active": "eq.true"},
        timeout=30,
    )
    response.raise_for_status()
    count = response.headers.get("content-range", "0/0").split("/")[-1]
    return int(count) if count != "*" else 0


def send_notification(new_subs, total):
    """Email notification about new subscribers."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD or not NOTIFY_EMAIL:
        print("Email credentials not set, skipping notification")
        return

    rows = ""
    for s in new_subs:
        challenges = ", ".join(s.get("challenges", []))
        rows += f"""
        <tr>
            <td style="padding:8px; border-bottom:1px solid #eee;">{s.get('name', 'N/A')}</td>
            <td style="padding:8px; border-bottom:1px solid #eee;">{s.get('email', '')}</td>
            <td style="padding:8px; border-bottom:1px solid #eee;">{challenges}</td>
            <td style="padding:8px; border-bottom:1px solid #eee;">{s.get('frequency', 'weekly')}</td>
        </tr>"""

    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #c0392b;">{len(new_subs)} New Daimoku Daily Subscriber{'s' if len(new_subs) != 1 else ''}!</h2>
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

    msg = MIMEMultipart()
    msg["From"] = f"Lotus Lane Bot <{GMAIL_ADDRESS}>"
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = f"Daimoku Daily: {len(new_subs)} new subscriber{'s' if len(new_subs) != 1 else ''} (total: {total})"
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"Notification sent to {NOTIFY_EMAIL}")


def main():
    new_subs = get_recent_subscribers(hours=6)

    if not new_subs:
        print("No new subscribers in the last 6 hours")
        return

    total = get_total_count()
    print(f"{len(new_subs)} new subscriber(s), {total} total")

    for s in new_subs:
        print(f"  - {s.get('name')}: {', '.join(s.get('challenges', []))}")

    send_notification(new_subs, total)


if __name__ == "__main__":
    main()
