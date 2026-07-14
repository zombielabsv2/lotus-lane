#!/usr/bin/env python3
"""
Two Lamps — weekly cross-faith dialogue generator.

Once a week this picks one event from the world's news and writes a short
dialogue between Iqbal and Daisaku Ikeda (drawing on Nichiren). It then
publishes the same dialogue to BOTH sites:

  * iqbalforall.org  — prepends a typed entry to data/two-lamps.ts
  * thelotuslane.in  — prepends an <article> to two-lamps/index.html and
                       refreshes the headline in the homepage band

…and emails Rahul the published piece so a weak one is a 30-second pull.

Run from the lotus-lane repo root. The weekly workflow clones iqbal-for-all
into ./_iqbal and passes it via --iqbal-dir.

  python pipeline/generate_two_lamps.py --iqbal-dir _iqbal --lotus-dir .
  python pipeline/generate_two_lamps.py --iqbal-dir _iqbal --lotus-dir . --dry-run

Idempotent: if an entry for this week's slug already exists in
data/two-lamps.ts, the run is a no-op.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")

MODEL = "claude-sonnet-4-6"
FROM_EMAIL = "Lotus Lane Bot <notifications@rxjapps.in>"

# Free world-news RSS feeds — no API key. First that responds wins.
NEWS_FEEDS = [
    "https://feeds.npr.org/1004/rss.xml",          # NPR — World
    "https://feeds.bbci.co.uk/news/world/rss.xml",  # BBC — World
]

IQBAL_SITE = "https://iqbalforall.org"
LOTUS_SITE = "https://thelotuslane.in"

# Markers the script writes between — keep in sync with the two repos.
IQBAL_MARKER = "// TWO-LAMPS-CRON-INSERT"
LOTUS_ARTICLE_MARKER = "<!-- LATEST ENTRY"
LOTUS_HEADLINE_OPEN = "<!--LAMP-HEADLINE-->"
LOTUS_HEADLINE_CLOSE = "<!--/LAMP-HEADLINE-->"


# ---------------------------------------------------------------------------
# 1. The week's news
# ---------------------------------------------------------------------------

def fetch_headlines() -> list[str]:
    """Return ~18 world-news headlines from the first feed that responds."""
    for url in NEWS_FEEDS:
        try:
            resp = httpx.get(url, timeout=20, follow_redirects=True,
                             headers={"User-Agent": "TwoLamps/1.0"})
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            titles = [t.text.strip() for t in root.iter("title")
                      if t.text and t.text.strip()]
            # Drop the channel title (first <title>); keep item titles.
            headlines = titles[1:19]
            if len(headlines) >= 5:
                print(f"Fetched {len(headlines)} headlines from {url}")
                return headlines
        except Exception as e:  # noqa: BLE001 — try the next feed
            print(f"  feed failed ({url}): {e}", file=sys.stderr)
    raise RuntimeError("Could not fetch news headlines from any feed.")


# ---------------------------------------------------------------------------
# 2. The dialogue (Claude)
# ---------------------------------------------------------------------------

PROMPT = """\
You are writing this week's entry of "Two Lamps" — a recurring weekly feature \
that takes one event from the world's news and reads it through two minds:

  • IQBAL — Muhammad Iqbal, the poet-philosopher. Themes: khudi (the awakened \
self), motion and striving, anti-fatalism, courage, the fear of the new order, \
ishq (love) as the engine of life, contempt for stagnation, the falcon \
(shaheen). Fiery, aphoristic, prophetic. He may quote his own well-known \
couplets — but ONLY genuine ones; if unsure, speak in his voice without a \
citation. Never invent a couplet.

  • IKEDA — Daisaku Ikeda, the Buddhist humanist, drawing on the 13th-century \
teacher Nichiren. Themes: human revolution (inner change driving outer \
change), dialogue over force, "winter always turns to spring", the oneness of \
self and environment, the power of one person, hope, peace. Warm, humane, \
encouraging. He may reference Nichiren's real treatises and well-known lines \
— ONLY genuine ones. Never invent a quote.

TOPIC SELECTION — read these headlines and pick ONE event:
{headlines}

Hard rules for choosing and writing:
  • Do NOT take a partisan side on an active armed conflict, an election, or a \
political figure. If the week is dominated by war or politics, write about the \
HUMAN CONDITION underneath it — fear, grief, courage, change, hope — not the \
politics.
  • Prefer an event with genuine human-universal depth: a technological or \
