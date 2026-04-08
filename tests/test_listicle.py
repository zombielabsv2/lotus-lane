"""Tests for the listicle infographic generator.

Tests data helpers, image generation, SEO page generation, and file structure.
Does NOT call Claude API — uses mock data for all tests.
"""

import ast
import json
import shutil
import sys
from pathlib import Path

import pytest

# Playwright requires browser binaries — skip dependent tests when not installed
_has_playwright = True
try:
    import playwright  # noqa: F401
except ModuleNotFoundError:
    _has_playwright = False

needs_playwright = pytest.mark.skipif(
    not _has_playwright, reason="playwright not installed (optional dependency)"
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "pipeline"

# Ensure project root is on path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_LISTICLE = {
    "title": "5 Quotes on Courage for When Fear Holds You Back",
    "theme": "courage",
    "theme_name": "Courage",
    "items": [
        {
            "quote": "Courage is not the absence of fear. Courage is feeling fear, recognizing fear, and still taking action.",
            "source": "Discussions on Youth",
            "explanation": "When your heart is racing before a big moment, that is exactly when courage is born.",
        },
        {
            "quote": "A great human revolution in just a single individual will help achieve a change in the destiny of a nation.",
            "source": "The Human Revolution",
            "explanation": "You do not need to change the world all at once — just start with yourself.",
        },
        {
            "quote": "Buddhism is about winning. It is about the courage to overcome obstacles.",
            "source": "Faith Into Action",
            "explanation": "Every obstacle is not a wall but a door waiting for your determination.",
        },
        {
            "quote": "The true hero is one who conquers his own anger and hatred.",
            "source": "For Today and Tomorrow",
            "explanation": "The hardest battles are not fought outside — they rage within us every day.",
        },
        {
            "quote": "No matter what happens, I will not be defeated. I will not run away.",
            "source": "The New Human Revolution, Vol. 1",
            "explanation": "This is not stubbornness — it is the quiet power of someone who refuses to give up.",
        },
    ],
}


# ---------------------------------------------------------------------------
# Syntax & structure tests
# ---------------------------------------------------------------------------


class TestListicleSyntax:
    """Verify generate_listicle.py parses and has expected structure."""

    def test_file_exists(self):
        assert (PIPELINE_DIR / "generate_listicle.py").exists()

    def test_syntax_valid(self):
        source = (PIPELINE_DIR / "generate_listicle.py").read_text(encoding="utf-8")
        ast.parse(source, filename="generate_listicle.py")

    def test_has_expected_functions(self):
        source = (PIPELINE_DIR / "generate_listicle.py").read_text(encoding="utf-8")
        tree = ast.parse(source, filename="generate_listicle.py")
        func_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        expected = {
            "load_quotes",
            "load_listicles",
            "save_listicles",
            "pick_theme",
            "generate_listicle_content",
            "draw_gradient",
            "wrap_text",
            "draw_separator",
            "generate_infographic",
            "generate_carousel_cover",
            "generate_carousel_slide",
            "generate_seo_page",
            "save_listicle",
            "generate",
            "main",
        }
        missing = expected - func_names
        assert not missing, f"Missing functions: {missing}"


# ---------------------------------------------------------------------------
# Data helper tests
# ---------------------------------------------------------------------------


class TestDataHelpers:
    """Test quote loading, theme picking, and history tracking."""

    def test_load_quotes(self):
        from pipeline.generate_listicle import load_quotes

        data = load_quotes()
        assert "themes" in data
        assert len(data["themes"]) == 21

    def test_pick_theme_no_history(self):
        from pipeline.generate_listicle import load_quotes, pick_theme

        data = load_quotes()
        theme = pick_theme(data, [])
        assert "id" in theme
        assert "name" in theme
        assert "quotes" in theme

    def test_pick_theme_forced(self):
        from pipeline.generate_listicle import load_quotes, pick_theme

        data = load_quotes()
        theme = pick_theme(data, [], forced_theme="hope")
        assert theme["id"] == "hope"

    def test_pick_theme_forced_invalid(self):
        from pipeline.generate_listicle import load_quotes, pick_theme

        data = load_quotes()
        with pytest.raises(ValueError, match="not found"):
            pick_theme(data, [], forced_theme="nonexistent")

    def test_pick_theme_avoids_recent(self):
        from pipeline.generate_listicle import load_quotes, pick_theme

        data = load_quotes()
        # Simulate 10 recent themes
        recent = [{"theme": t["id"]} for t in data["themes"][:10]]
        theme = pick_theme(data, recent)
        recent_ids = [l["theme"] for l in recent]
        assert theme["id"] not in recent_ids

    def test_pick_theme_resets_when_all_used(self):
        from pipeline.generate_listicle import load_quotes, pick_theme

        data = load_quotes()
        # All 21 themes used recently
        recent = [{"theme": t["id"]} for t in data["themes"]]
        theme = pick_theme(data, recent)
        assert "id" in theme  # Should still return something

    def test_load_listicles_empty(self):
        from pipeline.generate_listicle import load_listicles, LISTICLES_JSON

        # If no file exists, should return empty list
        if not LISTICLES_JSON.exists():
            result = load_listicles()
            assert result == []


