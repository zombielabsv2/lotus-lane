"""The Shorts rail is retired, and a render that produces nothing still fails.

Two eras in one file, both worth pinning.

WHAT HAPPENED. ElevenLabs began returning 401 payment_required on 2026-08-28.
`generate_video` correctly gave up and returned None each time, and `main()`
ignored the return value, so the process exited 0, the workflow step went green,
and four consecutive strips (28 Aug, 31 Aug, 2 Sep, 4 Sep) shipped with no
video. It surfaced ten days later in a weekly digest counting the holes.

WHAT RAHUL DECIDED, 2026-09-08: drop the rail rather than renew. 19 subscribers,
and the best video of the month had 6 views, against a subscription payable
whether or not anyone watches. The Short, the YouTube upload, the retry job and
the weekly backfill are gone.

So the tests split. The exit-code invariant still holds, because
video_generator.py is still here and still runnable by hand — unwired, not
deleted, so the decision stays reversible. And a new test pins the retirement
itself, because the failure mode now is somebody re-adding a step that quietly
needs a subscription nobody is paying.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
GEN = ROOT / "pipeline" / "video_generator.py"
STRIP_WF = ROOT / ".github" / "workflows" / "generate-strip.yml"


# ---------------------------------------------------------------------------
# Still true: a render that produced nothing must not exit 0.
# ---------------------------------------------------------------------------

def test_main_exits_non_zero_when_no_video_was_produced():
    src = GEN.read_text(encoding="utf-8")
    tail = src[src.index("def main("):]
    call = re.search(r"if generate_video\([^)]*\) is None:\s*(?:#.*\n\s*)*", tail)
    assert call, (
        "main() must check generate_video's return value. It returns None on "
        "every abort path, and ignoring that is what made a dead renderer look "
        "like a healthy one."
    )
    assert "sys.exit(1)" in tail[call.end():call.end() + 800]


def test_the_all_branch_also_exits_non_zero():
    """The backfill path had the same bug, and it was the path that mattered
    most when TTS was down."""
    src = GEN.read_text(encoding="utf-8")
    tail = src[src.index("def main("):]
    call = re.search(r"if generate_all\([^)]*\):", tail)
    assert call, "main() must check what generate_all returns"
    assert "sys.exit(1)" in tail[call.end():call.end() + 500]
    body = src[src.index("def generate_all("):src.index("def main(")]
    assert 'return results["failed"]' in body, (
        "generate_all must return its failures, or main() has nothing to check"
    )


# ---------------------------------------------------------------------------
# New: the rail is retired and does not come back by accident.
# ---------------------------------------------------------------------------

def test_the_shorts_rail_stays_retired():
    """Re-adding either step brings back a hard dependency on a subscription
    nobody is paying, and it fails the way the original did: quietly, with the
    run still green, because both steps were continue-on-error.

    If the rail is ever revived deliberately, delete this test in the same
    commit that renews the subscription — not before.
    """
    wf = STRIP_WF.read_text(encoding="utf-8")
    assert "Generate YouTube Short video" not in wf, (
        "the Short step is back; Rahul retired it on 2026-09-08 rather than "
        "renew ElevenLabs"
    )
    assert "Upload to YouTube" not in wf, "the YouTube upload step is back"
    assert "ELEVENLABS_API_KEY" not in wf, (
        "generate-strip no longer needs a TTS key; a step asking for one is a "
        "step that will fail on a dead subscription"
    )


def test_the_hook_reel_survived_the_cut():
    """It renders straight from the panels and never called ElevenLabs, so it
    was never part of what broke. Cutting it with the rail would have been
    collateral damage."""
    wf = STRIP_WF.read_text(encoding="utf-8")
    assert "Generate 15-second hook reel" in wf
    assert "id: hook_reel" in wf


def test_the_failure_summary_names_only_steps_that_exist():
    """It read steps.video.outcome and steps.youtube.outcome. A summary reading
    a step that is gone resolves to empty and silently never fires — which is
    the same class of bug as the exit code it was built to catch."""
    wf = STRIP_WF.read_text(encoding="utf-8")
    referenced = set(re.findall(r"steps\.([a-z_]+)\.outcome", wf))
    declared = set(re.findall(r"^\s+id: ([a-z_]+)\s*$", wf, re.MULTILINE))
    missing = referenced - declared
    assert not missing, f"failure summary reads step ids that do not exist: {sorted(missing)}"
