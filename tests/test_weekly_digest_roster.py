"""The weekly digest's subscriber roster must render as stacked cards, never a
wide side-by-side table.

Rahul, 2026-07-20: the 5-column roster (name / email / challenges / freq /
joined) clipped on his phone — the Email and Challenges columns shattered one
glyph per line. Even with the central chokepoint's cell-shatter fixed, five real
columns don't fit a 320px screen, so the roster is now a card per subscriber
(no side-by-side columns => can't clip). This test stops it drifting back to a
table.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

MOD = Path(__file__).resolve().parent.parent / "pipeline" / "weekly_traffic_digest.py"

spec = importlib.util.spec_from_file_location("wtd", MOD)
wtd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wtd)

ROSTER = {
    "daimoku": [
        {"name": "Rahul", "email": "rxj@google.com",
         "challenges": ["career", "global-influence"],
         "frequency": "weekly", "subscribed_at": "2026-04-12T00:00:00Z"},
    ],
    "content": [
        {"email": "someverylongemailaddress.person@example.com",
         "subscribed_at": "2026-05-01T00:00:00Z"},
    ],
}


def test_roster_has_no_side_by_side_table():
    html = wtd._roster_section(ROSTER)
    assert "<table" not in html, "roster must be stacked cards, not a wide table"


def test_roster_still_shows_the_data():
    html = wtd._roster_section(ROSTER)
    for needle in ("Rahul", "rxj@google.com", "Challenges:", "career"):
        assert needle in html, f"roster card dropped {needle!r}"


def test_no_wide_table_anywhere_in_roster():
    """Belt-and-suspenders: if a future edit reintroduces any table here, it must
    not be a >=4-column data table (the shape that can't fit a phone)."""
    html = wtd._roster_section(ROSTER)
    for block in re.findall(r"<table\b.*?</table>", html, re.S | re.I):
        first_row = re.search(r"<tr\b.*?</tr>", block, re.S | re.I)
        cells = len(re.findall(r"<t[dh]\b", first_row.group(0), re.I)) if first_row else 0
        assert cells < 4, f"roster reintroduced a {cells}-column table — won't fit a phone"
