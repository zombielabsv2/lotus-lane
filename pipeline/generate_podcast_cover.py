"""Generate 1400x1400 podcast cover art for Lotus Lane Daily.

Apple Podcasts spec: 1400x1400 to 3000x3000 px, RGB JPEG/PNG.
Matches the cream + red brand palette used across the site.

Usage:
    python pipeline/generate_podcast_cover.py [--out path/to/cover.png]
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


SIZE = 1500  # > 1400 minimum, < 3000 max — comfortable middle for Apple/Spotify
CREAM = (250, 249, 246)
CREAM_DEEP = (240, 236, 228)
RED = (192, 57, 43)
INK = (45, 45, 45)
INK_SOFT = (90, 88, 84)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/Georgia.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_paper(img: Image.Image) -> None:
    """Soft cream gradient — top lighter, bottom slightly deeper."""
    pixels = img.load()
    for y in range(SIZE):
        t = y / SIZE
        r = int(CREAM[0] * (1 - t) + CREAM_DEEP[0] * t)
        g = int(CREAM[1] * (1 - t) + CREAM_DEEP[1] * t)
        b = int(CREAM[2] * (1 - t) + CREAM_DEEP[2] * t)
        for x in range(SIZE):
            pixels[x, y] = (r, g, b)


def _draw_lotus(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int) -> None:
    """Stylised lotus — overlapping petal arcs."""
    petals = 8
    for i in range(petals):
        angle = (math.tau * i) / petals
        px = cx + math.cos(angle) * radius * 0.55
        py = cy + math.sin(angle) * radius * 0.55
        bbox = (
            px - radius * 0.55,
            py - radius * 0.85,
            px + radius * 0.55,
            py + radius * 0.85,
        )
        deg = math.degrees(angle) + 90
        draw.pieslice(bbox, deg - 32, deg + 32, fill=None, outline=RED, width=4)
    draw.ellipse(
        (cx - radius * 0.15, cy - radius * 0.15, cx + radius * 0.15, cy + radius * 0.15),
        fill=RED,
    )


def _draw_text_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    letter_spacing: int = 0,
) -> None:
    if letter_spacing == 0:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((SIZE - w) / 2, y), text, font=font, fill=fill)
        return
    # Manual letter spacing
    char_widths = [draw.textbbox((0, 0), c, font=font)[2] for c in text]
    total = sum(char_widths) + letter_spacing * (len(text) - 1)
    x = (SIZE - total) / 2
    for c, cw in zip(text, char_widths):
        draw.text((x, y), c, font=font, fill=fill)
        x += cw + letter_spacing


def generate(out_path: Path) -> Path:
    img = Image.new("RGB", (SIZE, SIZE), CREAM)
    _draw_paper(img)

    # Soft red glow behind lotus
    glow = Image.new("RGB", (SIZE, SIZE), CREAM)
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (SIZE * 0.18, SIZE * 0.18, SIZE * 0.82, SIZE * 0.82),
        fill=(245, 220, 215),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(80))
    img = Image.blend(img, glow, 0.6)

    draw = ImageDraw.Draw(img)

    # Lotus mark, vertically slightly above center
    _draw_lotus(draw, cx=SIZE // 2, cy=int(SIZE * 0.46), radius=int(SIZE * 0.18))

    # Brand wordmark — same treatment as the site header
    wordmark_y = int(SIZE * 0.71)
    main = _font(126, bold=True)
    _draw_text_centered(draw, "THE LOTUS LANE", wordmark_y, main, INK, letter_spacing=14)

    # Sub-title — "DAILY"
    sub_y = wordmark_y + 165
    sub = _font(58, bold=True)
    _draw_text_centered(draw, "D A I L Y", sub_y, sub, RED, letter_spacing=22)

    # Tagline
    tag_y = sub_y + 110
    tag = _font(40)
    _draw_text_centered(
        draw,
        "wisdom for what you're going through",
        tag_y,
        tag,
        INK_SOFT,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="podcast/cover.png")
    args = parser.parse_args()
    p = generate(Path(args.out))
    print(f"OK {p} ({p.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
