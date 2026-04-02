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
    """All 8 subscriber challenge categories have keywords."""
    from pipeline.generate_email import CHALLENGE_KEYWORDS

    expected = {"career", "health", "relationships", "family", "finances", "self-doubt", "grief", "perseverance"}
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
