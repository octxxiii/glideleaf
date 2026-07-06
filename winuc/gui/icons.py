"""Tray icon images, drawn in code so no asset files are needed."""

from __future__ import annotations

from PIL import Image, ImageDraw

# Status -> accent color for the dot.
_COLORS = {
    "stopped": (120, 120, 120),
    "starting": (230, 180, 40),
    "advertising": (60, 140, 230),
    "connected": (60, 140, 230),
    "ready": (60, 200, 110),
    "error": (220, 70, 70),
}


def make_icon(status: str = "stopped", size: int = 64) -> Image.Image:
    color = _COLORS.get(status, _COLORS["stopped"])
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Rounded dark square background.
    d.rounded_rectangle([2, 2, size - 3, size - 3], radius=size // 5, fill=(38, 40, 46, 255))
    # A pointer-ish glyph: a small circle (cursor) plus a bar (keyboard).
    cx, cy = size // 2, size // 2 - 6
    r = size // 6
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    d.rounded_rectangle(
        [size // 4, size - size // 3, size - size // 4, size - size // 5],
        radius=3,
        fill=color,
    )
    return img
