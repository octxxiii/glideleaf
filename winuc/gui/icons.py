"""Glideleaf mark shared by the window, tray, and Windows executable."""
from __future__ import annotations

from PIL import Image, ImageDraw

_STATUS = {
    "stopped": "#A5B1C4", "starting": "#F4BA55",
    "advertising": "#67B4FF", "connected": "#67B4FF",
    "ready": "#56D5A5", "error": "#FF7D78",
}


def make_icon(status: str | None = "stopped", size: int = 64) -> Image.Image:
    """Draw at 4x for crisp tray icons and high-resolution application icons."""
    scale = 4
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    def points(*values):
        return tuple(round(value * size * scale / 64) for value in values)

    draw.rounded_rectangle(points(2, 2, 62, 62), radius=round(15 * size * scale / 64), fill="#14243D")
    # Tapered leaf and a short vein retain their shape at 16 px.
    draw.ellipse(points(16, 15, 49, 48), fill="#6DE1BE")
    draw.polygon([points(17, 46), points(19, 28), points(48, 15), points(45, 36), points(29, 49)], fill="#6DE1BE")
    draw.line([points(18, 49), points(39, 28)], fill="#D7FFF1", width=max(2, round(3 * size * scale / 64)), joint="curve")
    draw.line([points(30, 37), points(29, 29)], fill="#D7FFF1", width=max(2, round(2 * size * scale / 64)))
    if status is not None:
        draw.ellipse(points(45, 43, 61, 59), fill="#14243D")
        draw.ellipse(points(48, 46, 58, 56), fill=_STATUS.get(status, _STATUS["stopped"]))
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def apply_window_icon(window) -> None:
    """Keep a Tk image reference alive for the title bar and task switcher."""
    from PIL import ImageTk
    window._glideleaf_icon = ImageTk.PhotoImage(make_icon(None, 64), master=window)
    window.iconphoto(False, window._glideleaf_icon)
