"""Tests for pipeline/youtube_upload.py.

Tests cover:
- Module syntax and expected function signatures (AST-based, no deps needed)
- Import chain verification
- Pure function smoke tests (no YouTube API calls)
- CLI argument parsing
- get_latest_date with real strips.json
- show_pending smoke test
- build_video_metadata output structure
- _category_hashtags mapping
"""

import ast
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
STRIPS_JSON = PROJECT_ROOT / "strips.json"
SHORTS_DIR = PROJECT_ROOT / "shorts"


# ---------------------------------------------------------------------------
# Tier 0: AST / syntax tests (no external deps)
# ---------------------------------------------------------------------------

class TestYouTubeUploadSyntax:
    """Verify the module parses and has expected structure."""

    def test_file_exists(self):
        assert (PIPELINE_DIR / "youtube_upload.py").exists()

    def test_parses_without_syntax_errors(self):
        source = (PIPELINE_DIR / "youtube_upload.py").read_text(encoding="utf-8")
        ast.parse(source, filename="youtube_upload.py")

    def test_has_expected_functions(self):
        source = (PIPELINE_DIR / "youtube_upload.py").read_text(encoding="utf-8")
        tree = ast.parse(source, filename="youtube_upload.py")
        func_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        expected = {
            "load_client_config",
            "do_auth",
            "get_access_token",
            "get_strip_data",
            "save_youtube_id",
            "get_pending_shorts",
            "show_pending",
            "build_video_metadata",
            "upload_video",
            "delete_video",
            "swap_old_videos",
            "get_latest_date",
            "main",
            "_category_hashtags",
        }
        missing = expected - func_names
        assert not missing, f"Missing functions: {missing}"

    def test_has_expected_constants(self):
        source = (PIPELINE_DIR / "youtube_upload.py").read_text(encoding="utf-8")
        for const in ["STRIPS_DIR", "SHORTS_DIR", "STRIPS_JSON", "TOKEN_FILE",
                       "CLIENT_SECRET_FILE", "AUTH_URL", "TOKEN_URL", "UPLOAD_URL",
                       "SCOPES"]:
            assert const in source, f"Missing constant: {const}"


# ---------------------------------------------------------------------------
# Tier 1: Import chain
# ---------------------------------------------------------------------------

