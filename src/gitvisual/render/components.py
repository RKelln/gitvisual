"""Reusable Pillow drawing components."""

from __future__ import annotations

from pathlib import Path

from PIL import ImageDraw, ImageFont


def load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font from path, falling back to Pillow's default if unavailable."""
    if path.exists():
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()


def wrap_text(
    text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int
) -> list[str]:
    """Word-wrap text to fit within max_width pixels using font metrics."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip() if current else word
        bbox = font.getbbox(test)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def draw_horizontal_rule(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    color: tuple[int, int, int, int],
    thickness: int = 1,
) -> None:
    """Draw a horizontal rule."""
    draw.rectangle([x, y, x + width, y + thickness], fill=color)


def draw_stat_badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    value: str,
    label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    value_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    label_color: tuple[int, int, int, int],
    value_color: tuple[int, int, int, int],
) -> int:
    """Draw a label+value pair inline. Returns the x position after the badge."""
    draw.text((x, y), label, font=label_font, fill=label_color)
    lbbox = label_font.getbbox(label)
    lw = lbbox[2] - lbbox[0]
    vx = x + lw + 6
    draw.text((vx, y), value, font=value_font, fill=value_color)
    vbbox = value_font.getbbox(value)
    vw = vbbox[2] - vbbox[0]
    return int(vx + vw)


def text_width(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    """Return rendered pixel width of text."""
    bbox = font.getbbox(text)
    return int(bbox[2] - bbox[0])


def text_height(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    """Return rendered pixel height of a typical line."""
    bbox = font.getbbox("Ag")
    return int(bbox[3] - bbox[1])
