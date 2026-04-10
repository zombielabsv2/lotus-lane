"""
Shared Playwright HTML/CSS renderer for The Lotus Lane.

Renders dialogue bands, footers, and video text overlays as HTML → image
using a headless Chromium browser. Produces vastly superior typography
compared to Pillow's basic FreeType rendering.

Used by:
    - generate_strip.py (static comic strips)
    - video_generator.py (YouTube Shorts)
"""

from io import BytesIO
from PIL import Image

# ---------------------------------------------------------------------------
# Colour constants (shared with pipeline)
# ---------------------------------------------------------------------------

# Static strip colours
STRIP_BG_DIALOGUE_HEX = "#f5f3ee"
STRIP_BG_FOOTER_HEX = "#f0ece4"
STRIP_BG_DIALOGUE_RGB = (245, 243, 238)
STRIP_SPEAKER_HEX = "#9b2828"
STRIP_TEXT_HEX = "#2d2d2d"

# Video colours
VIDEO_BG_HEX = "#18161c"
VIDEO_SPEAKER_HEX = "#dcb964"
VIDEO_TEXT_HEX = "#ffffff"
VIDEO_ENDCARD_BG_HEX = "#1e1b23"
VIDEO_ENDCARD_ACCENT_HEX = "#c8aa64"
VIDEO_ENDCARD_TEXT_HEX = "#f0ebe1"
VIDEO_ENDCARD_DIM_HEX = "#a09b91"

# Google Fonts import (loaded once per page, cached by browser)
GOOGLE_FONTS_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Comic+Neue:ital,wght@0,400;0,700;1,400&"
    "family=Nunito:wght@400;600;700&display=swap');"
)


# ---------------------------------------------------------------------------
# Browser lifecycle
# ---------------------------------------------------------------------------

class PlaywrightBrowser:
    """Context manager that opens one Chromium instance and reuses it."""

    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None
        self._fonts_loaded = False

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page()
        return self

    def __exit__(self, *exc):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def render(self, html, width, element_id="capture"):
        """Render HTML and screenshot a specific element. Returns PIL Image."""
        self._page.set_viewport_size({"width": width, "height": 800})
        self._page.set_content(html)

        # Wait for Google Fonts on first render; subsequent renders reuse cache
        if not self._fonts_loaded:
            self._page.wait_for_timeout(800)
            try:
                self._page.wait_for_function(
                    "document.fonts.ready.then(() => true)", timeout=5000
                )
            except Exception:
                pass
            self._page.wait_for_timeout(500)
            self._fonts_loaded = True
        else:
            self._page.wait_for_timeout(300)

        element = self._page.query_selector(f"#{element_id}")
        img_bytes = element.screenshot() if element else self._page.screenshot(full_page=True)
        return Image.open(BytesIO(img_bytes))


# ---------------------------------------------------------------------------
# HTML templates — static strip
# ---------------------------------------------------------------------------

def strip_dialogue_html(dialogue_lines, width):
    """HTML for a dialogue band below a comic panel (light background)."""
    lines_html = ""
    for line in dialogue_lines[:3]:
        parts = line.split(": ", 1)
        if len(parts) == 2:
            speaker, text = parts
            lines_html += (
                f'<div class="dl">'
                f'<span class="sp">{speaker}:</span> '
                f'<span class="tx">{text}</span>'
                f'</div>'
            )
        else:
            lines_html += f'<div class="dl"><span class="tx">{line}</span></div>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{GOOGLE_FONTS_IMPORT}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{width}px;margin:0;background:{STRIP_BG_DIALOGUE_HEX};
  font-family:'Nunito','Comic Neue','Segoe UI',sans-serif;-webkit-font-smoothing:antialiased}}
