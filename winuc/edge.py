"""Screen-edge break-through detection and virtual cursor tracking on the iPad side.

Reproduces the UX of macOS Universal Control:

  LOCAL   — Normal state. When the cursor reaches the outermost pixel of the configured edge, go to PUSHING.
  PUSHING — The cursor is pinned to the edge and further push amount (raw delta) is accumulated.
            When it exceeds push_threshold_px, "break through" to REMOTE.
            Moving in the opposite direction / not pushing for a while cancels and returns to LOCAL.
  REMOTE  — Capture all input and forward it to the iPad. Estimate the cursor position on the iPad
            from the motion sent, and when pushed back to the shared edge, return to LOCAL.

This module is pure logic with no dependency on Win32 (subject to unit tests).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class State(enum.Enum):
    LOCAL = "local"
    PUSHING = "pushing"
    REMOTE = "remote"


class PushResult(enum.Enum):
    STAY = "stay"
    CROSS = "cross"
    CANCEL = "cancel"


@dataclass
class RemoteMotion:
    dx: int
    dy: int
    exited: bool
    exit_point: tuple[int, int] | None = None  # PC-side cursor position when returning to LOCAL


# Per-edge "outward" unit vector (direction leaving the PC screen)
_OUTWARD = {
    "right": (1, 0),
    "left": (-1, 0),
    "top": (0, -1),
    "bottom": (0, 1),
}


class EdgeStateMachine:
    def __init__(
        self,
        edge: str,
        push_threshold_px: int,
        return_threshold_px: int,
        remote_size: tuple[int, int],
        speed: float = 1.0,
        layout_center_pct: int = 50,
        layout_span_pct: int = 100,
        cancel_margin_px: int = 15,
        idle_cancel_ms: int = 400,
    ) -> None:
        if edge not in _OUTWARD:
            raise ValueError(f"invalid edge: {edge}")
        self.edge = edge
        self.push_threshold = push_threshold_px
        self.return_threshold = return_threshold_px
        self.remote_w, self.remote_h = remote_size
        self.speed = speed
        self.layout_center_pct = layout_center_pct
        self.layout_span_pct = layout_span_pct
        self.cancel_margin = cancel_margin_px
        self.idle_cancel_ms = idle_cancel_ms

        self.state = State.LOCAL
        # PC-side edge range (virtual screen coordinates). Set by set_edge_geometry().
        self._edge_coord = 0       # Fixed coordinate of the edge (max x for right)
        self._edge_lo = 0          # Minimum of the range along the edge
        self._edge_hi = 0          # Maximum
        self._push_acc = 0.0
        self._push_last_ms = 0.0
        self._entry_point = (0, 0)
        # iPad-side virtual cursor
        self._vx = 0.0
        self._vy = 0.0
        self._return_acc = 0.0
        # Fractional carry-over from scaling
        self._carry_x = 0.0
        self._carry_y = 0.0

    # ------------------------------------------------------------- geometry

    def set_edge_geometry(self, edge_coord: int, lo: int, hi: int) -> None:
        """Set the edge position.

        For a vertical edge (right/left): edge_coord=x, lo/hi=range of y.
        For a horizontal edge (top/bottom): edge_coord=y, lo/hi=range of x.
        """
        self._edge_coord = edge_coord
        span = max(0, hi - lo)
        start = (self.layout_center_pct - self.layout_span_pct / 2) / 100
        end = (self.layout_center_pct + self.layout_span_pct / 2) / 100
        self._edge_lo = lo + round(span * start)
        self._edge_hi = lo + round(span * end)

    def hits_edge(self, x: int, y: int) -> bool:
        if self.edge == "right":
            return x >= self._edge_coord and self._edge_lo <= y <= self._edge_hi
        if self.edge == "left":
            return x <= self._edge_coord and self._edge_lo <= y <= self._edge_hi
        if self.edge == "top":
            return y <= self._edge_coord and self._edge_lo <= x <= self._edge_hi
        return y >= self._edge_coord and self._edge_lo <= x <= self._edge_hi

    # ---------------------------------------------------------- transitions

    def begin_push(self, x: int, y: int, now_ms: float) -> None:
        self.state = State.PUSHING
        self._entry_point = (x, y)
        self._push_acc = 0.0
        self._push_last_ms = now_ms

    def _outward_component(self, dx: int, dy: int) -> float:
        ox, oy = _OUTWARD[self.edge]
        return dx * ox + dy * oy

    def on_push_delta(self, dx: int, dy: int, now_ms: float) -> PushResult:
        assert self.state == State.PUSHING
        if now_ms - self._push_last_ms > self.idle_cancel_ms:
            # Push was interrupted: reset accumulation (stay pinned and wait)
            self._push_acc = 0.0
        self._push_last_ms = now_ms

        self._push_acc += self._outward_component(dx, dy)
        if self._push_acc >= self.push_threshold:
            self._enter_remote()
            return PushResult.CROSS
        if self._push_acc < -self.cancel_margin:
            self.state = State.LOCAL
            return PushResult.CANCEL
        return PushResult.STAY

    def cancel_push(self) -> None:
        self.state = State.LOCAL

    @property
    def entry_point(self) -> tuple[int, int]:
        return self._entry_point

    def _lateral_fraction(self) -> float:
        span = max(1, self._edge_hi - self._edge_lo)
        x, y = self._entry_point
        lateral = y if self.edge in ("right", "left") else x
        return min(1.0, max(0.0, (lateral - self._edge_lo) / span))

    def _enter_remote(self) -> None:
        self.state = State.REMOTE
        f = self._lateral_fraction()
        # Enter the iPad from the edge opposite the side we left the PC on
        if self.edge == "right":
            self._vx, self._vy = 0.0, f * (self.remote_h - 1)
        elif self.edge == "left":
            self._vx, self._vy = float(self.remote_w - 1), f * (self.remote_h - 1)
        elif self.edge == "top":
            self._vx, self._vy = f * (self.remote_w - 1), float(self.remote_h - 1)
        else:  # bottom
            self._vx, self._vy = f * (self.remote_w - 1), 0.0
        self._return_acc = 0.0
        self._carry_x = self._carry_y = 0.0

    # --------------------------------------------------------------- remote

    def _scale(self, dx: int, dy: int) -> tuple[int, int]:
        fx = dx * self.speed + self._carry_x
        fy = dy * self.speed + self._carry_y
        ix, iy = int(fx), int(fy)
        self._carry_x, self._carry_y = fx - ix, fy - iy
        return ix, iy

    def _pos_along(self, x: float, y: float) -> float:
        """Depth from the shared edge (positive toward the inside of the iPad). Negative means breaking through the edge."""
        if self.edge == "right":
            return x
        if self.edge == "left":
            return (self.remote_w - 1) - x
        if self.edge == "top":
            return (self.remote_h - 1) - y
        return y

    def on_remote_delta(self, dx: int, dy: int) -> RemoteMotion:
        assert self.state == State.REMOTE
        sdx, sdy = self._scale(dx, dy)

        nx, ny = self._vx + sdx, self._vy + sdy
        depth_before = self._pos_along(self._vx, self._vy)
        depth_after = self._pos_along(nx, ny)

        if depth_after < 0:
            # Accumulate the amount broken through the shared edge (a vigorous push-back returns in one go)
            self._return_acc += -depth_after + max(0.0, depth_before)
        elif depth_after > depth_before:
            self._return_acc = 0.0  # Reset when moving toward the inside of the iPad

        self._vx = min(float(self.remote_w - 1), max(0.0, nx))
        self._vy = min(float(self.remote_h - 1), max(0.0, ny))

        if self._return_acc >= self.return_threshold:
            self.state = State.LOCAL
            return RemoteMotion(sdx, sdy, True, self._exit_point())
        return RemoteMotion(sdx, sdy, False)

    def force_local(self) -> tuple[int, int]:
        """Fail-safe (disconnect / hotkey): immediately return to LOCAL."""
        self.state = State.LOCAL
        return self._exit_point()

    def _exit_point(self) -> tuple[int, int]:
        span = self._edge_hi - self._edge_lo
        if self.edge in ("right", "left"):
            f = self._vy / max(1, self.remote_h - 1)
            y = self._edge_lo + int(f * span)
            x = self._edge_coord
        else:
            f = self._vx / max(1, self.remote_w - 1)
            x = self._edge_lo + int(f * span)
            y = self._edge_coord
        return (x, y)
