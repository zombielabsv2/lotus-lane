"""Guard the operator-mail deferral lane in the empire email chokepoint.

Rahul was receiving ~27 emails a day through this function; 59% of them were the
inbox agent's own replies narrating work it had already finished, and on
2026-08-27 and 2026-08-31 the volume pushed jindal.rahul+claude@gmail.com onto
the 18/day astromedha cap, so real alerts were 429'd and lost. Migration 153 adds
a third verdict - `deferred` - which captures the message into
`empire_operator_digest` for one 07:00 IST email instead of delivering it.

Two properties have to hold in THIS file, and neither is covered by
test_resend_send_mobile_safe.py, which strips everything from `Deno.serve` to EOF
before handing the rest to node:

1. A deferral must be answered with a 200, never a 429. ~108 Cloud Run jobs call
   this endpoint; a 429 makes every one of them log a failure for mail that was
   never lost, and Fleet Health then alarms on those failures - manufacturing
   exactly the noise the lane exists to remove.
2. The guard must be handed the body and the sender, or the digest has nothing
   to render.

Plus the one that predates this change and is easy to destroy while editing:
the fingerprint's NUL separator.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FUNC = Path(__file__).resolve().parent.parent / "supabase" / "functions" / "resend-send" / "index.ts"


def _source() -> str:
    return FUNC.read_text(encoding="utf-8")


def _active(src: str) -> str:
    """Source minus comments, so a comment that merely *describes* a behaviour
    can never satisfy an assertion about it."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def test_deferral_is_answered_with_200_not_429():
    active = _active(_source())
    # The single-message path returns a Resend-shaped success for a deferral.
    assert re.search(r"if\s*\(\s*v\.deferred\s*\)", active), \
        "the single-message path must branch on a deferred verdict"
    assert "deferred-${crypto.randomUUID()}" in active, \
        "a deferral must synthesise a Resend-shaped id so callers see success"
    # ...and it must sit BEFORE the refusal branch, or !v.allow swallows it and
    # every deferral becomes a 429.
    assert active.index("v.deferred") < active.index("if (!v.allow)"), \
        "the deferred branch must precede the !v.allow refusal branch"


def test_batch_path_separates_deferrals_from_refusals():
    active = _active(_source())
    assert re.search(r"else\s+if\s*\(\s*v\.deferred\s*\)", active), \
        "the batch path must count deferrals apart from refusals"
    assert re.search(r"!kept\.length\s*&&\s*deferred\s*&&\s*!refused\.length", active), \
        "an all-deferred batch is a success and must not 429"


def test_guard_receives_the_body_and_sender():
    active = _active(_source())
    assert "p_html:" in active and "p_from:" in active, \
        "empire_claim_send needs the body and sender or the digest cannot render"


def test_deferred_verdict_is_not_treated_as_a_refusal():
    active = _active(_source())
    assert re.search(r'reason\s*===\s*"deferred"', active), \
        "allowSend must recognise 'deferred' as distinct from a refusal"


def test_fingerprint_nul_separator_survives():
    """`${subject}\x00${html}` - without the NUL, "ab"+"c" and "a"+"bc" collide
    and the duplicate guard silently suppresses a different email."""
    raw = FUNC.read_bytes()
    assert raw.count(0) == 1, \
        f"expected exactly one NUL (the fingerprint separator), found {raw.count(0)}"
    src = _source()
    i = src.index("\x00")
    window = src[i - 60:i + 40]
    assert "subject" in window and "html" in window, \
        "the NUL must still separate subject from html in the fingerprint"


def test_whole_file_parses():
    """test_resend_send_mobile_safe.py only parses the half above Deno.serve.
    The deferral branches live below it, so parse the WHOLE file here."""
    out = subprocess.run(
        [
            "node", "--experimental-strip-types", "--check",
            str(FUNC.with_suffix(".ts")),
        ],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, f"edge function does not parse:\n{out.stderr}"
