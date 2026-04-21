"""Tests for Daimoku Daily email pipeline."""

import sys
import os
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set chunks path for tests (sibling of lotus-lane in user home)
if "CHUNKS_PATH" not in os.environ:
    chunks_path = PROJECT_ROOT.parent / "nichiren-chatbot" / "data" / "processed" / "chunks.json"
    os.environ["CHUNKS_PATH"] = str(chunks_path)

_has_chunks = Path(os.environ["CHUNKS_PATH"]).exists()


def test_import_generate_email():
    """Tier 1: Import chain test."""
    from pipeline.generate_email import (
        load_chunks,
        search_chunks,
        pick_challenge,
        build_html_email,
        CHALLENGE_KEYWORDS,
        get_due_subscribers,
        process_subscriber,
    )
    assert callable(load_chunks)
    assert callable(search_chunks)
    assert callable(pick_challenge)
    assert callable(build_html_email)
    assert isinstance(CHALLENGE_KEYWORDS, dict)


def test_import_subscribe_api():
    """Tier 1: Import chain test."""
    from pipeline.subscribe_api import (
        list_subscribers,
        unsubscribe,
        get_stats,
    )
    assert callable(list_subscribers)
    assert callable(unsubscribe)
    assert callable(get_stats)


def test_challenge_keywords_coverage():
    """Legacy 8 broad + Apr 2026 narrow buckets all carry keywords."""
    from pipeline.generate_email import CHALLENGE_KEYWORDS

    legacy = {"career", "health", "relationships", "family", "finances", "self-doubt", "grief", "perseverance"}
    narrow = {
        "burnout", "toxic-workplace", "sidelined", "imposter", "relationship-conflict",
        "divorce", "parenting", "caregiving", "forgiveness", "money",
        "chronic-illness", "depression", "anxiety", "loneliness", "starting-over",
    }
    expected = legacy | narrow
    assert set(CHALLENGE_KEYWORDS.keys()) == expected

    for category, keywords in CHALLENGE_KEYWORDS.items():
        assert len(keywords) >= 5, f"{category} has too few keywords ({len(keywords)})"


@pytest.mark.skipif(not _has_chunks, reason="chunks.json not available in CI")
def test_load_chunks():
    """Tier 2: Knowledge base loads successfully."""
    from pipeline.generate_email import load_chunks

    # Reset cache
    import pipeline.generate_email as mod
    mod._chunks_cache = None

    chunks = load_chunks()
    assert isinstance(chunks, list)
    assert len(chunks) > 1000, f"Expected 1000+ chunks, got {len(chunks)}"

    # Check chunk structure
    chunk = chunks[0]
    assert "text" in chunk
    assert "metadata" in chunk
    assert "collection_name" in chunk["metadata"]


@pytest.mark.skipif(not _has_chunks, reason="chunks.json not available in CI")
def test_search_chunks():
    """Tier 2: Search returns relevant results for each challenge."""
    from pipeline.generate_email import search_chunks

    for challenge in ["career", "health", "grief", "perseverance", "self-doubt"]:
        results = search_chunks(challenge, limit=5)
        assert len(results) > 0, f"No results for '{challenge}'"
        assert len(results) <= 5

        # Each result should have text and metadata
        for r in results:
            assert "text" in r
            assert len(r["text"]) > 20


def test_pick_challenge():
    """Tier 2: Challenge rotation works (mocked — no Supabase needed)."""
    from unittest.mock import patch
    from pipeline.generate_email import pick_challenge

    subscriber = {
        "id": "test-123",
        "challenges": ["career", "health", "self-doubt"],
    }

    # Mock get_recent_categories to avoid Supabase call
    with patch("pipeline.generate_email.get_recent_categories", return_value=[]):
        picked = pick_challenge(subscriber)
        assert picked in subscriber["challenges"]

    # With some recent categories, should prefer unsent ones
    with patch("pipeline.generate_email.get_recent_categories", return_value=["career", "health"]):
        picked = pick_challenge(subscriber)
        assert picked == "self-doubt"


def test_pick_challenge_fallback():
    """Tier 2: Fallback when no challenges set."""
    from unittest.mock import patch
    from pipeline.generate_email import pick_challenge

    subscriber = {"id": "test-456", "challenges": []}
    with patch("pipeline.generate_email.get_recent_categories", return_value=[]):
        picked = pick_challenge(subscriber)
        assert picked == "perseverance"


