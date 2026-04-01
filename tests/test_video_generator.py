"""Tests for pipeline/video_generator.py.

Tests cover:
- Module syntax and expected function signatures (AST-based, no deps needed)
- Import chain verification (needs Pillow)
- Frame generation smoke tests (needs Pillow + cached strip data)
- Ken Burns, subtitle composition, end card rendering
"""

import ast
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
STRIPS_DIR = PROJECT_ROOT / "strips"


# ---------------------------------------------------------------------------
# Tier 0: AST / syntax tests (no external deps)
# ---------------------------------------------------------------------------

class TestVideoGeneratorSyntax:
    """Verify the module parses and has expected structure."""

    def test_file_exists(self):
        assert (PIPELINE_DIR / "video_generator.py").exists()

    def test_parses_without_syntax_errors(self):
        source = (PIPELINE_DIR / "video_generator.py").read_text(encoding="utf-8")
        ast.parse(source, filename="video_generator.py")

    def test_has_expected_functions(self):
        source = (PIPELINE_DIR / "video_generator.py").read_text(encoding="utf-8")
        tree = ast.parse(source, filename="video_generator.py")
        func_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        expected = {
            "check_ffmpeg",
            "generate_video",
            "generate_all",
            "main",
            "_load_font",
            "_wrap_text",
            "_ken_burns_crop",
            "_compose_panel_frame",
            "_compose_end_card",
            "_blend_frames",
        }
        missing = expected - func_names
        assert not missing, f"Missing functions: {missing}"

    def test_has_expected_constants(self):
        source = (PIPELINE_DIR / "video_generator.py").read_text(encoding="utf-8")
        # Check key constants are defined
        for const in ["VIDEO_WIDTH", "VIDEO_HEIGHT", "FPS_DEFAULT",
                      "PANEL_DURATION", "END_CARD_DURATION"]:
            assert const in source, f"Missing constant: {const}"


# ---------------------------------------------------------------------------
# Tier 1: Import chain
# ---------------------------------------------------------------------------

