"""Every application/ld+json block on the site must be parseable JSON.

Google Search Console flagged thelotuslane.in on 2026-07-25 with "Unparsable
structured data — Bad escape sequence in string". 18 of the /ikeda/ theme pages
carried `\\-` inside JSON string values, which is not a legal JSON escape, so
Search dropped the structured data for those pages entirely.

The source (ikeda/quotes.json) was clean — the sequence was introduced into the
generated HTML afterwards by a hyphen/em-dash post-processing pass. JavaScript
tolerates an unknown escape (it just yields the character), so the visible page
and the inline `const quotes` array looked fine and nothing surfaced it until
GSC complained days later.

This test closes that gap: it parses every JSON-LD block in the repo, so a bad
escape fails `verify_deploy.py` before the push instead of silently costing us
rich results. It is deliberately generic — it catches any malformed structured
data, not just this one escape.
"""

import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

_LD_JSON = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)

_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "landing-mocks", "prototype"}


def _html_files():
    for path in sorted(REPO.rglob("*.html")):
        if _SKIP_DIRS & set(path.relative_to(REPO).parts):
            continue
        yield path


def _blocks():
    """(path, index, raw_json) for every JSON-LD block on the site."""
    for path in _html_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, match in enumerate(_LD_JSON.finditer(text)):
            yield path, i, match.group(1)


def test_site_has_structured_data():
    """Guard the guard: if the regex or layout ever changes so that nothing is
    collected, the parse test below would vacuously pass."""
    assert sum(1 for _ in _blocks()) > 100


def test_every_json_ld_block_parses():
    failures = []
    for path, index, raw in _blocks():
        try:
            json.loads(raw)
        except json.JSONDecodeError as e:
            rel = path.relative_to(REPO).as_posix()
            context = raw[max(0, e.pos - 60):e.pos + 60].replace("\n", " ")
            failures.append(f"{rel} (block {index}): {e.msg} at char {e.pos}\n    ...{context}...")

    assert not failures, (
        f"{len(failures)} unparseable JSON-LD block(s) — Google will drop the "
        "structured data for these pages:\n" + "\n".join(failures)
    )


def test_no_invalid_backslash_escapes_in_json_ld():
    """The specific 2026-07-25 regression, named so a recurrence is obvious.

    Valid JSON string escapes are: " \\ / b f n r t uXXXX. Anything else is a
    parse error — `\\-` was the one that shipped.
    """
    invalid = re.compile(r'\\(?!["\\/bfnrtu])')
    offenders = []
    for path, index, raw in _blocks():
        if invalid.search(raw):
            found = sorted({m.group(0) + raw[m.end():m.end() + 1]
                            for m in invalid.finditer(raw)})
            offenders.append(f"{path.relative_to(REPO).as_posix()} (block {index}): {found}")

    assert not offenders, (
        "invalid backslash escape(s) inside JSON-LD:\n" + "\n".join(offenders)
    )