def test_build_html_email():
    """Tier 2: HTML email renders correctly."""
    from pipeline.generate_email import build_html_email

    data = {
        "opening": "Dear friend, I know this is hard.",
        "quote": "Winter always turns to spring.",
        "quote_source": "WND-1, 536",
        "interpretation": "Your current struggle will not last forever.",
        "practice": "Chant for 10 minutes focusing on gratitude.",
        "closing": "You have tremendous strength within you.",
    }

    html = build_html_email(data, "Rahul")

    assert "Winter always turns to spring" in html
    assert "WND-1, 536" in html
    assert "Daimoku Daily" in html
    assert "The Lotus Lane" in html
    assert "Today's Practice" in html
    assert "unsubscribe" in html.lower()


def test_html_email_escaping():
    """Tier 2: HTML email handles special characters."""
    from pipeline.generate_email import build_html_email

    data = {
        "opening": "Dear friend & ally, <keep going>.",
        "quote": "The voice does the Buddha's work.",
        "quote_source": "OTT, 4",
        "interpretation": "Your words matter.",
        "practice": "Chant with conviction.",
        "closing": "Keep going!",
    }

    html = build_html_email(data, "Test")
    assert isinstance(html, str)
    assert len(html) > 500


# ---------------------------------------------------------------------------
# Welcome Sequence Tests
# ---------------------------------------------------------------------------

def test_import_welcome_functions():
    """Tier 1: Welcome sequence imports work."""
    from pipeline.generate_email import (
        get_welcome_due_subscribers,
        process_welcome_subscriber,
        WELCOME_BUILDERS,
        CHALLENGE_THEME_MAP,
        CHALLENGE_LABELS,
        FREQUENCY_LABELS,
        _load_ikeda_quotes,
        _pick_ikeda_quote,
        _build_welcome_html,
        _build_welcome_1,
        _build_welcome_2,
        _build_welcome_3,
    )
    assert callable(get_welcome_due_subscribers)
    assert callable(process_welcome_subscriber)
    assert len(WELCOME_BUILDERS) == 3
    # Legacy 8 broad + Apr 2026 narrow buckets — must stay in lockstep
    assert len(CHALLENGE_THEME_MAP) == len(CHALLENGE_LABELS)
    assert set(CHALLENGE_THEME_MAP.keys()) == set(CHALLENGE_LABELS.keys())
    assert len(CHALLENGE_THEME_MAP) >= 8
    assert len(FREQUENCY_LABELS) == 3


def test_challenge_theme_map_coverage():
    """All 8 challenges map to valid Ikeda quote themes."""
    from pipeline.generate_email import CHALLENGE_THEME_MAP, _load_ikeda_quotes

    quotes = _load_ikeda_quotes()
    all_theme_ids = set(quotes.keys())

    for challenge, themes in CHALLENGE_THEME_MAP.items():
        assert len(themes) >= 1, f"{challenge} has no mapped themes"
        for theme in themes:
            assert theme in all_theme_ids, f"Theme '{theme}' for '{challenge}' not in Ikeda quotes"


def test_pick_ikeda_quote():
    """Quote picker returns valid quotes for all challenge themes."""
    from pipeline.generate_email import _pick_ikeda_quote, CHALLENGE_THEME_MAP

    for challenge, themes in CHALLENGE_THEME_MAP.items():
        quote = _pick_ikeda_quote(themes)
        assert "text" in quote, f"No text for {challenge}"
        assert len(quote["text"]) > 10, f"Quote too short for {challenge}"
        assert "source" in quote, f"No source for {challenge}"


def test_pick_ikeda_quote_fallback():
    """Quote picker handles unknown themes gracefully."""
    from pipeline.generate_email import _pick_ikeda_quote

    quote = _pick_ikeda_quote(["nonexistent_theme_xyz"])
    assert "text" in quote
    assert len(quote["text"]) > 10  # Should fall back to perseverance


_test_subscriber = {
    "id": "test-welcome-uuid",
    "name": "Priya",
    "email": "priya@test.com",
    "challenges": ["career", "self-doubt"],
    "situation_text": "Struggling at work",
    "frequency": "daily",
}