# ---------------------------------------------------------------------------
# Drawing helper tests
# ---------------------------------------------------------------------------


class TestDrawingHelpers:
    """Test low-level drawing functions."""

    def test_wrap_text_short(self):
        from pipeline.generate_listicle import wrap_text, load_font

        font = load_font("Nunito-Regular.ttf", 28)
        lines = wrap_text("Hello world", font, 500)
        assert len(lines) == 1
        assert lines[0] == "Hello world"

    def test_wrap_text_long(self):
        from pipeline.generate_listicle import wrap_text, load_font

        font = load_font("Nunito-Regular.ttf", 28)
        long_text = "This is a very long quote that should wrap across multiple lines because it exceeds the maximum width"
        lines = wrap_text(long_text, font, 300)
        assert len(lines) > 1

    def test_draw_gradient(self):
        from PIL import Image
        from pipeline.generate_listicle import draw_gradient, BG_TOP, BG_BOTTOM

        img = Image.new("RGB", (100, 100))
        draw_gradient(img, BG_TOP, BG_BOTTOM)
        # Top pixel should be close to BG_TOP
        top_pixel = img.getpixel((50, 0))
        assert top_pixel == BG_TOP
        # Bottom pixel should be close to BG_BOTTOM
        bottom_pixel = img.getpixel((50, 99))
        # Allow small rounding differences
        for i in range(3):
            assert abs(bottom_pixel[i] - BG_BOTTOM[i]) <= 1


# ---------------------------------------------------------------------------
# Image generation tests
# ---------------------------------------------------------------------------


@needs_playwright
class TestImageGeneration:
    """Test Pillow image generation with mock data."""

    def test_infographic_dimensions(self):
        from pipeline.generate_listicle import generate_infographic

        img = generate_infographic(MOCK_LISTICLE)
        assert img.size == (1080, 1920)

    def test_infographic_not_blank(self):
        from pipeline.generate_listicle import generate_infographic, BG_TOP

        img = generate_infographic(MOCK_LISTICLE)
        # Sample a few pixels — they shouldn't all be the same
        pixels = [img.getpixel((540, y)) for y in range(100, 1800, 200)]
        unique = set(pixels)
        assert len(unique) > 1, "Infographic appears to be blank (all same color)"

    def test_carousel_cover_dimensions(self):
        from pipeline.generate_listicle import generate_carousel_cover

        img = generate_carousel_cover(MOCK_LISTICLE)
        assert img.size == (1080, 1080)

    def test_carousel_slide_dimensions(self):
        from pipeline.generate_listicle import generate_carousel_slide

        for i, item in enumerate(MOCK_LISTICLE["items"]):
            img = generate_carousel_slide(item, i + 1, 5, "Courage")
            assert img.size == (1080, 1080), f"Slide {i+1} wrong size"

    def test_all_slides_different(self):
        """Each carousel slide should look different (different quotes)."""
        from pipeline.generate_listicle import generate_carousel_slide
        import hashlib

        hashes = set()
        for i, item in enumerate(MOCK_LISTICLE["items"]):
            img = generate_carousel_slide(item, i + 1, 5, "Courage")
            # Hash the full image bytes to capture text differences
            h = hashlib.md5(img.tobytes()).hexdigest()
            hashes.add(h)
        assert len(hashes) == 5, "Some carousel slides are identical"


# ---------------------------------------------------------------------------
# SEO page tests
# ---------------------------------------------------------------------------


