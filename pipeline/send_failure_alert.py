"""Send pipeline failure alert email via Resend API.

Called from generate-strip.yml when optional steps fail.
Expects env vars: RESEND_API_KEY, NOTIFY_EMAIL, FAIL_TEXT, RUN_URL
"""
import httpx
import os


def main():
    api_key = os.environ.get("RESEND_API_KEY", "")
    notify_email = os.environ.get("NOTIFY_EMAIL", "")
    failures = os.environ.get("FAIL_TEXT", "")
    run_url = os.environ.get("RUN_URL", "")

    if not api_key or not notify_email or not failures:
        print("Missing required env vars, skipping alert")
        return

    body = (
        f"<h3>Lotus Lane Pipeline Failures</h3>"
        f"<pre>{failures}</pre>"
        f'<p><a href="{run_url}">View run</a></p>'
    )

    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": "Lotus Lane Bot <notifications@rxjapps.in>",
            "to": [notify_email],
            "subject": "Lotus Lane: Pipeline failures detected",
            "html": body,
        },
    )
    print(f"Alert sent: {resp.status_code}")


if __name__ == "__main__":
    main()