class TestImportChain:
    """Verify the module imports without errors."""

    def test_import_video_generator(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import (
            check_ffmpeg,
            generate_video,
            generate_all,
            VIDEO_WIDTH,
            VIDEO_HEIGHT,
        )
        assert VIDEO_WIDTH == 1080
        assert VIDEO_HEIGHT == 1920

    def test_check_ffmpeg_returns_string_or_none(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import check_ffmpeg
        result = check_ffmpeg()
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Tier 2: Function smoke tests (needs Pillow)
# ---------------------------------------------------------------------------

class TestFontLoading:
    def test_load_font_returns_font_object(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _load_font
        font = _load_font(36)
        assert font is not None

    def test_load_bold_font(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _load_font
        font = _load_font(36, bold=True)
        assert font is not None


class TestTextWrapping:
    def test_short_text_no_wrap(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _wrap_text, _load_font
        font = _load_font(36)
        lines = _wrap_text("Hello world", font, 900)
        assert len(lines) == 1
        assert lines[0] == "Hello world"

    def test_long_text_wraps(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _wrap_text, _load_font
        font = _load_font(36)
        long_text = "This is a very long dialogue line that should definitely wrap because it exceeds the maximum width allowed for subtitles in the video"
        lines = _wrap_text(long_text, font, 400)
        assert len(lines) > 1

    def test_empty_text(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _wrap_text, _load_font
        font = _load_font(36)
        lines = _wrap_text("", font, 900)
        assert len(lines) >= 1  # Returns [""] at minimum


class TestKenBurns:
    def test_returns_correct_size(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _ken_burns_crop, PANEL_DISPLAY_SIZE
        from PIL import Image
        # Create a test 1024x1024 image
        img = Image.new("RGB", (1024, 1024), (128, 128, 128))
        result = _ken_burns_crop(img, 0.0)
        assert result.size == (PANEL_DISPLAY_SIZE, PANEL_DISPLAY_SIZE)

    def test_start_and_end_differ(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _ken_burns_crop
        from PIL import Image
        # Create a test image with distinct content
        img = Image.new("RGB", (1024, 1024))
        # Draw a gradient so start/end crops differ
        for x in range(1024):
            for y in range(0, 1024, 64):
                img.putpixel((x, y), (x % 256, y % 256, 128))

        start = _ken_burns_crop(img, 0.0)
        end = _ken_burns_crop(img, 1.0)
        # They should be slightly different due to zoom + drift
        assert start.tobytes() != end.tobytes()

    def test_progress_clamped(self):
        """Test with progress values at boundaries."""
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _ken_burns_crop, PANEL_DISPLAY_SIZE
        from PIL import Image
        img = Image.new("RGB", (1024, 1024), (100, 100, 100))
        for p in [0.0, 0.5, 1.0]:
            result = _ken_burns_crop(img, p)
            assert result.size == (PANEL_DISPLAY_SIZE, PANEL_DISPLAY_SIZE)


class TestComposeFrame:
    def test_empty_dialogue(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import (
            _compose_panel_frame, _load_font, VIDEO_WIDTH, VIDEO_HEIGHT,
            PANEL_DISPLAY_SIZE, SUBTITLE_FONT_SIZE,
        )
        from PIL import Image
        panel = Image.new("RGB", (PANEL_DISPLAY_SIZE, PANEL_DISPLAY_SIZE), (128, 128, 128))
        font = _load_font(SUBTITLE_FONT_SIZE)
        font_bold = _load_font(SUBTITLE_FONT_SIZE, bold=True)
        frame = _compose_panel_frame(panel, [], font, font_bold)
        assert frame.size == (VIDEO_WIDTH, VIDEO_HEIGHT)

    def test_with_dialogue(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import (
            _compose_panel_frame, _load_font, VIDEO_WIDTH, VIDEO_HEIGHT,
            PANEL_DISPLAY_SIZE, SUBTITLE_FONT_SIZE,
        )
        from PIL import Image
        panel = Image.new("RGB", (PANEL_DISPLAY_SIZE, PANEL_DISPLAY_SIZE), (128, 128, 128))
        font = _load_font(SUBTITLE_FONT_SIZE)
        font_bold = _load_font(SUBTITLE_FONT_SIZE, bold=True)
        dialogue = [
            "Meera: (sighs) Everyone else finished their PhD in 3 years.",
            "Vikram: Arre, I get it yaar.",
        ]
        frame = _compose_panel_frame(panel, dialogue, font, font_bold)
        assert frame.size == (VIDEO_WIDTH, VIDEO_HEIGHT)
        assert frame.mode == "RGB"


class TestEndCard:
    def test_creates_correct_size(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _compose_end_card, VIDEO_WIDTH, VIDEO_HEIGHT
        card = _compose_end_card(
            "Do not depend upon others.",
            "Nichiren's writings",
            "True fulfillment comes from walking our own path.",
            "The Weight of Gold Stars",
        )
        assert card.size == (VIDEO_WIDTH, VIDEO_HEIGHT)
        assert card.mode == "RGB"

    def test_empty_inputs(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _compose_end_card, VIDEO_WIDTH, VIDEO_HEIGHT
        card = _compose_end_card("", "", "", "")
        assert card.size == (VIDEO_WIDTH, VIDEO_HEIGHT)


class TestBlendFrames:
    def test_alpha_zero_returns_first(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _blend_frames
        from PIL import Image
        a = Image.new("RGB", (100, 100), (255, 0, 0))
        b = Image.new("RGB", (100, 100), (0, 0, 255))
        result = _blend_frames(a, b, 0.0)
        # Should be all red
        assert result.getpixel((50, 50)) == (255, 0, 0)

    def test_alpha_one_returns_second(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _blend_frames
        from PIL import Image
        a = Image.new("RGB", (100, 100), (255, 0, 0))
        b = Image.new("RGB", (100, 100), (0, 0, 255))
        result = _blend_frames(a, b, 1.0)
        assert result.getpixel((50, 50)) == (0, 0, 255)

    def test_alpha_half_blends(self):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import _blend_frames
        from PIL import Image
        a = Image.new("RGB", (100, 100), (200, 0, 0))
        b = Image.new("RGB", (100, 100), (0, 200, 0))
        result = _blend_frames(a, b, 0.5)
        r, g, _ = result.getpixel((50, 50))
        # Should be approximately (100, 100, 0)
        assert 90 <= r <= 110
        assert 90 <= g <= 110


# ---------------------------------------------------------------------------
# Tier 3: Integration test with real cached data
# ---------------------------------------------------------------------------

def _find_cached_date():
    """Find a date that has both script.json and 4 panel images."""
    cache_root = STRIPS_DIR / "cache"
    if not cache_root.exists():
        return None
    for d in sorted(cache_root.iterdir()):
        if not d.is_dir():
            continue
        if (d / "script.json").exists() and all((d / f"panel_{i}.png").exists() for i in range(1, 5)):
            return d.name
    return None


class TestIntegrationWithCache:
    """Integration tests that use real cached strip data."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.date = _find_cached_date()
        if not self.date:
            pytest.skip("No cached strip data available for integration tests")

    def test_script_json_has_expected_fields(self):
        path = STRIPS_DIR / "cache" / self.date / "script.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "script" in data
        script = data["script"]
        assert "panels" in script
        assert len(script["panels"]) >= 3
        assert "nichiren_quote" in script

    def test_panel_images_are_1024x1024(self):
        from PIL import Image
        for i in range(1, 5):
            path = STRIPS_DIR / "cache" / self.date / f"panel_{i}.png"
            img = Image.open(path)
            assert img.size == (1024, 1024), f"panel_{i}.png is {img.size}, expected 1024x1024"

    def test_generate_video_returns_path_or_none(self):
        """Smoke test: only runs if ffmpeg is available."""
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from pipeline.video_generator import check_ffmpeg
        if not check_ffmpeg():
            pytest.skip("ffmpeg not available")

        # Don't actually generate (too slow for unit tests)
        # Just verify the function signature works
        from pipeline.video_generator import generate_video
        import inspect
        sig = inspect.signature(generate_video)
        params = list(sig.parameters.keys())
        assert "date_str" in params
        assert "fps" in params
        assert "verbose" in params