class TestSEOPage:
    """Test HTML page generation."""

    def test_seo_page_structure(self):
        from pipeline.generate_listicle import generate_seo_page

        html = generate_seo_page(MOCK_LISTICLE, "2026-04-09", [])
        assert "<!DOCTYPE html>" in html
        assert "og:image" in html
        assert "schema.org" in html.lower() or "Schema.org" in html
        assert "Courage" in html
        assert "thelotuslane.in" in html

    def test_seo_page_has_all_quotes(self):
        from pipeline.generate_listicle import generate_seo_page

        html = generate_seo_page(MOCK_LISTICLE, "2026-04-09", [])
        for item in MOCK_LISTICLE["items"]:
            assert item["quote"] in html, f"Quote missing from page: {item['quote'][:40]}..."

    def test_seo_page_has_sharing(self):
        from pipeline.generate_listicle import generate_seo_page

        html = generate_seo_page(MOCK_LISTICLE, "2026-04-09", [])
        assert "WhatsApp" in html
        assert "Pinterest" in html

    def test_seo_page_has_goatcounter(self):
        from pipeline.generate_listicle import generate_seo_page

        html = generate_seo_page(MOCK_LISTICLE, "2026-04-09", [])
        assert "goatcounter" in html

    def test_navigation_links(self):
        from pipeline.generate_listicle import generate_seo_page

        all_listicles = [
            {"date": "2026-04-08", "title": "Previous Listicle", "theme": "hope"},
            {"date": "2026-04-09", "title": "Current", "theme": "courage"},
            {"date": "2026-04-10", "title": "Next Listicle", "theme": "peace"},
        ]
        html = generate_seo_page(MOCK_LISTICLE, "2026-04-09", all_listicles)
        assert "2026-04-08.html" in html
        assert "2026-04-10.html" in html


# ---------------------------------------------------------------------------
# Full save flow test
# ---------------------------------------------------------------------------


@needs_playwright
class TestSaveFlow:
    """Test the complete save pipeline with cleanup."""

    def setup_method(self):
        from pipeline.generate_listicle import LISTICLES_DIR

        self.listicles_dir = LISTICLES_DIR
        # Clean up before test
        if self.listicles_dir.exists():
            self._backup = True
        else:
            self._backup = False

    def teardown_method(self):
        # Clean up test artifacts
        test_date = "9999-12-31"
        (self.listicles_dir / f"{test_date}.png").unlink(missing_ok=True)
        (self.listicles_dir / f"{test_date}.html").unlink(missing_ok=True)
        carousel_dir = self.listicles_dir / test_date
        if carousel_dir.exists():
            shutil.rmtree(str(carousel_dir))
        # Remove test entry from listicles.json
        json_path = self.listicles_dir / "listicles.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            data = [l for l in data if l.get("date") != test_date]
            if data:
                json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            else:
                json_path.unlink()
        # Remove empty dir
        if self.listicles_dir.exists() and not any(self.listicles_dir.iterdir()):
            self.listicles_dir.rmdir()

    def test_save_creates_all_files(self):
        from pipeline.generate_listicle import (
            generate_infographic,
            generate_carousel_cover,
            generate_carousel_slide,
            save_listicle,
            load_listicles,
        )

        test_date = "9999-12-31"
        infographic = generate_infographic(MOCK_LISTICLE)
        cover = generate_carousel_cover(MOCK_LISTICLE)
        slides = [
            generate_carousel_slide(item, i + 1, 5, "Courage")
            for i, item in enumerate(MOCK_LISTICLE["items"])
        ]

        entry = save_listicle(MOCK_LISTICLE, test_date, infographic, cover, slides)

        assert (self.listicles_dir / f"{test_date}.png").exists()
        assert (self.listicles_dir / f"{test_date}.html").exists()
        assert (self.listicles_dir / test_date / "cover.png").exists()
        for i in range(1, 6):
            assert (self.listicles_dir / test_date / f"{i}.png").exists()

        data = load_listicles()
        assert any(l["date"] == test_date for l in data)


# ---------------------------------------------------------------------------
# Sitemap integration test
# ---------------------------------------------------------------------------


class TestSitemapIntegration:
    """Verify generate_pages.py includes listicle pages."""

    def test_sitemap_generator_has_listicle_section(self):
        source = (PIPELINE_DIR / "generate_pages.py").read_text(encoding="utf-8")
        assert "listicles" in source, "generate_pages.py missing listicle sitemap section"
        assert "listicles_dir" in source or "listicles/" in source
