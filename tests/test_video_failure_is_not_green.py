"""A Short that was never rendered must fail the step that renders it.

ElevenLabs began returning 401 payment_required on 2026-08-28 ("Your
subscription has a failed or incomplete payment"). `generate_video` correctly
gave up and returned None each time — and `main()` ignored the return value, so
the process exited 0, the workflow step went green, and four consecutive strips
(28 Aug, 31 Aug, 2 Sep, 4 Sep) shipped with no video. It surfaced ten days later
in a weekly digest counting the holes.

The alerting was already built and correct: the step is continue-on-error with
id `video`, and "Report failure summary" emails when
steps.video.outcome == 'failure'. It could simply never be true.

Two things are pinned here, because either one alone lets the silence back:
the exit code, and the workflow wiring that turns it into mail.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GEN = ROOT / "pipeline" / "video_generator.py"
WF = ROOT / ".github" / "workflows" / "generate-strip.yml"


def test_main_exits_non_zero_when_no_video_was_produced():
    src = GEN.read_text(encoding="utf-8")
    tail = src[src.index("def main("):]
    call = re.search(r"if generate_video\([^)]*\) is None:\s*(?:#.*\n\s*)*", tail)
    assert call, (
        "main() must check generate_video's return value. It returns None on "
        "every abort path, and ignoring that is what made a dead renderer look "
        "like a healthy one."
    )
    after = tail[call.end():call.end() + 800]
    assert "sys.exit(1)" in after, (
        "main() must exit non-zero when no video was produced — the workflow "
        "step is continue-on-error, so a zero exit is reported as success and "
        "no failure mail is sent."
    )


def test_the_video_step_is_still_wired_to_the_failure_mail():
    """The exit code only helps because something reads it."""
    wf = WF.read_text(encoding="utf-8")
    assert "id: video" in wf, "the video step lost its id; nothing can read its outcome"
    assert "steps.video.outcome" in wf, (
        "the failure summary no longer reads the video step's outcome, so a "
        "non-zero exit would go nowhere"
    )


def test_the_step_stays_continue_on_error():
    """Deliberate: a missing Short must not block the strip, the page, the
    email or the GCS sync. The fix is to make the failure LOUD, never to make
    it fatal."""
    wf = WF.read_text(encoding="utf-8")
    block = wf[wf.index("- name: Generate YouTube Short video"):]
    block = block[:block.index("- name: Generate 15-second hook reel")]
    assert "continue-on-error: true" in block
