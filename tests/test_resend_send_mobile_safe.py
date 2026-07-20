"""Guard the empire email chokepoint (supabase/functions/resend-send/index.ts).

Every empire email flows through this one Deno function's `mobileSafe()` before
Resend delivers it. On 2026-07-20 Rahul kept screenshotting the same clip — a
subscriber roster whose Email/Challenges columns shattered one glyph per line,
and the daily brief's automation table. Root cause: the central style pinned
`overflow-wrap: anywhere; word-break: break-word;`, which shrinks a text cell's
min-content width to ~1 char. The Python twin (kari-growth-platform/utils/
email_mobile.py) fixed exactly this on 2026-07-19 by switching to the gentle
`overflow-wrap: break-word`; the fix was never propagated here, so the central
layer kept re-breaking every multi-word cell across all 113 email types.

This test locks the fix so the aggressive rule can't drift back in — a static
check on the ACTIVE CSS (comments stripped, so the cautionary note that *names*
the bad rules doesn't trip it), plus a behavioral check via node when available.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

FUNC = Path(__file__).resolve().parent.parent / "supabase" / "functions" / "resend-send" / "index.ts"


def _source() -> str:
    return FUNC.read_text(encoding="utf-8")


def _active_css(src: str) -> str:
    """The function source minus CSS/JS block comments, so we assert on rules
    that actually take effect, not on the explanatory comment that references
    the forbidden rules by name."""
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def test_chokepoint_uses_gentle_wrap_rule():
    css = _active_css(_source())
    assert re.search(r"overflow-wrap:\s*break-word", css), \
        "the chokepoint must break long tokens with the GENTLE overflow-wrap:break-word"


def test_chokepoint_never_reintroduces_the_shatter_rules():
    """overflow-wrap:anywhere and word-break:break-word both crush a text cell to
    a 1-char column — the exact bug. They must never appear as an ACTIVE rule."""
    css = _active_css(_source())
    assert not re.search(r"overflow-wrap:\s*anywhere", css), \
        "overflow-wrap:anywhere shatters roster/scorecard cells one glyph per line"
    assert not re.search(r"word-break:\s*break-word", css), \
        "word-break:break-word shatters roster/scorecard cells one glyph per line"


def test_chokepoint_still_injects_viewport():
    # The other half of the fix — without <meta viewport> a phone lays the email
    # out at ~980px and clips it. Keep it wired.
    assert "name=\"viewport\"" in _source()


_NODE = shutil.which("node")


@pytest.mark.skipif(_NODE is None, reason="node not available to execute the Deno transform")
def test_mobile_safe_behaviour_via_node(tmp_path):
    """Run the real mobileSafe() and assert the roster is no longer shattered and
    the transform is idempotent (it used to double-wrap wide tables)."""
    src = _source()
    src = re.sub(r"Deno\.serve[\s\S]*$", "", src)
    src = re.sub(r"export function mobileSafe\(html:\s*string\):\s*string",
                 "function mobileSafe(html)", src)
    harness = src + textwrap.dedent("""
        const roster = '<html><head></head><body><table><thead><tr>'
          + '<th>Name</th><th>Email</th><th>Challenges</th><th>Freq</th><th>Joined</th>'
          + '</tr></thead><tbody><tr><td>Rahul</td><td>rxj@google.com</td>'
          + '<td>career, global-influence</td><td>weekly</td><td>Apr 12</td></tr>'
          + '</tbody></table></body></html>';
        const out = mobileSafe(roster);
        const activeCss = (h) => h.replace(/\\/\\*[\\s\\S]*?\\*\\//g, '');
        const css = activeCss(out);
        const scrolls = (h) => (h.match(/class="kbk-scroll"/g) || []).length;
        const checks = {
          viewport: /name="viewport"/.test(out),
          gentle_wrap: /overflow-wrap:\\s*break-word/.test(css),
          no_shatter: !/overflow-wrap:\\s*anywhere/.test(css) && !/word-break/.test(css),
          wrapped_once: scrolls(out) === 1,
          idempotent: mobileSafe(out) === out,
        };
        console.log(JSON.stringify(checks));
    """)
    f = tmp_path / "harness.mjs"
    f.write_text(harness, encoding="utf-8")
    res = subprocess.run([_NODE, str(f)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    import json
    checks = json.loads(res.stdout.strip().splitlines()[-1])
    assert all(checks.values()), f"mobileSafe behaviour regressed: {checks}"
