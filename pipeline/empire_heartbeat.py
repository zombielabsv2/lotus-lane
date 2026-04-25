"""Empire-wide cron heartbeat helper.

Crons call `beat(cron_name, payload=...)` at the very end on success.
The watcher in empire-dashboard scans empire_cron_heartbeats hourly and
emails Rahul on overdue rows.

Catches a class GitHub Actions failure-email does NOT cover:
  - cron didn't run at all (Actions outage, scheduler misconfig)
  - cron ran but did silent no-op (sent=0 with no error)

Never raises. Heartbeat failure is non-fatal; the cron's primary
work has already succeeded by the time beat() is called.

Required env: SUPABASE_URL, SUPABASE_SERVICE_KEY.

Vendored — keep this file identical across repos. Source of truth lives
in moonpath/pipeline/empire_heartbeat.py; copy/paste, do not symlink
(symlinks don't survive GitHub Actions checkout consistently).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

_TIMEOUT = 10.0


def beat(cron_name: str, payload: dict[str, Any] | None = None) -> bool:
    """Record a successful run for cron_name. Returns True on success.

    The row must be pre-registered in empire_cron_heartbeats (with
    repo + cadence). beat() only updates last_success_at + last_payload;
    it never inserts a new tracked cron, so an unregistered cron name
    silently no-ops with a clear warning. This is intentional: the
    "what cadence is expected" decision must be deliberate, not
    discovered by accident.
    """
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    if not url or not key:
        print(f"[heartbeat] skipped {cron_name}: missing SUPABASE_URL or SUPABASE_SERVICE_KEY", file=sys.stderr)
        return False

    now_iso = datetime.now(timezone.utc).isoformat()
    body = {
        "last_success_at": now_iso,
        "last_payload": payload or {},
    }

    try:
        resp = httpx.patch(
            f"{url}/rest/v1/empire_cron_heartbeats",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                # count=exact tells PostgREST to return Content-Range: <m>-<n>/<total>
                # so we can detect "0 rows matched" (unregistered cron).
                "Prefer": "return=minimal,count=exact",
            },
            params={"cron_name": f"eq.{cron_name}"},
            content=json.dumps(body),
            timeout=_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[heartbeat] {cron_name} request failed: {e}", file=sys.stderr)
        return False

    if resp.status_code >= 300:
        print(
            f"[heartbeat] {cron_name} non-2xx {resp.status_code}: {resp.text[:200]}",
            file=sys.stderr,
        )
        return False

    # Content-Range looks like "0-0/1" on update of one row, or "*/0" if
    # zero rows matched.
    cr = resp.headers.get("Content-Range", "")
    total = cr.split("/")[-1] if "/" in cr else "?"
    if total in ("0", "?"):
        print(
            f"[heartbeat] {cron_name} not registered in empire_cron_heartbeats; "
            f"add a row first (cron_name, repo, expected_cadence_hours).",
            file=sys.stderr,
        )
        return False

    print(f"[heartbeat] {cron_name} ok at {now_iso}", file=sys.stderr)
    return True
