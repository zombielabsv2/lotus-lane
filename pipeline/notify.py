"""
Send email notification with the strip image and WhatsApp-ready caption.
Uses Gmail SMTP (same setup as AstroMedha).
Triggered after each strip generation in the GitHub Actions pipeline.
"""

import base64
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path


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

    send_notification(strip)


if __name__ == "__main__":
    main()