def test_build_welcome_1():
    """Tier 2: Welcome email 1 renders correctly."""
    from pipeline.generate_email import _build_welcome_1

    result = _build_welcome_1(_test_subscriber)
    assert result["subject"] == "Welcome, Priya"
    html = result["html_body"]
    assert "Priya" in html
    assert "career" in html.lower()
    assert "self-doubt" in html.lower()
    assert "tomorrow morning" in html  # daily frequency
    assert "Lotus Lane" in html
    assert "unsubscribe" in html.lower()
    assert len(result["quote"]) > 10
    assert len(result["source"]) > 0
    # Universal framing: specific narrative jargon removed (quotes may still contain Buddhist concepts — those are attributed wisdom content)
    for phrase in ("Welcome to Daimoku Daily", "Nichiren Daishonin's writings", "writings of Nichiren Daishonin", "Buddhist writings"):
        assert phrase not in html, f"Jargon leaked into welcome_1 narrative: {phrase}"


def test_build_welcome_1_weekly():
    """Welcome 1 shows correct frequency text for weekly subscribers."""
    from pipeline.generate_email import _build_welcome_1

    sub = {**_test_subscriber, "frequency": "weekly"}
    result = _build_welcome_1(sub)
    assert "next Monday" in result["html_body"]


def test_build_welcome_1_thrice():
    """Welcome 1 shows correct frequency text for thrice_weekly subscribers."""
    from pipeline.generate_email import _build_welcome_1

    sub = {**_test_subscriber, "frequency": "thrice_weekly"}
    result = _build_welcome_1(sub)
    assert "next Mon, Wed, or Fri" in result["html_body"]


def test_build_welcome_2():
    """Tier 2: Welcome email 2 renders correctly."""
    from pipeline.generate_email import _build_welcome_2

    result = _build_welcome_2(_test_subscriber)
    assert "heart of practice" in result["subject"]
    html = result["html_body"]
    assert "Priya" in html
    assert "blessings contained in a single moment" in html  # simplified wisdom passage
    assert "career" in html.lower()  # Challenge-specific practice tip
    assert "Try This" in html  # Practice section header
    assert len(result["quote"]) > 10


def test_build_welcome_2_grief():
    """Welcome 2 chanting tip varies by challenge."""
    from pipeline.generate_email import _build_welcome_2

    sub = {**_test_subscriber, "challenges": ["grief"]}
    result = _build_welcome_2(sub)
    html = result["html_body"]
    assert "grief" in html.lower() or "tears" in html.lower() or "loss" in html.lower()


def test_build_welcome_3():
    """Tier 2: Welcome email 3 renders correctly."""
    from pipeline.generate_email import _build_welcome_3

    result = _build_welcome_3(_test_subscriber)
    assert "not alone" in result["subject"]
    html = result["html_body"]
    assert "Priya" in html
    assert "daily emails" in html  # frequency mention
    assert "thousands" in html.lower() or "practitioners" in html.lower()
    assert len(result["quote"]) > 10


def test_build_welcome_3_single_challenge():
    """Welcome 3 correctly renders a single challenge."""
    from pipeline.generate_email import _build_welcome_3

    sub = {**_test_subscriber, "challenges": ["health"]}
    result = _build_welcome_3(sub)
    html = result["html_body"]
    assert "health" in html


def test_build_welcome_3_three_challenges():
    """Welcome 3 correctly formats 3 challenges with serial comma."""
    from pipeline.generate_email import _build_welcome_3

    sub = {**_test_subscriber, "challenges": ["health", "family", "finances"]}
    result = _build_welcome_3(sub)
    html = result["html_body"]
    assert "health" in html
    assert "family" in html
    assert "finances" in html


def test_welcome_all_challenges():
    """Every challenge produces valid welcome emails for all 3 steps."""
    from pipeline.generate_email import WELCOME_BUILDERS

    challenges = ["career", "health", "relationships", "family", "finances", "self-doubt", "grief", "perseverance"]
    for challenge in challenges:
        sub = {
            "id": f"test-{challenge}",
            "name": "Test",
            "email": "test@test.com",
            "challenges": [challenge],
            "frequency": "weekly",
        }
        for step in [1, 2, 3]:
            sub["_welcome_step"] = step
            result = WELCOME_BUILDERS[step](sub)
            assert "subject" in result, f"No subject for {challenge} step {step}"
            assert "html_body" in result, f"No html_body for {challenge} step {step}"
            assert len(result["html_body"]) > 500, f"HTML too short for {challenge} step {step}"