.band{{width:{width}px;padding:18px 44px 16px;background:{STRIP_BG_DIALOGUE_HEX};
  border-top:1px solid #dcd8cf}}
.dl{{margin-bottom:10px;line-height:1.55;letter-spacing:0.01em}}
.dl:last-child{{margin-bottom:0}}
.sp{{font-family:'Comic Neue','Nunito',sans-serif;font-weight:700;
  color:{STRIP_SPEAKER_HEX};font-size:28px;text-shadow:0 1px 1px rgba(155,40,40,.08)}}
.tx{{font-family:'Nunito','Comic Neue',sans-serif;font-weight:400;
  color:{STRIP_TEXT_HEX};font-size:26px;text-shadow:0 .5px 0 rgba(0,0,0,.04)}}
</style></head><body>
<div class="band" id="capture">{lines_html}</div>
</body></html>"""


def strip_footer_html(quote, source, width,
                      brand="The Lotus Lane  \u00b7  thelotuslane.in"):
    """HTML for the footer section (Nichiren quote + branding)."""
    quote_html = ""
    if quote:
        quote_html = f'<div class="qt">\u201c{quote}\u201d</div>'
        if source:
            quote_html += f'<div class="src">\u2014 {source}</div>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{GOOGLE_FONTS_IMPORT}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{width}px;margin:0;background:{STRIP_BG_FOOTER_HEX};
  font-family:'Nunito','Comic Neue','Segoe UI',sans-serif;-webkit-font-smoothing:antialiased}}
.footer{{width:{width}px;padding:20px 50px 18px;background:{STRIP_BG_FOOTER_HEX};
  border-top:2px solid #d2cdc3;text-align:center}}
.qt{{font-size:22px;font-weight:600;color:#504638;line-height:1.5;
  letter-spacing:.01em;text-shadow:0 .5px 0 rgba(0,0,0,.03);
  margin-bottom:6px;font-style:italic}}
.src{{font-size:17px;font-weight:400;color:#8c8278;margin-bottom:14px;letter-spacing:.02em}}
.brand{{font-family:'Comic Neue','Nunito',sans-serif;font-size:18px;font-weight:700;
  color:#a09688;letter-spacing:.06em;text-transform:uppercase}}
</style></head><body>
<div class="footer" id="capture">{quote_html}<div class="brand">{brand}</div></div>
</body></html>"""


# ---------------------------------------------------------------------------
# HTML templates — video (dark background, 1080px wide)
# ---------------------------------------------------------------------------

def video_dialogue_html(dialogue_lines, width=1080):
    """HTML for video dialogue overlay (dark, semi-transparent band)."""
    lines_html = ""
    for line in dialogue_lines[:3]:
        parts = line.split(": ", 1)
        if len(parts) == 2:
            speaker, text = parts
            lines_html += (
                f'<div class="dl">'
                f'<span class="sp">{speaker}:</span> '
                f'<span class="tx">{text}</span>'
                f'</div>'
            )
        else:
            lines_html += f'<div class="dl"><span class="tx">{line}</span></div>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{GOOGLE_FONTS_IMPORT}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{width}px;margin:0;background:transparent;
  font-family:'Nunito','Comic Neue','Segoe UI',sans-serif;-webkit-font-smoothing:antialiased}}
.band{{width:{width - 120}px;margin:0 auto;padding:16px 24px 14px;
  background:rgba(15,13,18,0.82);border-radius:16px}}
.dl{{margin-bottom:10px;line-height:1.5;letter-spacing:.01em}}
.dl:last-child{{margin-bottom:0}}
.sp{{font-family:'Comic Neue','Nunito',sans-serif;font-weight:700;
  color:{VIDEO_SPEAKER_HEX};font-size:34px;
  text-shadow:0 1px 2px rgba(0,0,0,.3)}}
.tx{{font-family:'Nunito','Comic Neue',sans-serif;font-weight:400;
  color:{VIDEO_TEXT_HEX};font-size:32px;
  text-shadow:0 1px 2px rgba(0,0,0,.25)}}
