"""Generated Glideleaf mark shared by the window, tray, and executable."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

_MARK = Path(__file__).with_name("assets") / "glideleaf-mark.png"
_STATUS = {
    "stopped": "#A5B1C4", "starting": "#F4BA55",
    "advertising": "#67B4FF", "connected": "#67B4FF",
    "ready": "#56D5A5", "error": "#FF7D78",
}


@lru_cache(maxsize=1)
def _mark() -> Image.Image:
    with Image.open(_MARK) as source:
        return source.convert("RGBA")


def make_icon(status: str | None = "stopped", size: int = 64) -> Image.Image:
    """Resize the generated mark and add the live tray status at high resolution."""
    scale = 4
    if size <= 24:
        # A simplified optical size keeps the leaf visible in a 16 px tray slot.
        canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
        small = ImageDraw.Draw(canvas)
        def point(*values):
            return tuple(round(value * size * scale / 64) for value in values)
        small.rounded_rectangle(point(2, 2, 62, 62), radius=round(14 * size * scale / 64), fill="#0C2140")
        small.ellipse(point(15, 13, 51, 49), fill="#61DFAC")
        small.polygon([point(16, 47), point(23, 28), point(50, 15), point(45, 39), point(30, 49)], fill="#61DFAC")
        small.line([point(20, 47), point(43, 25)], fill="#0C2140", width=max(2, round(4 * size * scale / 64)))
    else:
        canvas = _mark().resize((size * scale, size * scale), Image.Resampling.LANCZOS)
    if status is not None:
        draw = ImageDraw.Draw(canvas)
        def box(*values):
            return tuple(round(value * size * scale / 64) for value in values)
        draw.ellipse(box(44, 42, 62, 60), fill="#0C2140")
        draw.ellipse(box(47, 45, 59, 57), fill=_STATUS.get(status, _STATUS["stopped"]))
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def apply_window_icon(window) -> None:
    """Keep a Tk image reference alive for the title bar and task switcher."""
    from PIL import ImageTk
    window._glideleaf_icon = ImageTk.PhotoImage(make_icon(None, 64), master=window)
    window.iconphoto(False, window._glideleaf_icon)
