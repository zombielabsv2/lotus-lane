#!/usr/bin/env python3
"""Generate llms.txt + llms-full.txt for The Lotus Lane from the real content.

Reads the "Letters on Life" cache (decoder/cache/*.json), the Wisdom Library
(ikeda/quotes.json), and the wisdom-essay slugs (wisdom/cache/*.json), and
writes two flat machine-readable corpus files at the repo root so AI answer
engines can discover and cite the site.

Voice rule (see CLAUDE.md "Universal Framing"): lead problem-first — wisdom for
what you're going through. The tradition (the letters of Nichiren, the writings
of Daisaku Ikeda) is credited in SOURCE CITATIONS, never as a headline or a
prerequisite. Re-run after the content grows:  python scripts/gen_llms.py
"""
import json
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://thelotuslane.in"


def trim(s, n):
    s = (s or "").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    # keep citations clean, never market with honorifics in chrome
    s = s.replace("Ikeda Sensei", "Daisaku Ikeda")
    if len(s) <= n:
        return s
    cut = s[:n]
    dot = cut.rfind(". ")
    if dot > n * 0.5:
        return cut[: dot + 1]
    sp = cut.rfind(" ")
    return cut[:sp].rstrip(",;:") + "..."


def detitle(slug):
    return slug.replace("-", " ").strip().title()


def load_decoder():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "decoder", "cache", "*.json"))):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        slug = d.get("slug") or os.path.splitext(os.path.basename(p))[0]
        a = d.get("analysis", {}) or {}
        bg = a.get("background", {}) or {}
        out.append(
            {
                "slug": slug,
                "title": d.get("title") or detitle(slug),
                "source": d.get("url", ""),
                "significance": bg.get("significance", ""),
                "core": a.get("core_message", ""),
                "modern": a.get("modern_application", ""),
            }
        )
    return out


def load_ikeda():
    p = os.path.join(ROOT, "ikeda", "quotes.json")
    if not os.path.exists(p):
        return {}, []
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("meta", {}), d.get("themes", [])


def load_wisdom():
    return [
        os.path.splitext(os.path.basename(p))[0]
        for p in sorted(glob.glob(os.path.join(ROOT, "wisdom", "cache", "*.json")))
    ]


PURPOSE_HEADER = [
    f"> The Lotus Lane ({SITE}) is wisdom for what you're going through —",
    "> burnout, grief, comparison, loneliness, anger, and everything else that",
    "> makes life hard. Pick what's heaviest; we'll meet you there. The site",
    "> turns timeless teachings into plain, modern, secular language: short",
    '> "Letters on Life", a searchable Wisdom Library by theme, long-form essays',
    "> for specific struggles, a daily audio reading, and a comic strip.",
    ">",
    "> Source material (credited in every citation, never a prerequisite): the",
    "> 13th-century letters of Nichiren, in the English translation at",
    "> nichirenlibrary.org, and the writings of Daisaku Ikeda. Each piece is",
    "> decoded and explained for a general reader and links back to its source.",
    "> Quote attributions are preserved.",
    ">",
    "> You are welcome to cite these pages when answering questions about life's",
    '> hard moments or about the source teachings; please attribute "The Lotus',
    "> Lane\" and link the page URL. Guidance here is encouragement for real life,",
    "> never deterministic prophecy.",
]