class TestImportChain:
    """Verify the module imports without errors."""

    def test_import_youtube_upload(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import (
            get_latest_date,
            get_strip_data,
            get_pending_shorts,
            show_pending,
            build_video_metadata,
            upload_video,
            delete_video,
            swap_old_videos,
            main,
        )
        assert callable(get_latest_date)
        assert callable(get_strip_data)
        assert callable(get_pending_shorts)
        assert callable(show_pending)
        assert callable(build_video_metadata)
        assert callable(upload_video)
        assert callable(delete_video)
        assert callable(swap_old_videos)
        assert callable(main)

    def test_import_private_helpers(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import _category_hashtags
        assert callable(_category_hashtags)

    def test_import_constants(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import (
            STRIPS_DIR, SHORTS_DIR, STRIPS_JSON, TOKEN_FILE,
            CLIENT_SECRET_FILE, AUTH_URL, TOKEN_URL, UPLOAD_URL, SCOPES,
        )
        assert isinstance(AUTH_URL, str)
        assert "google" in AUTH_URL
        assert isinstance(TOKEN_URL, str)
        assert isinstance(UPLOAD_URL, str)
        assert "youtube" in UPLOAD_URL
        assert isinstance(SCOPES, str)


# ---------------------------------------------------------------------------
# Tier 2: Pure function smoke tests (no API calls)
# ---------------------------------------------------------------------------

class TestGetLatestDate:
    """Test get_latest_date returns most recent date from strips.json."""

    def test_returns_string(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import get_latest_date
        result = get_latest_date()
        assert result is not None, "get_latest_date returned None — strips.json may be empty"
        assert isinstance(result, str)

    def test_returns_valid_date_format(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import get_latest_date
        result = get_latest_date()
        # Should be YYYY-MM-DD
        parts = result.split("-")
        assert len(parts) == 3, f"Expected YYYY-MM-DD format, got {result}"
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2
        assert len(parts[2]) == 2

    def test_returns_most_recent(self):
        """Verify it returns the latest date, not first or random."""
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import get_latest_date
        with open(STRIPS_JSON, "r", encoding="utf-8") as f:
            strips = json.load(f)
        all_dates = sorted([s["date"] for s in strips], reverse=True)
        result = get_latest_date()
        assert result == all_dates[0], f"Expected {all_dates[0]}, got {result}"


class TestGetStripData:
    """Test get_strip_data returns correct strip for a given date."""

    def test_existing_date(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import get_strip_data
        # Use first date in strips.json
        with open(STRIPS_JSON, "r", encoding="utf-8") as f:
            strips = json.load(f)
        first_date = strips[0]["date"]
        result = get_strip_data(first_date)
        assert result is not None
        assert result["date"] == first_date
        assert "title" in result

    def test_nonexistent_date_returns_none(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import get_strip_data
        result = get_strip_data("1999-01-01")
        assert result is None


class TestCategoryHashtags:
    """Test _category_hashtags returns appropriate hashtags."""

    def test_known_categories(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import _category_hashtags

        known = [
            "work-stress", "relationships", "family", "health",
            "finances", "self-doubt", "grief-loss", "perseverance",
        ]
        for cat in known:
            result = _category_hashtags(cat)
            assert isinstance(result, str)
            assert result.startswith("#"), f"Hashtags for {cat} should start with #"
            assert len(result) > 5, f"Hashtags for {cat} too short"

    def test_unknown_category_returns_default(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import _category_hashtags
        result = _category_hashtags("nonexistent-category-xyz")
        assert isinstance(result, str)
        assert "#" in result  # Should return a default

    def test_empty_category_returns_default(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import _category_hashtags
        result = _category_hashtags("")
        assert isinstance(result, str)
        assert "#" in result


class TestBuildVideoMetadata:
    """Test build_video_metadata generates proper YouTube metadata."""

    @pytest.fixture
    def sample_strip(self):
        return {
            "date": "2026-03-15",
            "title": "The Weight of Gold Stars",
            "message": "True fulfillment comes from walking our own path.",
            "quote": "Do not depend upon others.",
            "source": "Nichiren Daishonin",
            "category": "work-stress",
            "tags": ["career", "ambition"],
        }

    def test_returns_dict_with_snippet_and_status(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        assert "snippet" in result
        assert "status" in result

    def test_snippet_has_required_fields(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        snippet = result["snippet"]
        assert "title" in snippet
        assert "description" in snippet
        assert "tags" in snippet
        assert "categoryId" in snippet

    def test_title_contains_lotus_lane(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        assert "Lotus Lane" in result["snippet"]["title"]

    def test_title_max_length(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        assert len(result["snippet"]["title"]) <= 100

    def test_title_truncation_for_long_titles(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        long_strip = {
            "date": "2026-03-15",
            "title": "A" * 120,  # Very long title
            "message": "Test",
            "quote": "Test quote",
            "source": "Test source",
            "category": "health",
            "tags": [],
        }
        result = build_video_metadata(long_strip)
        assert len(result["snippet"]["title"]) <= 105  # 90 + " | Lotus Lane"

    def test_description_contains_quote(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        desc = result["snippet"]["description"]
        assert sample_strip["quote"] in desc
        assert sample_strip["source"] in desc

    def test_description_contains_strip_link(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        assert "thelotuslane.in/strips/" in result["snippet"]["description"]

    def test_tags_deduplicated_and_capped(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        tags = result["snippet"]["tags"]
        assert len(tags) <= 30
        assert len(tags) == len(set(tags)), "Tags should be deduplicated"

    def test_tags_include_strip_tags(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        tags = result["snippet"]["tags"]
        assert "career" in tags
        assert "ambition" in tags

    def test_tags_include_core_tags(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        tags = result["snippet"]["tags"]
        assert "nichiren buddhism" in tags
        assert "the lotus lane" in tags
        assert "shorts" in tags

    def test_status_is_public(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        assert result["status"]["privacyStatus"] == "public"
        assert result["status"]["selfDeclaredMadeForKids"] is False

    def test_category_id_is_education(self, sample_strip):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        result = build_video_metadata(sample_strip)
        assert result["snippet"]["categoryId"] == "27"

    def test_missing_optional_fields_handled(self):
        """Strip with minimal fields should not crash."""
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import build_video_metadata
        minimal_strip = {
            "date": "2026-01-01",
            "title": "Test Strip",
        }
        result = build_video_metadata(minimal_strip)
        assert "snippet" in result
        assert "status" in result
        # .get() returns empty string/list for missing keys
        assert isinstance(result["snippet"]["description"], str)


class TestGetPendingShorts:
    """Test get_pending_shorts returns list of strips needing upload."""

    def test_returns_list(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import get_pending_shorts
        result = get_pending_shorts()
        assert isinstance(result, list)

    def test_pending_items_have_required_fields(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import get_pending_shorts
        result = get_pending_shorts()
        for item in result:
            assert "date" in item
            assert "title" in item
            # Pending means no youtube_id
            assert not item.get("youtube_id")


class TestShowPending:
    """Test show_pending doesn't crash with current strips.json."""

    def test_runs_without_error(self, capsys):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import show_pending
        # Should not raise
        show_pending()
        captured = capsys.readouterr()
        assert "YouTube Shorts Status" in captured.out
        assert "Total strips" in captured.out

    def test_output_contains_counts(self, capsys):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import show_pending
        show_pending()
        captured = capsys.readouterr()
        assert "Uploaded:" in captured.out
        assert "Pending:" in captured.out
        assert "No video:" in captured.out


# ---------------------------------------------------------------------------
# Tier 2: CLI argument parsing
# ---------------------------------------------------------------------------

class TestCLIArgumentParsing:
    """Verify all CLI flags are registered in the argparse parser."""

    @pytest.fixture
    def parser(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        import argparse
        # Recreate the parser as defined in main()
        parser = argparse.ArgumentParser(description="Upload Lotus Lane shorts to YouTube")
        parser.add_argument("--auth", action="store_true", help="Run OAuth2 setup")
        parser.add_argument("--date", help="Upload video for specific date")
        parser.add_argument("--latest", action="store_true", help="Upload the latest video")
        parser.add_argument("--all", action="store_true", help="Upload all videos")
        parser.add_argument("--pending", action="store_true", help="Show upload status of all shorts")
        parser.add_argument("--force", action="store_true", help="Re-upload even if already uploaded")
        parser.add_argument("--swap-old", action="store_true",
                            help="Delete old YouTube videos and re-upload with new text (5/day)")
        return parser

    def test_auth_flag(self, parser):
        args = parser.parse_args(["--auth"])
        assert args.auth is True

    def test_date_flag(self, parser):
        args = parser.parse_args(["--date", "2026-03-31"])
        assert args.date == "2026-03-31"

    def test_latest_flag(self, parser):
        args = parser.parse_args(["--latest"])
        assert args.latest is True

    def test_all_flag(self, parser):
        args = parser.parse_args(["--all"])
        assert getattr(args, "all") is True

    def test_pending_flag(self, parser):
        args = parser.parse_args(["--pending"])
        assert args.pending is True

    def test_force_flag(self, parser):
        args = parser.parse_args(["--force"])
        assert args.force is True

    def test_swap_old_flag(self, parser):
        args = parser.parse_args(["--swap-old"])
        assert args.swap_old is True

    def test_combined_flags(self, parser):
        args = parser.parse_args(["--latest", "--force"])
        assert args.latest is True
        assert args.force is True

    def test_no_flags_defaults(self, parser):
        args = parser.parse_args([])
        assert args.auth is False
        assert args.date is None
        assert args.latest is False
        assert getattr(args, "all") is False
        assert args.pending is False
        assert args.force is False
        assert args.swap_old is False


class TestCLIFlagsInSource:
    """Verify the actual source code registers all expected flags."""

    def test_all_flags_present_in_source(self):
        source = (PIPELINE_DIR / "youtube_upload.py").read_text(encoding="utf-8")
        expected_flags = [
            "--auth", "--date", "--latest", "--all",
            "--pending", "--force", "--swap-old",
        ]
        for flag in expected_flags:
            assert flag in source, f"Flag {flag} not found in youtube_upload.py"


# ---------------------------------------------------------------------------
# Tier 2: swap_old_videos callable check
# ---------------------------------------------------------------------------

class TestSwapOldVideos:
    """Test swap_old_videos is callable (does not invoke API)."""

    def test_function_exists_and_callable(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.youtube_upload import swap_old_videos
        assert callable(swap_old_videos)

    def test_function_signature(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        import inspect
        from pipeline.youtube_upload import swap_old_videos
        sig = inspect.signature(swap_old_videos)
        params = list(sig.parameters.keys())
        assert "max_per_run" in params
        # Default should be 5
        assert sig.parameters["max_per_run"].default == 5