</style></head><body>
<div class="band" id="capture">{lines_html}</div>
</body></html>"""


def video_endcard_html(quote, source, message, title, width=1080, height=1920):
    """HTML for the branded end card (dark background, gold accents)."""
    quote_html = ""
    if quote:
        quote_html = f'<div class="qt">\u201c{quote}\u201d</div>'
    source_html = f'<div class="src">\u2014 {source}</div>' if source else ""
    msg_html = f'<div class="msg">{message}</div>' if message else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{GOOGLE_FONTS_IMPORT}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{width}px;height:{height}px;margin:0;
  background:{VIDEO_ENDCARD_BG_HEX};
  font-family:'Nunito','Comic Neue','Segoe UI',sans-serif;-webkit-font-smoothing:antialiased;
  display:flex;flex-direction:column;align-items:center;justify-content:center}}
.card{{width:{width}px;height:{height}px;display:flex;flex-direction:column;
  align-items:center;justify-content:center;padding:60px 80px;text-align:center}}
.accent{{width:200px;height:2px;background:{VIDEO_ENDCARD_ACCENT_HEX};margin:30px auto}}
.qt{{font-size:38px;font-weight:600;color:{VIDEO_ENDCARD_TEXT_HEX};
  line-height:1.5;letter-spacing:.01em;font-style:italic;max-width:900px}}
.src{{font-size:26px;color:{VIDEO_ENDCARD_DIM_HEX};margin-top:16px;letter-spacing:.02em}}
.msg{{font-size:30px;color:{VIDEO_ENDCARD_DIM_HEX};margin-top:30px;
  line-height:1.5;max-width:860px}}
.brand{{font-family:'Comic Neue','Nunito',sans-serif;font-size:28px;font-weight:700;
  color:{VIDEO_ENDCARD_ACCENT_HEX};letter-spacing:.04em;margin-top:60px}}
.url{{font-size:24px;color:{VIDEO_ENDCARD_DIM_HEX};margin-top:12px}}
</style></head><body>
<div class="card" id="capture">
  <div class="accent"></div>
  {quote_html}
  {source_html}
  {msg_html}
  <div class="accent"></div>
  <div class="brand">The Lotus Lane</div>
  <div class="url">thelotuslane.in</div>
</div>
</body></html>"""


# ---------------------------------------------------------------------------
# High-level render helpers
# ---------------------------------------------------------------------------

def render_strip_bands(script, width, browser=None):
    """Render all dialogue bands + footer for a static strip.

    If *browser* is supplied it is reused (faster). Otherwise a temporary
    browser is opened and closed automatically.

    Returns (band_images, footer_image) — list of PIL Images + one PIL Image.
    """
    own_browser = browser is None
    if own_browser:
        browser = PlaywrightBrowser()
        browser.__enter__()

    try:
        band_images = []
        for panel_data in script["panels"]:
            dialogue = panel_data.get("dialogue", [])
            if not dialogue:
                band_images.append(Image.new("RGB", (width, 10), STRIP_BG_DIALOGUE_RGB))
                continue
            html = strip_dialogue_html(dialogue, width)
            band_images.append(browser.render(html, width))

        quote = script.get("nichiren_quote", "")
        source = script.get("source", "")
        html = strip_footer_html(quote, source, width)
        footer_image = browser.render(html, width)

        return band_images, footer_image
    finally:
        if own_browser:
            browser.__exit__(None, None, None)


def render_video_dialogue(dialogue_lines, width=1080, browser=None):
    """Render a video dialogue overlay. Returns PIL RGBA Image."""
    own_browser = browser is None
    if own_browser:
        browser = PlaywrightBrowser()
        browser.__enter__()
    try:
        html = video_dialogue_html(dialogue_lines, width)
        return browser.render(html, width)
    finally:
        if own_browser:
            browser.__exit__(None, None, None)


def render_video_endcard(script, width=1080, height=1920, browser=None):
    """Render the end card for a video. Returns PIL RGB Image."""
    own_browser = browser is None
    if own_browser:
        browser = PlaywrightBrowser()
        browser.__enter__()
    try:
        html = video_endcard_html(
            script.get("nichiren_quote", ""),
            script.get("source", ""),
            script.get("message", ""),
            script.get("title", ""),
            width, height,
        )
        img = browser.render(html, width)
        # Ensure exact dimensions
        if img.size != (width, height):
            canvas = Image.new("RGB", (width, height), (30, 27, 35))
            canvas.paste(img, (0, 0))
            img = canvas
        return img
    finally:
        if own_browser:
            browser.__exit__(None, None, None)
