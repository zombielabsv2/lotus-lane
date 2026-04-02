"""
Send email notification with the strip image and WhatsApp-ready caption.
Uses Gmail SMTP (same setup as AstroMedha).
Triggered after each strip generation in the GitHub Actions pipeline.
"""

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path

import httpx


GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")
STRIPS_DIR = Path(__file__).parent.parent / "strips"
STRIPS_JSON = Path(__file__).parent.parent / "strips.json"


def get_latest_strip():
    """Get the most recent strip from strips.json."""
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)
    strips.sort(key=lambda s: s["date"], reverse=True)
    return strips[0] if strips else None


def build_whatsapp_caption(strip):
    """Build a WhatsApp-ready caption for copy-paste."""
    title = strip.get("title", "")
    message = strip.get("message", "")
    quote = strip.get("quote", "")
    source = strip.get("source", "")

    caption = f"*{title}*\n\n"
    caption += f"{message}\n\n"
    if quote:
        caption += f'_"{quote}"_\n'
        if source:
            caption += f"— {source}\n"
    caption += "\n"
    caption += "Know someone who needs this? Forward it to them.\n\n"
    caption += "Follow for more: tinyurl.com/thelotuslane"

    return caption


def build_status_caption(strip):
    """Build a shorter caption for WhatsApp Status."""
    title = strip.get("title", "")
    quote = strip.get("quote", "")
    return f"*{title}*\n\n_\"{quote[:100]}{'...' if len(quote) > 100 else ''}\"_\n\ntinyurl.com/thelotuslane"


def send_notification(strip):
    """Send email with strip image and WhatsApp captions via Gmail SMTP."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD or not NOTIFY_EMAIL:
        print("  [NOTIFY] Skipped — GMAIL_ADDRESS, GMAIL_APP_PASSWORD, or NOTIFY_EMAIL not set")
        return

    whatsapp_caption = build_whatsapp_caption(strip)
    status_caption = build_status_caption(strip)

    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #c0392b;">New Lotus Lane Strip Ready!</h2>
        <p style="color: #666;">Strip for <strong>{strip['date']}</strong> — "{strip['title']}"</p>

        <p style="color: #666;">The strip image is attached. Save it to your phone.</p>

        <div style="background: #f5f2ed; padding: 16px; border-radius: 8px; margin: 16px 0;">
            <h3 style="margin: 0 0 8px; color: #333;">WhatsApp Channel Caption (copy-paste):</h3>
            <pre style="background: white; padding: 12px; border-radius: 6px; font-size: 14px;
                        white-space: pre-wrap; border: 1px solid #e0e0e0;">{whatsapp_caption}</pre>
        </div>

        <div style="background: #f5f2ed; padding: 16px; border-radius: 8px; margin: 16px 0;">
            <h3 style="margin: 0 0 8px; color: #333;">WhatsApp Status Caption (shorter):</h3>
            <pre style="background: white; padding: 12px; border-radius: 6px; font-size: 14px;
                        white-space: pre-wrap; border: 1px solid #e0e0e0;">{status_caption}</pre>
        </div>

        <p style="color: #999; font-size: 12px;">Total time: ~3 minutes. That's it!</p>
    </div>
    """

    # Build email
    msg = MIMEMultipart()
    msg["From"] = f"Lotus Lane Bot <{GMAIL_ADDRESS}>"
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = f"Post to WhatsApp: {strip['title']}"
    msg.attach(MIMEText(html, "html"))

    # Attach strip image
    image_path = STRIPS_DIR.parent / strip["image"]
    with open(image_path, "rb") as f:
        img_attachment = MIMEImage(f.read(), name=f"lotus-lane-{strip['date']}.png")
    msg.attach(img_attachment)

    # Send via Gmail SMTP
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"  [NOTIFY] Email sent to {NOTIFY_EMAIL}")


def get_content_subscribers():
    """Get all active content subscribers from Supabase."""
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not supabase_key:
        return []

    response = httpx.get(
        f"{supabase_url}/rest/v1/content_subscribers",
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        params={"active": "eq.true", "select": "email"},
        timeout=30,
    )
    if response.status_code == 200:
        return [s["email"] for s in response.json()]
    return []


