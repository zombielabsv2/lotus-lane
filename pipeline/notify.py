"""
Send email notification with the strip image and WhatsApp-ready caption.
Triggered after each strip generation in the GitHub Actions pipeline.
"""

import base64
import json
import os
from pathlib import Path

import httpx


RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
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
    tags = strip.get("tags", [])

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
    """Send email with strip image and WhatsApp captions."""
    if not RESEND_API_KEY or not NOTIFY_EMAIL:
        print("  [NOTIFY] Skipped — RESEND_API_KEY or NOTIFY_EMAIL not set")
        return

    # Read strip image
    image_path = STRIPS_DIR.parent / strip["image"]
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    whatsapp_caption = build_whatsapp_caption(strip)
    status_caption = build_status_caption(strip)

    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #c0392b;">New Lotus Lane Strip Ready!</h2>
        <p style="color: #666;">Strip for <strong>{strip['date']}</strong> — "{strip['title']}"</p>

        <div style="background: #f5f2ed; padding: 16px; border-radius: 8px; margin: 16px 0;">
            <h3 style="margin: 0 0 8px; color: #333;">Step 1: Save the image</h3>
            <p style="color: #666; margin: 0;">The strip is attached to this email. Save it to your phone.</p>
        </div>

        <div style="background: #f5f2ed; padding: 16px; border-radius: 8px; margin: 16px 0;">
            <h3 style="margin: 0 0 8px; color: #333;">Step 2: Post to WhatsApp Channel</h3>
            <p style="color: #666; margin: 0 0 8px;">Copy this caption:</p>
            <pre style="background: white; padding: 12px; border-radius: 6px; font-size: 14px;
                        white-space: pre-wrap; border: 1px solid #e0e0e0;">{whatsapp_caption}</pre>
        </div>

        <div style="background: #f5f2ed; padding: 16px; border-radius: 8px; margin: 16px 0;">
            <h3 style="margin: 0 0 8px; color: #333;">Step 3: Post to WhatsApp Status</h3>
            <p style="color: #666; margin: 0 0 8px;">Copy this shorter caption:</p>
            <pre style="background: white; padding: 12px; border-radius: 6px; font-size: 14px;
                        white-space: pre-wrap; border: 1px solid #e0e0e0;">{status_caption}</pre>
        </div>

        <p style="color: #999; font-size: 12px;">Total time: ~3 minutes. That's it!</p>
    </div>
    """

    response = httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": "Lotus Lane Bot <onboarding@resend.dev>",
            "to": [NOTIFY_EMAIL],
            "subject": f"New Strip: {strip['title']} — post to WhatsApp",
            "html": html,
            "attachments": [
                {
                    "filename": f"lotus-lane-{strip['date']}.png",
                    "content": image_b64,
                }
            ],
        },
        timeout=30,
    )
    response.raise_for_status()
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
