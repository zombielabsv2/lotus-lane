"""
Weekly traffic digest for The Lotus Lane.

Pulls signals from the sources we already have auth for, formats them into a
readable HTML email, and ships it via Resend. GA4 + GoatCounter are flagged in
the footer as pending API-token setup.

Run:
    python pipeline/weekly_traffic_digest.py              # send to NOTIFY_EMAIL
    python pipeline/weekly_traffic_digest.py --dry-run    # print, don't send
    python pipeline/weekly_traffic_digest.py --to me@x    # override recipient

Env:
    SUPABASE_URL, SUPABASE_SERVICE_KEY   — subscriber stats
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN — channel + video views
    GA4_SA_KEY (JSON), GA4_PROPERTY_ID   — sessions, top pages, referrers, devices
    RESEND_API_KEY, NOTIFY_EMAIL         — send
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
STRIPS_JSON = ROOT / "strips.json"
SITE_URL = "https://thelotuslane.in"
GA4_MEASUREMENT_ID = "G-4DM9P70KJ6"
GOATCOUNTER_DASHBOARD = "https://zombielabs.goatcounter.com"

RESEND_API_URL = "https://api.resend.com/emails"
FROM_EMAIL = "Lotus Lane Bot <notifications@rxjapps.in>"
YT_TOKEN_URL = "https://oauth2.googleapis.com/token"
YT_API = "https://www.googleapis.com/youtube/v3"
GA4_API = "https://analyticsdata.googleapis.com/v1beta"


# ---------------------------------------------------------------------------
# Supabase — subscriber signal
# ---------------------------------------------------------------------------

def _supabase_headers() -> dict:
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _supabase_count(table: str, params: dict | None = None) -> int:
    url = os.environ.get("SUPABASE_URL", "")
    if not url:
        return -1
    headers = {**_supabase_headers(), "Prefer": "count=exact", "Range": "0-0"}
    resp = httpx.get(f"{url}/rest/v1/{table}", headers=headers, params=params or {}, timeout=30)
    resp.raise_for_status()
    count_str = resp.headers.get("content-range", "0/0").split("/")[-1]
    return int(count_str) if count_str != "*" else 0


def collect_subscribers() -> dict:
    """Return subscriber totals + 7d deltas for both lists."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    out = {
        "daimoku_total": 0,
        "daimoku_new_7d": 0,
        "content_total": 0,
        "content_new_7d": 0,
        "email_sent_7d": 0,
        "email_failed_7d": 0,
        "source_error": None,
    }

    try:
        out["daimoku_total"] = _supabase_count(
            "daimoku_subscribers", {"active": "eq.true", "confirmed": "eq.true"}
        )
        out["daimoku_new_7d"] = _supabase_count(
            "daimoku_subscribers",
            {"subscribed_at": f"gte.{since}", "confirmed": "eq.true"},
        )
        out["content_total"] = _supabase_count(
            "content_subscribers", {"active": "eq.true"}
        )
        out["content_new_7d"] = _supabase_count(
            "content_subscribers", {"subscribed_at": f"gte.{since}"}
        )
        out["email_sent_7d"] = _supabase_count(
            "daimoku_email_log", {"sent_at": f"gte.{since}", "status": "eq.sent"}
        )
        out["email_failed_7d"] = _supabase_count(
            "daimoku_email_log", {"sent_at": f"gte.{since}", "status": "neq.sent"}
        )
    except Exception as e:
        out["source_error"] = f"{type(e).__name__}: {e}"

    return out


# ---------------------------------------------------------------------------
# YouTube — channel stats + per-video views
# ---------------------------------------------------------------------------