def send_content_email(subscriber_email, strip):
    """Send new content notification to a subscriber."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return

    yt_link = f"https://www.youtube.com/@thelotuslane_ND"
    site_link = "https://zombielabsv2.github.io/lotus-lane/"

    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 560px; margin: 0 auto;">
        <div style="text-align:center; padding:1rem 0; border-bottom:2px solid #e8e4de;">
            <div style="font-size:1.3rem; color:#4a4a4a; font-weight:300; letter-spacing:0.1em;">
                The <span style="font-weight:600; color:#c0392b;">Lotus</span> Lane
            </div>
        </div>

        <div style="padding:1.5rem 0;">
            <h2 style="color:#333; font-size:1.1rem; margin-bottom:0.5rem;">New Strip: {strip.get('title', '')}</h2>
            <p style="color:#666; font-size:0.9rem; line-height:1.5; margin-bottom:1rem;">{strip.get('message', '')}</p>

            <div style="background:#fdf8f0; border-left:3px solid #c0392b; padding:0.8rem 1rem; margin-bottom:1rem;">
                <em style="color:#555; font-size:0.88rem;">"{strip.get('quote', '')}"</em>
                <div style="color:#999; font-size:0.75rem; margin-top:0.3rem;">— {strip.get('source', '')}</div>
            </div>

            <div style="text-align:center; margin:1.5rem 0;">
                <a href="{site_link}" style="
                    display:inline-block; padding:0.6rem 1.5rem; background:#c0392b; color:white;
                    text-decoration:none; border-radius:8px; font-size:0.9rem; font-weight:500;
                ">Read the full strip</a>
            </div>

            <p style="color:#999; font-size:0.8rem; text-align:center;">
                Also on <a href="{yt_link}" style="color:#c0392b;">YouTube Shorts</a>
            </p>
        </div>

        <div style="border-top:1px solid #eee; padding:1rem 0; text-align:center;">
            <p style="color:#bbb; font-size:0.7rem;">
                You're receiving this because you subscribed at The Lotus Lane.<br>
                <a href="{site_link}" style="color:#999;">Visit site</a>
            </p>
        </div>
    </div>
    """

    msg = MIMEMultipart()
    msg["From"] = f"The Lotus Lane <{GMAIL_ADDRESS}>"
    msg["To"] = subscriber_email
    msg["Subject"] = f"New Strip: {strip.get('title', '')} — The Lotus Lane"
    msg.attach(MIMEText(html, "html"))

    # Attach strip image
    image_path = STRIPS_DIR.parent / strip["image"]
    with open(image_path, "rb") as f:
        img_attachment = MIMEImage(f.read(), name=f"lotus-lane-{strip['date']}.png")
    msg.attach(img_attachment)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def notify_content_subscribers(strip):
    """Send new strip notification to all content subscribers."""
    subscribers = get_content_subscribers()
    if not subscribers:
        print(f"  [CONTENT] No content subscribers to notify")
        return

    print(f"  [CONTENT] Notifying {len(subscribers)} content subscribers...")
    sent = 0
    for email in subscribers:
        try:
            send_content_email(email, strip)
            sent += 1
        except Exception as e:
            print(f"  [CONTENT] Failed to send to {email}: {e}")

    print(f"  [CONTENT] Sent {sent}/{len(subscribers)} emails")


def main():
    strip = get_latest_strip()
    if not strip:
        print("No strips found")
        return

    print(f"Latest strip: {strip['date']} — {strip['title']}")
    print(f"\n--- WhatsApp Channel Caption ---")
    print(build_whatsapp_caption(strip))
    print(f"\n--- WhatsApp Status Caption ---")
    print(build_status_caption(strip))

    # Notify Rahul (WhatsApp posting reminder)
    send_notification(strip)

    # Notify content subscribers
    notify_content_subscribers(strip)


if __name__ == "__main__":
    main()
