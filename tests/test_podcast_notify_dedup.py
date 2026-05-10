"""Tests for podcast-notification idempotency (lotus_podcast_notifications)."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline import notify


def test_imports_dedup_helpers():
    assert callable(notify._already_notified_podcast)
    assert callable(notify._mark_podcast_notified)
    assert notify.PODCAST_NOTIF_TABLE == "lotus_podcast_notifications"


def test_already_notified_empty_slug_fails_closed():
    assert notify._already_notified_podcast("") is True
    assert notify._already_notified_podcast(None) is True


def test_already_notified_no_supabase_fails_closed(monkeypatch):
    monkeypatch.setattr(notify, "_supabase_creds", lambda: (None, None))
    assert notify._already_notified_podcast("any-slug") is True


def test_already_notified_returns_false_for_unseen_slug(monkeypatch):
    monkeypatch.setattr(notify, "_supabase_creds", lambda: ("https://x", "k"))
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = []
    with patch.object(notify.httpx, "get", return_value=fake_resp):
        assert notify._already_notified_podcast("brand-new") is False


def test_already_notified_returns_true_for_marked_slug(monkeypatch):
    monkeypatch.setattr(notify, "_supabase_creds", lambda: ("https://x", "k"))
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = [{"notified_at": "2026-05-11T00:00:00Z"}]
    with patch.object(notify.httpx, "get", return_value=fake_resp):
        assert notify._already_notified_podcast("burnout-recovery") is True


def test_already_notified_supabase_error_fails_closed(monkeypatch):
    monkeypatch.setattr(notify, "_supabase_creds", lambda: ("https://x", "k"))
    fake_resp = MagicMock(status_code=500, text="boom")
    with patch.object(notify.httpx, "get", return_value=fake_resp):
        assert notify._already_notified_podcast("anything") is True


def test_send_podcast_notification_skips_when_already_notified(monkeypatch, capsys):
    monkeypatch.setattr(notify, "RESEND_API_KEY", "fake")
    monkeypatch.setattr(notify, "NOTIFY_EMAIL", "rahul@test")
    monkeypatch.setattr(notify, "_already_notified_podcast", lambda slug: True)
    sent = {"called": False}
    monkeypatch.setattr(notify, "_send_via_resend", lambda *a, **k: sent.update(called=True) or True)
    notify.send_podcast_notification({"slug": "burnout-recovery", "title": "x", "episode_number": 1})
    assert sent["called"] is False
    out = capsys.readouterr().out
    assert "already notified" in out


def test_send_podcast_notification_marks_after_send(monkeypatch):
    monkeypatch.setattr(notify, "RESEND_API_KEY", "fake")
    monkeypatch.setattr(notify, "NOTIFY_EMAIL", "rahul@test")
    monkeypatch.setattr(notify, "_already_notified_podcast", lambda slug: False)
    monkeypatch.setattr(notify, "_send_via_resend", lambda *a, **k: True)
    marked = {"slug": None}
    monkeypatch.setattr(notify, "_mark_podcast_notified", lambda slug: marked.update(slug=slug))
    notify.send_podcast_notification({"slug": "new-ep", "title": "t", "episode_number": 99, "duration_seconds": 600, "audio_url": "u"})
    assert marked["slug"] == "new-ep"


def test_send_podcast_notification_does_not_mark_on_send_failure(monkeypatch):
    monkeypatch.setattr(notify, "RESEND_API_KEY", "fake")
    monkeypatch.setattr(notify, "NOTIFY_EMAIL", "rahul@test")
    monkeypatch.setattr(notify, "_already_notified_podcast", lambda slug: False)
    monkeypatch.setattr(notify, "_send_via_resend", lambda *a, **k: False)
    marked = {"called": False}
    monkeypatch.setattr(notify, "_mark_podcast_notified", lambda slug: marked.update(called=True))
    notify.send_podcast_notification({"slug": "fails", "title": "t", "episode_number": 99, "duration_seconds": 600, "audio_url": "u"})
    assert marked["called"] is False
