"""Max-plan generation broker client.

Instead of POSTing to api.anthropic.com (metered, prepaid balance), a cron job
enqueues its prompt into Supabase `max_gen_queue`. The inbox-agent VM polls that
table every 2 minutes and, when work is present, drains it with `claude -p` on
the Claude Max OAuth token — zero API spend.

Contract for callers
--------------------
    text = maxgen_client.generate(system=..., user=..., max_tokens=..., app=..., action=...)
    if text is None:
        text = <existing metered API call>      # fallback, unchanged

`generate()` returns None (never raises) whenever the broker cannot serve the
request — disabled, misconfigured, drain timeout, or a failed generation. The
caller's existing API path stays as the safety net, so a broker outage can never
stop an email from going out.

Enable per-job with MAXGEN_ENABLED=1. Everything else has a working default.

Env:
    MAXGEN_ENABLED     "1" to route through the broker (default off)
    MAXGEN_TIMEOUT_S   seconds to wait for the VM (default 600)
    SUPABASE_URL       required
    SUPABASE_SERVICE_KEY / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_KEY   required
"""

from __future__ import annotations

import os
import sys
import time

import httpx

POLL_INTERVAL_S = 5.0
DEFAULT_TIMEOUT_S = 600.0

# What the VM actually serves the request with. Recorded in api_usage_log at
# cost 0 so the daily cost report shows work SHIFTED rather than work vanished.
MAX_MODEL_LABEL = "max-oauth:claude-opus-4-8"


def _env(*names: str) -> str:
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return ""


def _supabase() -> tuple[str, str]:
    url = _env("SUPABASE_URL").rstrip("/")
    key = _env("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY")
    return url, key


def enabled() -> bool:
    if os.environ.get("MAXGEN_ENABLED", "").strip() != "1":
        return False
    url, key = _supabase()
    if not url or not key:
        print(
            "[maxgen] MAXGEN_ENABLED=1 but SUPABASE_URL/SERVICE_KEY missing — using API path",
            file=sys.stderr,
        )
        return False
    return True


def _headers(key: str, extra: dict | None = None) -> dict:
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _log_shifted(app: str, action: str, metadata: dict | None) -> None:
    """Record the served request at $0 so cost reporting stays complete."""
    url, key = _supabase()
    if not url or not key:
        return
    try:
        httpx.post(
            f"{url}/rest/v1/api_usage_log",
            headers=_headers(key, {"Prefer": "return=minimal"}),
            json={
                "app": app,
                "action": action,
                "model": MAX_MODEL_LABEL,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0,
                "metadata": {**(metadata or {}), "source": "maxgen"},
            },
            timeout=5.0,
        )
    except Exception as e:  # noqa: BLE001 — accounting must never break a send
        print(f"[maxgen] usage log failed (non-fatal): {e}", file=sys.stderr)


def _fail_row(url: str, key: str, row_id: str, why: str) -> None:
    try:
        httpx.patch(
            f"{url}/rest/v1/max_gen_queue",
            headers=_headers(key, {"Prefer": "return=minimal"}),
            params={"id": f"eq.{row_id}"},
            json={"status": "failed", "error": why[:500]},
            timeout=10.0,
        )
    except Exception:  # noqa: BLE001
        pass


def generate(
    *,
    system: str,
    user: str,
    max_tokens: int,
    app: str,
    action: str,
    response_format: str = "text",
    metadata: dict | None = None,
    timeout_s: float | None = None,
) -> str | None:
    """Ask the VM to generate on Max. Returns text, or None to fall back to API."""
    if not enabled():
        return None

    url, key = _supabase()
    budget = timeout_s if timeout_s is not None else float(
        os.environ.get("MAXGEN_TIMEOUT_S", DEFAULT_TIMEOUT_S)
    )

    try:
        r = httpx.post(
            f"{url}/rest/v1/max_gen_queue",
            headers=_headers(key, {"Prefer": "return=representation"}),
            json={
                "app": app,
                "action": action,
                "system_prompt": system,
                "user_prompt": user,
                "max_tokens": max_tokens,
                "response_format": response_format,
            },
            timeout=20.0,
        )
        r.raise_for_status()
        row_id = r.json()[0]["id"]
    except Exception as e:  # noqa: BLE001
        print(f"[maxgen] enqueue failed ({e}) — using API path", file=sys.stderr)
        return None

    print(f"[maxgen] queued {app}/{action} id={row_id}; waiting up to {int(budget)}s", file=sys.stderr)
    deadline = time.monotonic() + budget

    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_S)
        try:
            g = httpx.get(
                f"{url}/rest/v1/max_gen_queue",
                headers=_headers(key),
                params={"id": f"eq.{row_id}", "select": "status,result,error"},
                timeout=15.0,
            )
            g.raise_for_status()
            rows = g.json()
            if not rows:
                continue
            row = rows[0]
        except Exception as e:  # noqa: BLE001
            print(f"[maxgen] poll error (retrying): {e}", file=sys.stderr)
            continue

        if row["status"] == "done" and row.get("result"):
            waited = int(budget - (deadline - time.monotonic()))
            print(f"[maxgen] served on Max in ~{waited}s — no API spend", file=sys.stderr)
            _log_shifted(app, action, metadata)
            return row["result"]

        if row["status"] == "failed":
            print(f"[maxgen] VM reported failure: {row.get('error')} — using API path", file=sys.stderr)
            return None

    _fail_row(url, key, row_id, "caller timeout — fell back to metered API")
    print(f"[maxgen] timed out after {int(budget)}s — using API path", file=sys.stderr)
    return None
