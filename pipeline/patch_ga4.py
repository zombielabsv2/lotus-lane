"""Inject GA4 tracking snippet into every .html at repo root + subdirs.

Idempotent via GA4_MARKER. Re-run to update the ID.

Run: python pipeline/patch_ga4.py
"""
from __future__ import annotations

from pathlib import Path

MEASUREMENT_ID = "G-4DM9P70KJ6"

ROOT = Path(__file__).resolve().parent.parent
GA4_MARKER = "<!-- ga4 -->"

SKIP_NAMES = {"googlea378c3b4c0072e97.html"}  # GSC verification file, leave as-is

SNIPPET_TEMPLATE = (
    "\n{marker}\n"
    "<script>\n"
    "  (function() {{\n"
    "    var mid = '{mid}';\n"
    "    if (mid.indexOf('PLACEHOLDER') !== -1) return;\n"
    "    var s = document.createElement('script');\n"
    "    s.async = true;\n"
    "    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + mid;\n"
    "    document.head.appendChild(s);\n"
    "    window.dataLayer = window.dataLayer || [];\n"
    "    window.gtag = function(){{window.dataLayer.push(arguments);}};\n"
    "    window.gtag('js', new Date());\n"
    "    window.gtag('config', mid);\n"
    "  }})();\n"
    "</script>\n"
)


def snippet() -> str:
    return SNIPPET_TEMPLATE.format(marker=GA4_MARKER, mid=MEASUREMENT_ID)


def patch_one(path: Path) -> str:
    html = path.read_text(encoding="utf-8")
    if GA4_MARKER in html:
        marker_idx = html.find(GA4_MARKER)
        start = html.rfind("\n", 0, marker_idx)
        close_tag = "</script>"
        end = html.find(close_tag, marker_idx) + len(close_tag)
        new_html = html[:start] + snippet().rstrip() + html[end:]
        if new_html == html:
            return "skipped"
        path.write_text(new_html, encoding="utf-8")
        return "replaced"

    if "</head>" not in html:
        return "no-head"
    new_html = html.replace("</head>", snippet() + "</head>", 1)
    path.write_text(new_html, encoding="utf-8")
    return "injected"


def main() -> None:
    counts: dict[str, int] = {}
    for path in ROOT.rglob("*.html"):
        if path.name in SKIP_NAMES:
            continue
        if any(part.startswith(".") or part == "node_modules" for part in path.parts):
            continue
        status = patch_one(path)
        counts[status] = counts.get(status, 0) + 1

    print(f"Lotus Lane GA4 patch (ID: {MEASUREMENT_ID})")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