scientific shift, an economic story, a climate event, a cultural moment, a \
moral question. Reach past the headline to what it asks of a person.
  • Two voices in conversation — they may agree, extend, or gently push back \
on each other. It is a dialogue, not two monologues. End in motion.

FORMAT — exactly 4 turns, alternating Iqbal, Ikeda, Iqbal, Ikeda. Each turn \
is one paragraph, roughly 70–110 words. The whole piece is about half a page.

Call the submit_dialogue tool with the finished entry. The closing line must \
take the form: "Two lamps, one week. Iqbal: … Ikeda: … Between them, …".
"""

# A single tool — Claude returns its `input` as already-valid structured JSON,
# which sidesteps the unescaped-quote breakage of free-text JSON.
TOOL = {
    "name": "submit_dialogue",
    "description": "Submit the finished Two Lamps dialogue entry.",
    "input_schema": {
        "type": "object",
        "properties": {
            "slugStub": {"type": "string",
                         "description": "3-4 word kebab-case slug, no date"},
            "headline": {"type": "string",
                         "description": "evocative, non-partisan, ~6-9 words"},
            "kicker": {"type": "string",
                       "description": "4-7 word sub-theme line"},
            "summary": {"type": "string",
                        "description": "1-2 sentence index teaser, ~25 words"},
            "framing": {"type": "string",
                        "description": "2-4 sentences: the event stated "
                        "neutrally, then the human question underneath"},
            "iqbal_first": {"type": "string",
                            "description": "Iqbal's opening turn — one "
                            "paragraph, 70-110 words"},
            "ikeda_first": {"type": "string",
                            "description": "Ikeda's reply — one paragraph, "
                            "70-110 words"},
            "iqbal_second": {"type": "string",
                             "description": "Iqbal's second turn — one "
                             "paragraph, 70-110 words"},
            "ikeda_second": {"type": "string",
                             "description": "Ikeda's closing turn — one "
                             "paragraph, 70-110 words"},
            "closing": {"type": "string",
                        "description": "one closing line, 'Two lamps, one "
                        "week. ...'"},
        },
        "required": ["slugStub", "headline", "kicker", "summary", "framing",
                     "iqbal_first", "ikeda_first", "iqbal_second",
                     "ikeda_second", "closing"],
    },
}


def generate_dialogue(headlines: list[str]) -> dict:
    """Call Claude and return a validated dialogue dict."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    prompt = PROMPT.format(headlines="\n".join(f"  - {h}" for h in headlines))
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 2200,
            "tools": [TOOL],
            "tool_choice": {"type": "tool", "name": "submit_dialogue"},
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Anthropic failed ({resp.status_code}): {resp.text}")

    data = None
    for block in resp.json().get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "submit_dialogue":
            data = block["input"]
            break
    if data is None:
        raise RuntimeError("no submit_dialogue tool_use block in response")

    # Validate — fail loudly rather than publish garbage.
    fields = ("slugStub", "headline", "kicker", "summary", "framing",
              "iqbal_first", "ikeda_first", "iqbal_second", "ikeda_second",
              "closing")
    for key in fields:
        val = data.get(key)
        if not val or not isinstance(val, str):
            raise RuntimeError(f"Claude response missing/invalid '{key}'")

    # Assemble the 4 turns in fixed order — the schema is flat strings so the
    # model can't stringify a nested array.
    data["turns"] = [
        {"speaker": "Iqbal", "text": data["iqbal_first"].strip()},
        {"speaker": "Ikeda", "text": data["ikeda_first"].strip()},
        {"speaker": "Iqbal", "text": data["iqbal_second"].strip()},
        {"speaker": "Ikeda", "text": data["ikeda_second"].strip()},
    ]
    return data


# ---------------------------------------------------------------------------
# 3. Dates / slug
# ---------------------------------------------------------------------------

def week_anchor() -> dt.date:
    """The Saturday of the current week — entries are anchored to it."""
    today = dt.datetime.now(dt.timezone.utc).date()
    days_ahead = (5 - today.weekday()) % 7  # Mon=0 … Sat=5
    return today + dt.timedelta(days=days_ahead)