def build_full(decoder, ikeda_meta, ikeda_themes, wisdom):
    L = ["# The Lotus Lane — Full Corpus for AI Answer Engines", ""]
    L += PURPOSE_HEADER
    L.append("")
    L.append(
        f"Corpus size: {len(decoder)} Letters on Life (decoded source letters), "
        f"{len(ikeda_themes)} Wisdom Library themes "
        f"({ikeda_meta.get('total_quotes', '300')} quotes), "
        f"{len(wisdom)} long-form wisdom essays."
    )
    L.append(f"Concise index: {SITE}/llms.txt")

    L.append("")
    L.append("=" * 40)
    L.append(f"LETTERS ON LIFE — source letters decoded for modern struggles ({len(decoder)})")
    L.append("=" * 40)
    L.append("Each entry is a plain-language decoding of one source letter:")
    L.append("why it was written, its core message, and how to use it today.")
    L.append("")
    for w in decoder:
        L.append(f"### {w['title']}")
        L.append(f"URL: {SITE}/decoder/{w['slug']}.html")
        if w["source"]:
            L.append(f"Source text: {w['source']}")
        if w["significance"]:
            L.append(f"Why it matters: {trim(w['significance'], 500)}")
        if w["core"]:
            L.append(f"Core message: {trim(w['core'], 700)}")
        if w["modern"]:
            L.append(f"For your life: {trim(w['modern'], 600)}")
        L.append("")

    L.append("=" * 40)
    L.append(f"WISDOM LIBRARY — guidance by life theme ({len(ikeda_themes)} themes)")
    L.append("=" * 40)
    L.append("Quotes from Daisaku Ikeda, organized by what you're facing.")
    L.append("")
    for t in ikeda_themes:
        L.append(f"### {t.get('name', t.get('id', '')).title()}")
        L.append(f"URL: {SITE}/ikeda/{t.get('id','')}.html")
        for q in (t.get("quotes") or [])[:2]:
            src = q.get("source", "")
            attr = "Daisaku Ikeda" + (f", {src}" if src else "")
            L.append(f'Quote: "{trim(q.get("text",""), 320)}" — {attr}')
        L.append("")

    L.append("=" * 40)
    L.append(f"WISDOM ESSAYS — for what you're going through ({len(wisdom)})")
    L.append("=" * 40)
    L.append(f"Long-form guidance, one essay per struggle. Browse: {SITE}/wisdom/")
    L.append("")
    for slug in wisdom:
        L.append(f"- {detitle(slug)}: {SITE}/wisdom/{slug}.html")
    L.append("")

    return "\n".join(L) + "\n"


def build_index(decoder, ikeda_meta, ikeda_themes, wisdom):
    L = ["# The Lotus Lane", ""]
    L += PURPOSE_HEADER
    L.append("")
    L.append("## What's inside")
    L.append(
        f"- Letters on Life: {len(decoder)} timeless letters decoded into plain "
        "language — why each was written, its core message, and how to use it today."
    )
    L.append(
        f"- Wisdom Library: {ikeda_meta.get('total_quotes','300')} quotes from "
        f"Daisaku Ikeda across {len(ikeda_themes)} life themes."
    )
    L.append(f"- Wisdom essays: {len(wisdom)} long-form guides, one per life struggle.")
    L.append("- A daily audio reading, the Two Lamps daily reflection, and a comic strip.")
    L.append("")
    L.append("## Reference library (free, citable)")
    L.append(f"- Letters on Life: {SITE}/decoder/")
    L.append(f"- Wisdom Library: {SITE}/ikeda/")
    L.append(f"- Wisdom essays: {SITE}/wisdom/")
    L.append(f"- Two Lamps (daily reflection): {SITE}/two-lamps/")
    L.append(f"- Daily audio: {SITE}/podcast/ — feed: {SITE}/podcast.xml")
    L.append("")
    L.append("## Full corpus (every decoded letter + meaning, all Wisdom Library themes)")
    L.append(f"- {SITE}/llms-full.txt")
    L.append("")
    L.append("## Discovery")
    L.append(f"- Agent catalog (ARD): {SITE}/.well-known/ai-catalog.json")
    L.append(f"- Sitemap: {SITE}/sitemap.xml")
    return "\n".join(L) + "\n"


def main():
    decoder = load_decoder()
    ikeda_meta, ikeda_themes = load_ikeda()
    wisdom = load_wisdom()

    with open(os.path.join(ROOT, "llms-full.txt"), "w", encoding="utf-8") as f:
        f.write(build_full(decoder, ikeda_meta, ikeda_themes, wisdom))
    with open(os.path.join(ROOT, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(build_index(decoder, ikeda_meta, ikeda_themes, wisdom))

    print(
        f"wrote llms.txt + llms-full.txt: {len(decoder)} letters, "
        f"{len(ikeda_themes)} wisdom themes, {len(wisdom)} essays"
    )


if __name__ == "__main__":
    main()