def _youtube_access_token() -> str | None:
    rt = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "")
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    if not all([rt, cid, csec]):
        return None
    resp = httpx.post(
        YT_TOKEN_URL,
        data={
            "client_id": cid,
            "client_secret": csec,
            "refresh_token": rt,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if resp.status_code >= 400:
        print(f"[youtube] oauth failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        return None
    return resp.json().get("access_token")


def collect_youtube(recent_video_ids: list[str]) -> dict:
    out = {
        "channel": None,
        "videos": {},  # video_id -> {views, likes, comments, published_at, title}
        "source_error": None,
    }
    token = _youtube_access_token()
    if not token:
        out["source_error"] = "missing YouTube OAuth creds (or refresh failed)"
        return out

    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = httpx.get(
            f"{YT_API}/channels",
            headers=headers,
            params={"part": "snippet,statistics", "mine": "true"},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("items") or []
        if items:
            ch = items[0]
            stats = ch.get("statistics") or {}
            out["channel"] = {
                "title": (ch.get("snippet") or {}).get("title", ""),
                "subscribers": int(stats.get("subscriberCount") or 0),
                "total_views": int(stats.get("viewCount") or 0),
                "video_count": int(stats.get("videoCount") or 0),
            }
    except Exception as e:
        out["source_error"] = f"channel stats: {type(e).__name__}: {e}"

    if recent_video_ids:
        try:
            r = httpx.get(
                f"{YT_API}/videos",
                headers=headers,
                params={"part": "snippet,statistics", "id": ",".join(recent_video_ids)},
                timeout=30,
            )
            r.raise_for_status()
            for v in r.json().get("items") or []:
                vid = v.get("id", "")
                stats = v.get("statistics") or {}
                snip = v.get("snippet") or {}
                out["videos"][vid] = {
                    "title": snip.get("title", ""),
                    "published_at": snip.get("publishedAt", ""),
                    "views": int(stats.get("viewCount") or 0),
                    "likes": int(stats.get("likeCount") or 0),
                    "comments": int(stats.get("commentCount") or 0),
                }
        except Exception as e:
            err = f"video stats: {type(e).__name__}: {e}"
            out["source_error"] = f"{out['source_error']}; {err}" if out["source_error"] else err

    return out


# ---------------------------------------------------------------------------
# GA4 — sessions, top pages, top referrers, device mix
# ---------------------------------------------------------------------------

def _ga4_access_token() -> str | None:
    raw = os.environ.get("GA4_SA_KEY", "").strip()
    if not raw:
        return None
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
        )
        creds.refresh(Request())
        return creds.token
    except Exception as e:
        print(f"[ga4] auth failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def _ga4_run_report(token: str, property_id: str, body: dict) -> dict | None:
    resp = httpx.post(
        f"{GA4_API}/properties/{property_id}:runReport",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    if resp.status_code >= 400:
        print(f"[ga4] runReport failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        return None
    return resp.json()


def _ga4_rows(report: dict | None, dim_count: int = 1) -> list[tuple]:
    if not report:
        return []
    out = []
    for row in report.get("rows", []) or []:
        dims = [d.get("value", "") for d in row.get("dimensionValues", [])][:dim_count]
        metrics = [m.get("value", "") for m in row.get("metricValues", [])]
        out.append((*dims, *metrics))
    return out


def collect_ga4() -> dict:
    out = {
        "available": False,
        "totals": {},
        "top_pages": [],
        "top_referrers": [],
        "device_mix": [],
        "country_mix": [],
        "source_error": None,
    }
    prop_id = os.environ.get("GA4_PROPERTY_ID", "").strip()
    if not prop_id:
        out["source_error"] = "GA4_PROPERTY_ID env var not set"
        return out

    token = _ga4_access_token()
    if not token:
        out["source_error"] = "GA4 service account auth failed (check GA4_SA_KEY + property grant)"
        return out

    date_range = [{"startDate": "7daysAgo", "endDate": "yesterday"}]

    # 1. Totals
    totals = _ga4_run_report(token, prop_id, {
        "dateRanges": date_range,
        "metrics": [
            {"name": "sessions"},
            {"name": "activeUsers"},
            {"name": "screenPageViews"},
            {"name": "engagementRate"},
            {"name": "averageSessionDuration"},
        ],
    })
    rows = _ga4_rows(totals, dim_count=0)
    if rows:
        s, u, pv, er, asd = rows[0]
        out["totals"] = {
            "sessions": int(s or 0),
            "users": int(u or 0),
            "pageviews": int(pv or 0),
            "engagement_rate": float(er or 0.0),
            "avg_session_sec": float(asd or 0.0),
        }
        out["available"] = True
    else:
        out["source_error"] = "GA4 returned no data (property has no events in last 7d, or auth mis-scoped)"
        return out

    # 2. Top pages
    pages = _ga4_run_report(token, prop_id, {
        "dateRanges": date_range,
        "dimensions": [{"name": "pagePath"}],
        "metrics": [{"name": "screenPageViews"}],
        "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
        "limit": 10,
    })
    out["top_pages"] = [(p, int(v or 0)) for p, v in _ga4_rows(pages)]

    # 3. Top referrers (session source, excluding direct)
    refs = _ga4_run_report(token, prop_id, {
        "dateRanges": date_range,
        "dimensions": [{"name": "sessionSource"}],
        "metrics": [{"name": "sessions"}],
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 8,
    })
    out["top_referrers"] = [(s, int(v or 0)) for s, v in _ga4_rows(refs)]

    # 4. Device mix
    dev = _ga4_run_report(token, prop_id, {
        "dateRanges": date_range,
        "dimensions": [{"name": "deviceCategory"}],
        "metrics": [{"name": "sessions"}],
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
    })
    out["device_mix"] = [(d, int(v or 0)) for d, v in _ga4_rows(dev)]

    # 5. Top countries
    ctry = _ga4_run_report(token, prop_id, {
        "dateRanges": date_range,
        "dimensions": [{"name": "country"}],
        "metrics": [{"name": "sessions"}],
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 5,
    })
    out["country_mix"] = [(c, int(v or 0)) for c, v in _ga4_rows(ctry)]

    return out


# ---------------------------------------------------------------------------
# strips.json — publishing signal + top views
# ---------------------------------------------------------------------------

def collect_strips_signal() -> dict:
    with open(STRIPS_JSON, "r", encoding="utf-8") as f:
        strips = json.load(f)

    today = datetime.now(timezone.utc).date()
    week_ago = today - timedelta(days=7)

    def _parse_date(s: str):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    recent = []
    missing_video = 0
    total_cached_views = 0
    for s in strips:
        d = _parse_date(s.get("date", ""))
        if not d:
            continue
        if d >= week_ago:
            recent.append(s)
            if not s.get("youtube_id"):
                missing_video += 1
        total_cached_views += int(s.get("youtube_views") or 0)

    recent.sort(key=lambda s: s["date"], reverse=True)

    # top 5 all-time by cached youtube_views
    by_views = sorted(
        (s for s in strips if s.get("youtube_id") and (s.get("youtube_views") or 0) > 0),
        key=lambda s: int(s.get("youtube_views") or 0),
        reverse=True,
    )[:5]

    return {
        "total_strips": len(strips),
        "recent": recent,
        "recent_video_ids": [s["youtube_id"] for s in recent if s.get("youtube_id")],
        "missing_video_in_week": missing_video,
        "total_cached_youtube_views": total_cached_views,
        "top_5_cached": [
            {
                "date": s["date"],
                "title": s.get("title", ""),
                "youtube_id": s["youtube_id"],
                "views": int(s.get("youtube_views") or 0),
            }
            for s in by_views
        ],
    }


# ---------------------------------------------------------------------------
# HTML formatting
# ---------------------------------------------------------------------------

def _fmt_int(n: int) -> str:
    if n < 0:
        return "—"
    return f"{n:,}"


def _delta(n: int) -> str:
    if n <= 0:
        return "—"
    return f"+{n:,}"


def _fmt_duration(seconds: float) -> str:
    s = int(round(seconds or 0))
    m, s = divmod(s, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _fmt_pct(frac: float) -> str:
    return f"{(frac or 0.0) * 100:.1f}%"


def _ga4_section(ga4: dict) -> str:
    if not ga4.get("available"):
        return f"""
  <div style="margin-bottom:28px;padding:14px 16px;background:#fff8e1;border-left:3px solid #f5a623;">
    <div style="font-size:14px;color:#555;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Site Traffic (GA4)</div>
    <p style="margin:6px 0 0;color:#8a5a00;">Unavailable: {ga4.get('source_error') or 'unknown error'}</p>
  </div>
  """

    t = ga4["totals"]
    totals_html = f"""
    <table style="width:100%;border-collapse:collapse;margin-top:8px;">
      <tr><td style="padding:6px 0;color:#555;">Sessions</td><td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_int(t['sessions'])}</td></tr>
      <tr><td style="padding:6px 0;color:#555;">Users</td><td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_int(t['users'])}</td></tr>
      <tr><td style="padding:6px 0;color:#555;">Pageviews</td><td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_int(t['pageviews'])}</td></tr>
      <tr><td style="padding:6px 0;color:#555;">Engagement rate</td><td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_pct(t['engagement_rate'])}</td></tr>
      <tr><td style="padding:6px 0;color:#555;">Avg session duration</td><td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_duration(t['avg_session_sec'])}</td></tr>
    </table>
    """

    def _table(title: str, rows: list[tuple], col_label: str) -> str:
        if not rows:
            return ""
        body = ""
        for label, value in rows:
            label_html = (label or "(direct / none)").replace("<", "&lt;")[:80]
            body += f"""
            <tr>
              <td style="padding:6px 12px 6px 0;color:#111;font-size:13px;">{label_html}</td>
              <td style="padding:6px 0;text-align:right;font-weight:600;font-size:13px;">{_fmt_int(value)}</td>
            </tr>
            """
        return f"""
        <div style="margin-top:16px;">
          <div style="font-size:12px;color:#999;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">{title}</div>
          <table style="width:100%;border-collapse:collapse;border-top:1px solid #eee;">
            <thead><tr style="color:#999;font-size:11px;"><th style="padding:4px 0;text-align:left;font-weight:500;">&nbsp;</th><th style="padding:4px 0;text-align:right;font-weight:500;">{col_label}</th></tr></thead>
            <tbody>{body}</tbody>
          </table>
        </div>
        """

    top_pages = _table("Top pages", ga4["top_pages"], "views")
    top_refs = _table("Traffic sources", ga4["top_referrers"], "sessions")
    devices = _table("Device", ga4["device_mix"], "sessions")
    countries = _table("Top countries", ga4["country_mix"], "sessions")

    return f"""
  <div style="margin-bottom:28px;">
    <div style="font-size:14px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Site Traffic (GA4, last 7 days)</div>
    {totals_html}
    {top_pages}
    {top_refs}
    <div style="display:flex;gap:16px;">
      <div style="flex:1;">{devices}</div>
      <div style="flex:1;">{countries}</div>
    </div>
  </div>
  """


def build_html(subs: dict, yt: dict, strips: dict, ga4: dict) -> str:
    today = datetime.now(timezone.utc).strftime("%b %d, %Y")
    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%b %d")
    week_end = datetime.now(timezone.utc).strftime("%b %d")

    ch = yt.get("channel") or {}
    ch_rows = ""
    if ch:
        ch_rows = f"""
        <table style="width:100%;border-collapse:collapse;margin-top:8px;">
          <tr><td style="padding:6px 0;color:#555;">Subscribers</td><td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_int(ch.get('subscribers', 0))}</td></tr>
          <tr><td style="padding:6px 0;color:#555;">Total views (all-time)</td><td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_int(ch.get('total_views', 0))}</td></tr>
          <tr><td style="padding:6px 0;color:#555;">Videos published</td><td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_int(ch.get('video_count', 0))}</td></tr>
        </table>
        """
    else:
        ch_rows = f"<p style='color:#c33;margin:6px 0 0;'>YouTube channel stats unavailable: {yt.get('source_error') or 'unknown'}</p>"

    # Recent strips table (this week)
    recent_rows_html = ""
    for s in strips["recent"]:
        vid_id = s.get("youtube_id", "")
        views = "—"
        if vid_id and vid_id in yt.get("videos", {}):
            views = _fmt_int(yt["videos"][vid_id]["views"])
        elif vid_id:
            views = "pending"
        else:
            views = "<span style='color:#c33;'>no video</span>"
        link = f"{SITE_URL}/strips/{s['date']}.html"
        recent_rows_html += f"""
        <tr>
          <td style="padding:8px 12px 8px 0;color:#555;font-size:13px;white-space:nowrap;">{s['date']}</td>
          <td style="padding:8px 12px 8px 0;"><a href="{link}" style="color:#111;text-decoration:none;">{s.get('title', '(untitled)')}</a></td>
          <td style="padding:8px 0;text-align:right;font-weight:600;">{views}</td>
        </tr>
        """
    if not recent_rows_html:
        recent_rows_html = "<tr><td colspan='3' style='padding:12px;color:#999;text-align:center;'>No strips published this week</td></tr>"

    # Top 5 all-time
    top_rows_html = ""
    for s in strips["top_5_cached"]:
        yt_url = f"https://youtu.be/{s['youtube_id']}"
        top_rows_html += f"""
        <tr>
          <td style="padding:6px 12px 6px 0;color:#555;font-size:13px;white-space:nowrap;">{s['date']}</td>
          <td style="padding:6px 12px 6px 0;"><a href="{yt_url}" style="color:#111;text-decoration:none;">{s['title']}</a></td>
          <td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_int(s['views'])}</td>
        </tr>
        """
    if not top_rows_html:
        top_rows_html = "<tr><td colspan='3' style='padding:12px;color:#999;text-align:center;'>No cached view counts yet</td></tr>"

    # Health flags
    health_flags = []
    if strips["missing_video_in_week"] > 0:
        health_flags.append(
            f"<li><b>{strips['missing_video_in_week']}</b> strip(s) this week missing a YouTube video</li>"
        )
    if subs.get("email_failed_7d", 0) > 0:
        health_flags.append(
            f"<li><b>{subs['email_failed_7d']}</b> Daily Lotus email failures this week</li>"
        )
    if yt.get("source_error"):
        health_flags.append(f"<li>YouTube: {yt['source_error']}</li>")
    if subs.get("source_error"):
        health_flags.append(f"<li>Supabase: {subs['source_error']}</li>")
    if ga4.get("source_error") and not ga4.get("available"):
        health_flags.append(f"<li>GA4: {ga4['source_error']}</li>")
    health_html = (
        f"<ul style='margin:8px 0 0 20px;padding:0;color:#c33;'>{''.join(health_flags)}</ul>"
        if health_flags
        else "<p style='margin:8px 0 0;color:#2d7a2d;'>All green.</p>"
    )

    subs_daimoku_delta = _delta(subs.get("daimoku_new_7d", 0))
    subs_content_delta = _delta(subs.get("content_new_7d", 0))

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f7f6f2;">
<div style="max-width:640px;margin:0 auto;padding:32px 24px;background:#fff;">

  <div style="border-bottom:3px solid #c9a961;padding-bottom:12px;margin-bottom:20px;">
    <div style="font-size:12px;color:#999;letter-spacing:1px;text-transform:uppercase;">The Lotus Lane — Weekly Traffic</div>
    <div style="font-size:22px;font-weight:600;color:#111;margin-top:4px;">{week_start} – {week_end}, {datetime.now(timezone.utc).year}</div>
  </div>

  <div style="margin-bottom:28px;">
    <div style="font-size:14px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Subscribers</div>
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <td style="padding:6px 0;color:#555;">Daily Lotus (confirmed, active)</td>
        <td style="padding:6px 0;text-align:right;">
          <span style="font-weight:600;">{_fmt_int(subs.get('daimoku_total', 0))}</span>
          <span style="color:#2d7a2d;font-size:13px;margin-left:8px;">{subs_daimoku_delta} this week</span>
        </td>
      </tr>
      <tr>
        <td style="padding:6px 0;color:#555;">New-strip notifications</td>
        <td style="padding:6px 0;text-align:right;">
          <span style="font-weight:600;">{_fmt_int(subs.get('content_total', 0))}</span>
          <span style="color:#2d7a2d;font-size:13px;margin-left:8px;">{subs_content_delta} this week</span>
        </td>
      </tr>
      <tr>
        <td style="padding:6px 0;color:#555;">Emails sent (Daily Lotus)</td>
        <td style="padding:6px 0;text-align:right;font-weight:600;">{_fmt_int(subs.get('email_sent_7d', 0))}</td>
      </tr>
    </table>
  </div>

  {_ga4_section(ga4)}

  <div style="margin-bottom:28px;">
    <div style="font-size:14px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">YouTube Channel</div>
    {ch_rows}
  </div>

  <div style="margin-bottom:28px;">
    <div style="font-size:14px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">This Week's Strips</div>
    <table style="width:100%;border-collapse:collapse;border-top:1px solid #eee;">
      <thead>
        <tr style="color:#999;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;">
          <th style="padding:8px 0;text-align:left;font-weight:500;">Date</th>
          <th style="padding:8px 0;text-align:left;font-weight:500;">Title</th>
          <th style="padding:8px 0;text-align:right;font-weight:500;">YT Views</th>
        </tr>
      </thead>
      <tbody>{recent_rows_html}</tbody>
    </table>
  </div>

  <div style="margin-bottom:28px;">
    <div style="font-size:14px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Top 5 Strips (all-time, cached views)</div>
    <table style="width:100%;border-collapse:collapse;border-top:1px solid #eee;">
      <tbody>{top_rows_html}</tbody>
    </table>
  </div>

  <div style="margin-bottom:28px;padding:14px 16px;background:#faf8f1;border-left:3px solid #c9a961;">
    <div style="font-size:14px;color:#555;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Health</div>
    {health_html}
  </div>

  <div style="margin-top:32px;padding-top:16px;border-top:1px solid #eee;font-size:12px;color:#999;line-height:1.6;">
    <p style="margin:0 0 8px;"><b>Sources wired:</b> Supabase (subscribers), YouTube Data API (channel + video views), GA4 (site traffic), strips.json (publishing).</p>
    <p style="margin:0 0 8px;"><b>Not yet wired:</b> GoatCounter ({GOATCOUNTER_DASHBOARD}) — needs API token. Reply with &quot;wire up GoatCounter&quot; to add.</p>
    <p style="margin:0;">Generated {today} UTC. Runs every Monday 8:00 IST.</p>
  </div>

</div>
</body></html>
"""


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def send_email(to: str, subject: str, html: str, dry_run: bool = False) -> None:
    if dry_run:
        print(html)
        print(f"\n[dry-run] would send to {to} — subject: {subject}", file=sys.stderr)
        return

    key = os.environ.get("RESEND_API_KEY", "")
    if not key:
        raise RuntimeError("RESEND_API_KEY missing")
    resp = httpx.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"from": FROM_EMAIL, "to": [to], "subject": subject, "html": html},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Resend failed ({resp.status_code}): {resp.text}")
    print(f"Sent to {to} (id={resp.json().get('id')})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="print HTML, don't send")
    p.add_argument("--to", help="override recipient (default NOTIFY_EMAIL)")
    args = p.parse_args()

    strips_signal = collect_strips_signal()
    yt = collect_youtube(strips_signal["recent_video_ids"])
    subs = collect_subscribers()
    ga4 = collect_ga4()

    html = build_html(subs, yt, strips_signal, ga4)

    today = datetime.now(timezone.utc).strftime("%b %d")
    ch = yt.get("channel") or {}
    subs_count = subs.get("daimoku_total", 0)
    yt_subs = ch.get("subscribers", 0) if ch else 0
    subject = f"Lotus Lane weekly — {today} · {_fmt_int(subs_count)} daimoku · {_fmt_int(yt_subs)} YT subs"

    to = args.to or os.environ.get("NOTIFY_EMAIL", "").strip()
    if not to and not args.dry_run:
        raise RuntimeError("no recipient — set NOTIFY_EMAIL or pass --to")

    send_email(to or "dry-run@local", subject, html, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