def slugify(stub: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", stub.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


# ---------------------------------------------------------------------------
# 4. Write — iqbalforall.org
# ---------------------------------------------------------------------------

def build_ts_entry(d: dict) -> str:
    """A TypeScript LampEntry object literal, 2-space indented for the array."""
    def s(v: str) -> str:  # JSON strings are valid TS strings
        return json.dumps(v, ensure_ascii=False)

    turns = ",\n".join(
        f'      {{ speaker: "{t["speaker"]}", text: {s(t["text"])} }}'
        for t in d["turns"]
    )
    return (
        "  {\n"
        f'    slug: {s(d["slug"])},\n'
        f'    isoDate: {s(d["isoDate"])},\n'
        f'    dateLabel: {s(d["dateLabel"])},\n'
        f'    headline: {s(d["headline"])},\n'
        f'    kicker: {s(d["kicker"])},\n'
        f'    summary: {s(d["summary"])},\n'
        f'    framing: {s(d["framing"])},\n'
        "    turns: [\n"
        f"{turns}\n"
        "    ],\n"
        f'    closing: {s(d["closing"])},\n'
        "  },"
    )


def write_iqbal(iqbal_dir: str, d: dict, dry_run: bool) -> None:
    path = os.path.join(iqbal_dir, "data", "two-lamps.ts")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if IQBAL_MARKER not in src:
        raise RuntimeError(f"insert marker not found in {path}")

    entry = build_ts_entry(d)
    lines = src.split("\n")
    out = []
    for line in lines:
        out.append(line)
        if IQBAL_MARKER in line:
            out.append(entry)
    new_src = "\n".join(out)

    if dry_run:
        print(f"[dry-run] would write {path} (+{len(entry.splitlines())} lines)")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_src)
    print(f"Wrote {path}")


# ---------------------------------------------------------------------------
# 5. Write — thelotuslane.in
# ---------------------------------------------------------------------------

def build_lotus_article(d: dict) -> str:
    def esc(v: str) -> str:
        return html.escape(v, quote=False)

    turns = []
    for t in d["turns"]:
        cls = "iqbal" if t["speaker"] == "Iqbal" else "ikeda"
        turns.append(
            f'      <div class="turn {cls}">\n'
            f'        <div class="who">{t["speaker"]}</div>\n'
            f"        <p>{esc(t['text'])}</p>\n"
            f"      </div>"
        )
    turns_html = "\n\n".join(turns)
    return (
        '    <article class="entry">\n'
        f'      <div class="date">{esc(d["dateLabel"])}</div>\n'
        f'      <h3>{esc(d["headline"])}</h3>\n\n'
        f'      <p class="framing">{esc(d["framing"])}</p>\n\n'
        f"{turns_html}\n\n"
        f'      <p class="closing">{esc(d["closing"])}</p>\n'
        "    </article>"
    )


def write_lotus(lotus_dir: str, d: dict, dry_run: bool) -> None:
    # 5a — prepend the article on the Two Lamps page.
    page = os.path.join(lotus_dir, "two-lamps", "index.html")
    with open(page, encoding="utf-8") as f:
        src = f.read()
    if LOTUS_ARTICLE_MARKER not in src:
        raise RuntimeError(f"article marker not found in {page}")

    article = build_lotus_article(d)
    lines = src.split("\n")
    out = []
    for line in lines:
        out.append(line)
        if LOTUS_ARTICLE_MARKER in line:
            out.append(article)
            out.append("")  # blank line before the previous article
    new_page = "\n".join(out)

    # 5b — refresh the homepage band headline.
    home = os.path.join(lotus_dir, "index.html")
    with open(home, encoding="utf-8") as f:
        home_src = f.read()
    pattern = re.compile(
        re.escape(LOTUS_HEADLINE_OPEN) + ".*?" + re.escape(LOTUS_HEADLINE_CLOSE),
        re.DOTALL,
    )
    if not pattern.search(home_src):
        raise RuntimeError(f"headline markers not found in {home}")
    new_home = pattern.sub(
        LOTUS_HEADLINE_OPEN + html.escape(d["headline"], quote=False)
        + LOTUS_HEADLINE_CLOSE,
        home_src,
    )

    if dry_run:
        print(f"[dry-run] would write {page} (+article) and {home} (band headline)")
        return
    with open(page, "w", encoding="utf-8") as f:
        f.write(new_page)
    with open(home, "w", encoding="utf-8") as f:
        f.write(new_home)
    print(f"Wrote {page} and {home}")


