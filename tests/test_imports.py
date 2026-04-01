"""Baseline smoke tests for lotus-lane project.

Tests syntax validity and config constants for the comic strip pipeline.
Does NOT require external dependencies (httpx, Pillow, dotenv, anthropic).
"""

import ast
import sys
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"


def _get_pipeline_py_files():
    """Return all .py files in pipeline/."""
    return list(PIPELINE_DIR.glob("*.py"))


class TestSyntax:
    """Verify all Python files in pipeline/ parse without syntax errors."""

    def test_all_pipeline_files_parse(self):
        py_files = _get_pipeline_py_files()
        assert len(py_files) > 0, "No .py files found in pipeline/"
        for f in py_files:
            source = f.read_text(encoding="utf-8")
            try:
                ast.parse(source, filename=str(f))
            except SyntaxError as e:
                raise AssertionError(f"Syntax error in {f.name}: {e}")

    def test_config_py_exists(self):
        assert (PIPELINE_DIR / "config.py").exists()

    def test_generate_strip_py_exists(self):
        assert (PIPELINE_DIR / "generate_strip.py").exists()

    def test_quality_check_py_exists(self):
        assert (PIPELINE_DIR / "quality_check.py").exists()


class TestConfigModule:
    """Test pipeline/config.py imports and has expected constants."""

    def test_config_imports_cleanly(self):
        """config.py only uses stdlib (os, pathlib) so it should import cleanly."""
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.config import (
            CHARACTERS,
            CHALLENGE_TOPICS,
            ART_STYLE,
            PANELS_PER_STRIP,
            STRIP_WIDTH,
            PANEL_HEIGHT,
            PANEL_GAP,
            PUBLISH_DAYS,
            STRIPS_DIR,
            STRIPS_JSON,
            CHARACTERS_DIR,
        )

    def test_characters_dict_structure(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.config import CHARACTERS

        assert isinstance(CHARACTERS, dict), "CHARACTERS should be a dict"
        assert len(CHARACTERS) >= 4, f"Expected at least 4 characters, got {len(CHARACTERS)}"

        expected_keys = {"arjun", "meera", "sudha", "vikram"}
        assert expected_keys.issubset(
            set(CHARACTERS.keys())
        ), f"Missing characters: {expected_keys - set(CHARACTERS.keys())}"

        # Each character should have required fields
        for key, char in CHARACTERS.items():
            for field in ("name", "age", "role", "appearance", "personality", "color"):
                assert field in char, f"Character '{key}' missing field '{field}'"

    def test_challenge_topics_structure(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.config import CHALLENGE_TOPICS

        assert isinstance(CHALLENGE_TOPICS, dict)
        assert len(CHALLENGE_TOPICS) >= 6, f"Expected at least 6 categories, got {len(CHALLENGE_TOPICS)}"

        expected_categories = {
            "work-stress", "relationships", "family", "health",
            "finances", "self-doubt",
        }
        missing = expected_categories - set(CHALLENGE_TOPICS.keys())
        assert not missing, f"Missing challenge categories: {missing}"

        # Each category should have a non-empty list of topics
        for cat, topics in CHALLENGE_TOPICS.items():
            assert isinstance(topics, list), f"Category '{cat}' should map to a list"
            assert len(topics) > 0, f"Category '{cat}' has no topics"

    def test_art_style_is_nonempty_string(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.config import ART_STYLE

        assert isinstance(ART_STYLE, str)
        assert len(ART_STYLE) > 50, "ART_STYLE should be a substantial prompt string"

    def test_panel_dimensions_reasonable(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.config import PANELS_PER_STRIP, STRIP_WIDTH, PANEL_HEIGHT

        assert PANELS_PER_STRIP >= 3
        assert STRIP_WIDTH >= 512
        assert PANEL_HEIGHT >= 400

    def test_publish_days_valid(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.config import PUBLISH_DAYS

        assert isinstance(PUBLISH_DAYS, list)
        assert all(0 <= d <= 6 for d in PUBLISH_DAYS), "Publish days must be 0-6"


class TestGenerateStripModule:
    """Test generate_strip.py structure (can't import due to external deps)."""

    def test_has_expected_functions(self):
        source = (PIPELINE_DIR / "generate_strip.py").read_text(encoding="utf-8")
        tree = ast.parse(source, filename="generate_strip.py")
        func_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        expected = {
            "pick_topic",
            "pick_characters",
            "generate_script",
            "generate_panel_image",
            "assemble_strip",
            "save_strip",
            "generate",
            "main",
        }
        missing = expected - func_names
        assert not missing, f"Missing functions in generate_strip.py: {missing}"


class TestQualityCheckModule:
    """Test quality_check.py structure (can't import due to Pillow/httpx)."""

    def test_has_expected_functions(self):
        source = (PIPELINE_DIR / "quality_check.py").read_text(encoding="utf-8")
        tree = ast.parse(source, filename="quality_check.py")
        func_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        expected = {
            "check_resolution",
            "check_blank_or_dark",
            "check_low_contrast",
            "check_corruption",
            "run_pillow_checks",
            "check_text_in_image",
            "run_full_qc",
        }
        missing = expected - func_names
        assert not missing, f"Missing functions in quality_check.py: {missing}"