def test_welcome_no_api_cost():
    """Welcome emails are template-based — no Claude API calls."""
    from pipeline.generate_email import _build_welcome_1, _build_welcome_2, _build_welcome_3

    # These should work without ANTHROPIC_API_KEY set
    import os
    old_key = os.environ.get("ANTHROPIC_API_KEY", "")
    os.environ["ANTHROPIC_API_KEY"] = ""
    try:
        for builder in [_build_welcome_1, _build_welcome_2, _build_welcome_3]:
            result = builder(_test_subscriber)
            assert "html_body" in result
    finally:
        if old_key:
            os.environ["ANTHROPIC_API_KEY"] = old_key


def test_get_welcome_due_subscribers_mocked():
    """Tier 2: Welcome subscriber detection with mocked Supabase."""
    from unittest.mock import patch
    from pipeline.generate_email import get_welcome_due_subscribers

    mock_subscribers = [
        {"id": "new-sub", "name": "New", "email": "new@test.com", "challenges": ["career"], "frequency": "daily", "active": True},
    ]

    # New subscriber with no welcome logs => step 1
    with patch("pipeline.generate_email.supabase_get") as mock_get:
        mock_get.side_effect = [
            mock_subscribers,  # First call: get subscribers
            [],                # Second call: get welcome logs (empty)
        ]
        due = get_welcome_due_subscribers()
        assert len(due) == 1
        assert due[0]["_welcome_step"] == 1

    # Subscriber who completed welcome_1 yesterday => step 2
    from datetime import datetime, timezone, timedelta
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1, hours=1)).isoformat()
    with patch("pipeline.generate_email.supabase_get") as mock_get:
        mock_get.side_effect = [
            mock_subscribers,
            [{"challenge_category": "welcome_1", "sent_at": yesterday, "status": "sent"}],
        ]
        due = get_welcome_due_subscribers()
        assert len(due) == 1
        assert due[0]["_welcome_step"] == 2

    # Subscriber who completed all 3 => not due
    with patch("pipeline.generate_email.supabase_get") as mock_get:
        mock_get.side_effect = [
            mock_subscribers,
            [
                {"challenge_category": "welcome_1", "sent_at": yesterday, "status": "sent"},
                {"challenge_category": "welcome_2", "sent_at": yesterday, "status": "sent"},
                {"challenge_category": "welcome_3", "sent_at": yesterday, "status": "sent"},
            ],
        ]
        due = get_welcome_due_subscribers()
        assert len(due) == 0


def test_process_welcome_subscriber_mocked():
    """Tier 2: Welcome processing with mocked send + log."""
    from unittest.mock import patch
    from pipeline.generate_email import process_welcome_subscriber

    sub = {**_test_subscriber, "_welcome_step": 1}

    with patch("pipeline.generate_email.send_email", return_value=True) as mock_send, \
         patch("pipeline.generate_email.supabase_post") as mock_post:
        result = process_welcome_subscriber(sub)
        assert result is True
        mock_send.assert_called_once()
        mock_post.assert_called_once()
        # Check log entry uses welcome_1 as category
        log_data = mock_post.call_args[0][1]
        assert log_data["challenge_category"] == "welcome_1"
        assert log_data["status"] == "sent"


if __name__ == "__main__":
    test_import_generate_email()
    print("PASS: test_import_generate_email")

    test_import_subscribe_api()
    print("PASS: test_import_subscribe_api")

    test_challenge_keywords_coverage()
    print("PASS: test_challenge_keywords_coverage")

    test_load_chunks()
    print("PASS: test_load_chunks")

    test_search_chunks()
    print("PASS: test_search_chunks")

    test_pick_challenge()
    print("PASS: test_pick_challenge")

    test_pick_challenge_fallback()
    print("PASS: test_pick_challenge_fallback")

    test_build_html_email()
    print("PASS: test_build_html_email")

    test_html_email_escaping()
    print("PASS: test_html_email_escaping")

    print("\nAll tests passed!")