# ---------------------------------------------------------------------------
# 6. Notify Rahul
# ---------------------------------------------------------------------------

def send_email(d: dict, dry_run: bool) -> None:
    iqbal_url = f"{IQBAL_SITE}/two-lamps/{d['slug']}"
    lotus_url = f"{LOTUS_SITE}/two-lamps/"

    turns_html = "".join(
        f'<p style="margin:14px 0;"><b style="color:'
        f'{"#b07d28" if t["speaker"] == "Iqbal" else "#c0392b"};">'
        f'{t["speaker"]}</b><br>{html.escape(t["text"])}</p>'
        for t in d["turns"]
    )
    body = f"""\
<div style="font-family:Segoe UI,system-ui,sans-serif;max-width:640px;margin:0 auto;color:#2d2d2d;">
  <p style="font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#c0392b;font-weight:700;">
    Two Lamps &middot; {html.escape(d['dateLabel'])}</p>
  <h2 style="font-weight:400;">{html.escape(d['headline'])}</h2>
  <p style="font-style:italic;color:#6a6a6a;border-left:3px solid #c0392b;padding-left:14px;">
    {html.escape(d['framing'])}</p>
  {turns_html}
  <p style="font-style:italic;color:#6a5a30;border-top:1px solid #e8d9b3;padding-top:14px;">
    {html.escape(d['closing'])}</p>
  <p style="font-size:14px;margin-top:24px;">
    Live now &mdash;<br>
    &bull; <a href="{iqbal_url}">{iqbal_url}</a><br>
    &bull; <a href="{lotus_url}">{lotus_url}</a></p>
  <p style="font-size:12px;color:#999;border-top:1px solid #eee;padding-top:12px;margin-top:20px;">
    Auto-published by the weekly Two Lamps workflow. If this one is weak,
    revert the two commits &mdash; the homepage band and page both roll back.</p>
</div>"""

    subject = f"Two Lamps published — {d['headline']}"
    if dry_run:
        print(f"[dry-run] would email {NOTIFY_EMAIL or '(NOTIFY_EMAIL unset)'} — {subject}")
        return
    if not RESEND_API_KEY or not NOTIFY_EMAIL:
        print("RESEND_API_KEY or NOTIFY_EMAIL missing — skipping email", file=sys.stderr)
        return
    resp = httpx.post(
        "https://ejvavmpieilvigjktugh.supabase.co/functions/v1/resend-send/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                 "Content-Type": "application/json"},
        json={"from": FROM_EMAIL, "to": [NOTIFY_EMAIL],
              "subject": subject, "html": body},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Resend failed ({resp.status_code}): {resp.text}")
    print(f"Emailed {NOTIFY_EMAIL}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--iqbal-dir", required=True, help="path to iqbal-for-all checkout")
    p.add_argument("--lotus-dir", default=".", help="path to lotus-lane checkout")
    p.add_argument("--dry-run", action="store_true",
                   help="generate and print only — no writes, no email")
    args = p.parse_args()

    anchor = week_anchor()
    iso = anchor.isoformat()
    date_label = f"Week of {anchor.strftime('%B')} {anchor.day}, {anchor.year}"

    # Idempotency — already published for this week?
    ts_path = os.path.join(args.iqbal_dir, "data", "two-lamps.ts")
    with open(ts_path, encoding="utf-8") as f:
        existing = f.read()
    if f'"{iso}-' in existing or f"'{iso}-" in existing:
        print(f"An entry for {iso} already exists — nothing to do.")
        return

    headlines = fetch_headlines()
    d = generate_dialogue(headlines)

    d["isoDate"] = iso
    d["dateLabel"] = date_label
    d["slug"] = f"{iso}-{slugify(d['slugStub'])}"

    print(f"\n=== Two Lamps — {d['dateLabel']} ===")
    print(f"Headline: {d['headline']}")
    print(f"Slug:     {d['slug']}\n")
    for t in d["turns"]:
        print(f"[{t['speaker']}] {t['text']}\n")
    print(f"{d['closing']}\n")

    write_iqbal(args.iqbal_dir, d, args.dry_run)
    write_lotus(args.lotus_dir, d, args.dry_run)
    send_email(d, args.dry_run)
    print("\nDone." if not args.dry_run else "\nDry run complete — nothing written.")


if __name__ == "__main__":
    main()
