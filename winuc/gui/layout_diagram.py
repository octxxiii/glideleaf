"""Shared screen-arrangement drawing and drag geometry for Tk windows."""
from __future__ import annotations
import math

from .theme import BLUE, INK, LINE, MUTED, font_family


def clamp_center(center: int, span: int) -> int:
    low = math.ceil(span / 2)
    high = math.floor(100 - span / 2)
    return int(max(low, min(high, center)))


def layout_from_point(x: float, y: float, pc: tuple[float, float, float, float], span: int) -> tuple[str, int]:
    """Map a dragged iPad center to an edge and a valid overlap center."""
    x1, y1, x2, y2 = pc
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = (x - cx) / ((x2 - x1) / 2), (y - cy) / ((y2 - y1) / 2)
    if abs(dx) >= abs(dy):
        edge = "right" if dx >= 0 else "left"
        pct = round((y - y1) / (y2 - y1) * 100)
    else:
        edge = "bottom" if dy >= 0 else "top"
        pct = round((x - x1) / (x2 - x1) * 100)
    return edge, clamp_center(pct, span)


def draw_layout(canvas, edge: str, center: int, span: int, *, compact: bool = False):
    """Draw the PC, the iPad, and the active crossing segment."""
    canvas.delete("all")
    width = max(300, canvas.winfo_width())
    height = max(100, canvas.winfo_height())
    pc_w, pc_h = (142, 38) if compact else (200, min(114, max(70, height - 72)))
    pad_w, pad_h = (94, 30) if compact else (118, min(60, max(40, height - pc_h - 14)))
    cx, cy = width / 2, height / 2
    if edge == "top":
        cy += (pad_h + 6) / 2
    elif edge == "bottom":
        cy -= (pad_h + 6) / 2
    x1, y1, x2, y2 = cx - pc_w / 2, cy - pc_h / 2, cx + pc_w / 2, cy + pc_h / 2
    c = clamp_center(center, span) / 100
    start, end = c - span / 200, c + span / 200
    if edge in ("left", "right"):
        iy = y1 + c * pc_h
        ix = x1 - 6 - pad_w / 2 if edge == "left" else x2 + 6 + pad_w / 2
        portal_x = x1 if edge == "left" else x2
        portal = (portal_x, y1 + start * pc_h, portal_x, y1 + end * pc_h)
    else:
        ix = x1 + c * pc_w
        iy = y1 - 6 - pad_h / 2 if edge == "top" else y2 + 6 + pad_h / 2
        portal_y = y1 if edge == "top" else y2
        portal = (x1 + start * pc_w, portal_y, x1 + end * pc_w, portal_y)
    canvas.create_rectangle(x1, y1, x2, y2, fill="#FFFFFF", outline=LINE, width=2)
    canvas.create_text(cx, cy, text="Windows PC", fill=INK, font=("Segoe UI", 11 if compact else 13, "bold"))
    canvas.create_line(*portal, fill=BLUE, width=5 if compact else 7, capstyle="round")
    canvas.create_rectangle(ix - pad_w / 2, iy - pad_h / 2, ix + pad_w / 2, iy + pad_h / 2,
                            fill="#D9EEE8", outline=BLUE, width=2)
    canvas.create_text(ix, iy, text="iPad", fill=INK, font=("Segoe UI", 10 if compact else 12, "bold"))
    return (x1, y1, x2, y2)
