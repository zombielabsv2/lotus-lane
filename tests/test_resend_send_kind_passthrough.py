"""The send guard must be TOLD what a message is, not left to infer it.

`empire_claim_send` decides product-versus-marketing so the rolling weekly
ceiling only ever binds on campaigns. It accepts an explicit `p_kind` and
honours it, and only falls back to matching the subject against
`empire_send_policy.product_patterns` when it gets none.

Nothing passed one until 2026-09-12. So every send was classified by inference,
and an unrecognised subject defaults to `marketing` -- which means REFUSED once
the four weekly slots are gone. Read from `email_log` filtered to weekly_cap,
that fired 10 times across 4 dates and 6 people, every one of them mail somebody
PAYS for:

    2026-08-27  evening reflection   amit_gupta, jyoti_borade,
                                     nicolette_de_csipkay, prashant_singh,
                                     reem_osama
    2026-08-29  dasha transition     jyoti_borade
    2026-08-30  dasha transition     jyoti_borade
    2026-09-09  daily guidance x3    anand_a_deshpande

Each was "fixed" by adding the missing subject pattern, which repairs the
instance and leaves the class alive: the daily guidance subject is chosen at
send time by a chart-hook with four variants, so which one a reader gets is a
property of THEIR chart and the bug surfaces one subscriber at a time.

Two properties have to hold here, and the second is the one that makes the first
safe to ship:

1. A caller's `kind` reaches the guard as `p_kind`.
2. `kind` NEVER reaches api.resend.com. This function's stated contract is
   "byte-for-byte the Resend API", and it forwards the parsed body verbatim, so
   a control field left in the payload would be handed to a third-party API that
   never agreed to accept it. Both the single-message and the /emails/batch
   lanes have to strip it.

Plus the separator that is trivially destroyed while editing this file: the
fingerprint joins subject and html with a literal NUL so the boundary cannot be
forged by a subject that merely contains the html's opening bytes.
"""
from __future__ import annotations

import re
from pathlib import Path

FUNC = (Path(__file__).resolve().parent.parent
        / "supabase" / "functions" / "resend-send" / "index.ts")


def _source() -> str:
    return FUNC.read_text(encoding="utf-8")


def _active(src: str) -> str:
    """Source minus comments, so a comment that merely DESCRIBES a behaviour can
    never satisfy an assertion about it."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def test_an_explicit_kind_is_forwarded_to_the_guard():
    active = _active(_source())
    assert re.search(r"p_kind\s*:", active), (
        "empire_claim_send is not being told what this message is, so it will "
        "fall back to guessing from the subject line -- the exact failure that "
        "refused paid mail 10 times between 27 Aug and 9 Sep 2026."
    )
    assert re.search(r"p_kind\s*:[^,]*msg\.kind", active, flags=re.S), (
        "p_kind must come from the CALLER's message, not be hardcoded. A "
        "hardcoded 'product' would exempt every campaign and the weekly cap "
        "would bind on nothing at all."
    )


def test_a_caller_that_passes_no_kind_keeps_the_old_behaviour():
    """The rollout safety property. Lotus Lane, KBK and byrxj all send through
    this function and none of them passes a kind. They must be unaffected, which
    means an absent kind has to reach the guard as null so it falls back to
    subject matching exactly as before."""
    active = _active(_source())
    m = re.search(r"p_kind\s*:(.{0,240}?),\n", active, flags=re.S)
    assert m, "could not read the p_kind expression"
    expr = m.group(1)
    assert "null" in expr, (
        "an absent or blank kind must resolve to null, not to a string. Any "
        "other default silently reclassifies every existing caller's mail."
    )


def test_kind_is_stripped_from_the_body_forwarded_to_resend():
    active = _active(_source())
    assert re.search(r"function stripKind\s*\(", active), (
        "no stripKind helper: our control field would be forwarded to "
        "api.resend.com, breaking this function's byte-for-byte contract."
    )
    assert re.search(r'delete\s+m\.kind', active), \
        "stripKind must actually remove the field, not merely inspect it"


def test_both_send_lanes_strip_it():
    active = _active(_source())
    assert re.search(r"kept\.map\(\s*stripKind\s*\)", active), (
        "the /emails/batch lane rebuilds its body from `kept` and must strip "
        "kind from every surviving message."
    )
    assert re.search(r"JSON\.stringify\(\s*stripKind\(\s*parsed\s*\)\s*\)", active), (
        "the single-message lane must re-serialise from the stripped object. "
        "Note it has to re-serialise rather than reuse the earlier `body`, "
        "because mobileSafe patches `parsed` in place and that transform must "
        "survive."
    )


def test_the_fingerprint_nul_separator_survives():
    raw = FUNC.read_bytes()
    assert raw.count(b"\x00") == 1, (
        "the fingerprint joins subject and html with a single literal NUL. "
        "Editors and encoding round-trips drop it silently, and without it a "
        "subject can be crafted to collide with another message's fingerprint."
    )
