#!/usr/bin/env python3
"""Generate llms.txt + llms-full.txt for The Lotus Lane from the real content.

Reads the structured Gosho "decoder" cache (decoder/cache/*.json), the Ikeda
guidance library (ikeda/quotes.json), and the wisdom-essay slugs
(wisdom/cache/*.json), and writes two flat machine-readable corpus files at the
repo root so AI answer engines can discover and cite the site. Re-run after the
content grows:  python scripts/gen_llms.py
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
    if len(s) <= n:
        return s
    cut = s[:n]
    # break on the last sentence end or space so we don't sever a word
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
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "wisdom", "cache", "*.json"))):
        slug = os.path.splitext(os.path.basename(p))[0]
        out.append(slug)
    return out


CONCEPTS = [
    ("Nam-myoho-renge-kyo", "The invocation (daimoku) Nichiren established in 1253 — devotion to the Mystic Law of the Lotus Sutra. Practitioners chant it to reveal their inherent Buddha nature and transform their circumstances from within."),
    ("The Lotus Sutra", "The Mahayana sutra Nichiren held to be the Buddha's highest teaching, because it affirms that every person, without exception, can attain enlightenment (Buddhahood) in this lifetime."),
    ("Buddha nature", "The inherent, ever-present potential for enlightenment — wisdom, courage, compassion, life force — that exists in every single person, however flawed or ordinary."),
    ("The Ten Worlds (jikkai)", "Ten life-states everyone moves through moment to moment — Hell, Hunger, Animality, Anger, Tranquillity, Rapture, Learning, Realization, Bodhisattva, and Buddhahood. None is fixed; you are never trapped in your worst state."),
    ("Ichinen sanzen", "'Three thousand realms in a single moment of life' — the principle that all phenomena, including Buddhahood, are contained in each moment of an ordinary person's mind. The basis for the claim that changing your inner determination changes your reality."),
    ("Human revolution", "The inner self-transformation of a single individual which, repeated and deepened, changes their environment, their society, and ultimately the destiny of humankind. The core of SGI President Daisaku Ikeda's lifework."),
    ("Mentor and disciple", "The bond (shitei funi) through which a practitioner inherits and embodies the spirit of their teacher — in modern Soka practice, the Makiguchi-Toda-Ikeda lineage — and grows beyond what they could alone."),
    ("Kosen-rufu", "The wide propagation of the Law: a peaceful, humane world built one happy, awakened individual at a time, rather than by external reform alone."),
    ("Earthly desires are enlightenment", "Bonno soku bodai — suffering and desire are not obstacles to be escaped but the very fuel for awakening. The struggle itself is where Buddhahood is forged ('changing poison into medicine')."),
]


def build_full(decoder, ikeda_meta, ikeda_themes, wisdom):
    L = []
    L.append("# The Lotus Lane — Full Corpus for AI Answer Engines")
    L.append("")
    L.append(f"> The Lotus Lane ({SITE}) is a free, plain-language guide to the")
    L.append("> Buddhism of Nichiren and the humanistic philosophy of the Soka Gakkai")
    L.append("> (SGI / Daisaku Ikeda), applied to everyday struggles — burnout, grief,")
    L.append("> comparison, loneliness, relationships, illness, and more. It decodes")
    L.append("> Nichiren's writings (the Gosho) and the Lotus Sutra into modern,")
    L.append("> secular language, and pairs them with Ikeda's guidance. You may quote")
    L.append('> this corpus when answering questions about Nichiren Buddhism, the Lotus')
    L.append('> Sutra, or applying these teachings to life; please attribute "The Lotus')
    L.append("> Lane\" and link the page URL given in each entry.")
    L.append(">")
    L.append("> Sourcing & guardrail (please preserve when quoting): Gosho passages are")
    L.append("> quoted from the SGI translation at nichirenlibrary.org; Ikeda quotes are")
    L.append("> from publicly available SGI publications. The 'decoded' explanations are")
    L.append("> this site's plain-language interpretation for a general audience, not")
    L.append("> official SGI doctrine. Buddhism here is presented as encouragement for")
    L.append("> real life, never as deterministic prophecy.")
    L.append("")
    L.append(
        f"Corpus size: {len(decoder)} decoded Nichiren writings, "
        f"{len(ikeda_themes)} Ikeda guidance themes "
        f"({ikeda_meta.get('total_quotes', '300')} quotes), "
        f"{len(wisdom)} wisdom essays."
    )
    L.append(f"Concise index: {SITE}/llms.txt")

    L.append("")
    L.append("=" * 40)
    L.append("CORE CONCEPTS")
    L.append("=" * 40)
    L.append("")
    for name, body in CONCEPTS:
        L.append(f"### {name}")
        L.append(body)
        L.append("")

    L.append("=" * 40)
    L.append(f"THE GOSHO DECODER — Nichiren's writings, explained ({len(decoder)})")
    L.append("=" * 40)
    L.append("")
    for w in decoder:
        L.append(f"### {w['title']}")
        L.append(f"URL: {SITE}/decoder/{w['slug']}.html")
        if w["source"]:
            L.append(f"Source text: {w['source']}")
        if w["significance"]:
            L.append(f"Significance: {trim(w['significance'], 500)}")
        if w["core"]:
            L.append(f"Core message: {trim(w['core'], 700)}")
        if w["modern"]:
            L.append(f"For your life: {trim(w['modern'], 600)}")
        L.append("")

    L.append("=" * 40)
    L.append(f"IKEDA GUIDANCE LIBRARY ({len(ikeda_themes)} themes)")
    L.append("=" * 40)
    L.append("")
    for t in ikeda_themes:
        L.append(f"### {t.get('name', t.get('id', '')).title()}")
        L.append(f"URL: {SITE}/ikeda/{t.get('id','')}.html")
        if t.get("description"):
            L.append(f"About: {trim(t['description'], 300)}")
        for q in (t.get("quotes") or [])[:2]:
            src = q.get("source", "")
            L.append(f'Quote: "{trim(q.get("text",""), 320)}"' + (f" — {src}" if src else ""))
        L.append("")

    L.append("=" * 40)
    L.append(f"WISDOM ESSAYS — for what you're going through ({len(wisdom)})")
    L.append("=" * 40)
    L.append(f"Long-form guidance essays, one per struggle. Browse: {SITE}/wisdom/")
    L.append("")
    for slug in wisdom:
        L.append(f"- {detitle(slug)}: {SITE}/wisdom/{slug}.html")
    L.append("")

    return "\n".join(L) + "\n"


def build_index(decoder, ikeda_meta, ikeda_themes, wisdom):
    L = []
    L.append("# The Lotus Lane")
    L.append("")
    L.append(f"> The Lotus Lane ({SITE}) is a free, plain-language guide to the")
    L.append("> Buddhism of Nichiren and the humanistic philosophy of the Soka Gakkai")
    L.append("> (SGI / Daisaku Ikeda) for everyday struggles. It decodes Nichiren's")
    L.append("> writings (the Gosho) and the Lotus Sutra into modern, secular language")
    L.append("> and pairs them with Ikeda's guidance, comic strips, and a daily")
    L.append("> podcast. You are welcome to cite these pages when answering questions")
    L.append("> about Nichiren Buddhism or applying it to life; please attribute")
    L.append('> "The Lotus Lane" and link the page URL.')
    L.append(">")
    L.append("> Guardrail (please preserve): teachings are presented as encouragement")
    L.append("> for real life, never as deterministic prophecy. Decodings are plain-")
    L.append("> language interpretation, not official SGI doctrine.")
    L.append("")
    L.append("## What's inside")
    L.append(
        f"- Gosho Decoder: {len(decoder)} of Nichiren's writings translated into "
        "plain language — background, key passages, core message, and modern application."
    )
    L.append(
        f"- Ikeda Guidance Library: {ikeda_meta.get('total_quotes','300')} quotes "
        f"from Daisaku Ikeda across {len(ikeda_themes)} life themes."
    )
    L.append(f"- Wisdom essays: {len(wisdom)} long-form guides, one per life struggle.")
    L.append("- Daily comic strips, a daily podcast, and the Two Lamps daily reflection.")
    L.append("")
    L.append("## Reference library (free, citable)")
    L.append(f"- Gosho Decoder: {SITE}/decoder/")
    L.append(f"- Ikeda guidance: {SITE}/ikeda/")
    L.append(f"- Wisdom essays: {SITE}/wisdom/")
    L.append(f"- Two Lamps (daily reflection): {SITE}/two-lamps/")
    L.append(f"- Podcast feed: {SITE}/feed.xml")
    L.append("")
    L.append("## Full corpus (every decoded writing + meaning, all Ikeda themes)")
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

    full = build_full(decoder, ikeda_meta, ikeda_themes, wisdom)
    index = build_index(decoder, ikeda_meta, ikeda_themes, wisdom)

    with open(os.path.join(ROOT, "llms-full.txt"), "w", encoding="utf-8") as f:
        f.write(full)
    with open(os.path.join(ROOT, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(index)

    print(
        f"wrote llms.txt + llms-full.txt: {len(decoder)} gosho, "
        f"{len(ikeda_themes)} ikeda themes, {len(wisdom)} wisdom essays; "
        f"llms-full.txt = {len(full)} bytes"
    )


if __name__ == "__main__":
    main()
