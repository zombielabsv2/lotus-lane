"""The daimoku send must prefer the Max broker and must never depend on it.

Rahul decided the cutover on 2026-08-27 (inbox thread 1a04249ad78f8667). This
job called api.anthropic.com once per subscriber on the SHARED prepaid key — the
same key several unrelated live automations draw on — so a daily send was a
daily drip against a balance that, when it runs dry, takes those automations
with it.

The rule the tests below pin is the one that makes the cutover safe: the broker
is an OPTIMISATION, not a dependency. `maxgen_client.generate()` returns None
rather than raising on every failure it knows about (disabled, no creds, drain
timeout, failed generation), and the metered path must still be sitting there
when it does. A cutover that removed the fallback would trade recurring spend
for a single point of failure on somebody's morning email.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import generate_email  # noqa: E402

_MODEL_JSON = json.dumps({
    "subject": "A moment for you",
    "opening": "o", "quote": "q", "quote_source": "s",
    "interpretation": "i", "practice": "p", "closing": "c",
})
_SUB = {"name": "Test", "email": "t@example.com", "situation_text": ""}


def test_broker_result_is_used_and_the_api_is_never_called():
    with patch("maxgen_client.generate", return_value=_MODEL_JSON), \
         patch("httpx.post") as api, \
         patch("pipeline.generate_email.build_html_email", return_value="<p>x</p>"):
        out = generate_email.generate_email_content(_SUB, "career", [])
    assert out["subject"] == "A moment for you"
    assert api.call_count == 0, "broker served it; the metered API must not be hit"


def test_falls_back_to_the_api_when_the_broker_declines():
    """None is the broker's whole failure vocabulary — disabled, no creds,
    timed out, generation failed. Every one of them must land here."""
    class _Resp:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"content": [{"text": _MODEL_JSON}],
                    "usage": {"input_tokens": 1, "output_tokens": 1}}

    with patch("maxgen_client.generate", return_value=None), \
         patch("httpx.post", return_value=_Resp()) as api, \
         patch("pipeline.generate_email.build_html_email", return_value="<p>x</p>"):
        out = generate_email.generate_email_content(_SUB, "career", [])
    assert out["subject"] == "A moment for you"
    assert api.call_count == 1, "broker declined; the email must still go out"


def test_a_broker_that_raises_does_not_stop_the_send():
    """The client contract says it never raises, but this call site must not be
    the thing that trusts that. An import error or a transport bug inside the
    client is not a reason somebody misses their morning email."""
    class _Resp:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"content": [{"text": _MODEL_JSON}],
                    "usage": {"input_tokens": 1, "output_tokens": 1}}

    with patch("maxgen_client.generate", side_effect=RuntimeError("boom")), \
         patch("httpx.post", return_value=_Resp()) as api, \
         patch("pipeline.generate_email.build_html_email", return_value="<p>x</p>"):
        out = generate_email.generate_email_content(_SUB, "career", [])
    assert out["subject"] == "A moment for you"
    assert api.call_count == 1


def test_both_paths_share_one_normaliser():
    """The parse/normalise tail is shared so a fix cannot reach one path and
    miss the other. A model that omits quote_source must degrade the same way
    whichever path served it."""
    partial = json.dumps({"opening": "o"})
    with patch("pipeline.generate_email.build_html_email", return_value="<p>x</p>"):
        out = generate_email._finish_email_content(partial, "Test", _SUB)
    assert out["subject"] == "A moment for you, Test"
    assert out["source"] == ""


def test_the_metered_key_is_still_wired_in_ci():
    """Removing ANTHROPIC_API_KEY from the workflow was floated as "the real
    win". It is not: it deletes the fallback these tests exist to protect. If
    someone drops it, this fails and says why."""
    wf = (Path(__file__).resolve().parents[1]
          / ".github" / "workflows" / "daily-content.yml").read_text(encoding="utf-8")
    assert "MAXGEN_ENABLED" in wf, "broker never turned on in CI"
    assert "ANTHROPIC_API_KEY" in wf, (
        "the metered fallback was removed — the broker is an optimisation, "
        "not a dependency"
    )
