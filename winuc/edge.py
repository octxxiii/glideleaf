"""画面端の突き抜け判定と、iPad 側の仮想カーソル追跡。

macOS Universal Control の UX を再現する:

  LOCAL   — 通常状態。カーソルが設定されたエッジの最外周ピクセルに達すると PUSHING へ。
  PUSHING — カーソルはエッジにピン留めされ、さらに押し込んだ量 (raw delta) を蓄積。
            push_threshold_px を超えたら REMOTE へ「突き抜け」る。
            逆方向へ動かす/しばらく押し込まないとキャンセルして LOCAL へ戻る。
  REMOTE  — 全入力を奪って iPad へ転送。送った移動量から iPad 上のカーソル位置を
            推定し、共有エッジへ push し戻されたら LOCAL へ戻る。

このモジュールは Win32 に依存しない純粋ロジック (ユニットテスト対象)。
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
    exit_point: tuple[int, int] | None = None  # LOCAL 復帰時の PC 側カーソル位置


# エッジごとの「外向き」単位ベクトル (PC 画面から出ていく方向)
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
        self.cancel_margin = cancel_margin_px
        self.idle_cancel_ms = idle_cancel_ms

        self.state = State.LOCAL
        # PC 側エッジ範囲 (仮想スクリーン座標)。set_edge_geometry() で設定。
        self._edge_coord = 0       # エッジの固定座標 (right なら最大 x)
        self._edge_lo = 0          # エッジに沿った範囲の最小値
        self._edge_hi = 0          # 最大値
        self._push_acc = 0.0
        self._push_last_ms = 0.0
        self._entry_point = (0, 0)
        # iPad 側仮想カーソル
        self._vx = 0.0
        self._vy = 0.0
        self._return_acc = 0.0
        # スケーリングの端数繰り越し
        self._carry_x = 0.0
        self._carry_y = 0.0

    # ------------------------------------------------------------- geometry

    def set_edge_geometry(self, edge_coord: int, lo: int, hi: int) -> None:
        """エッジの位置を設定する。

        vertical エッジ (right/left) なら edge_coord=x, lo/hi=y の範囲。
        horizontal エッジ (top/bottom) なら edge_coord=y, lo/hi=x の範囲。
        """
        self._edge_coord = edge_coord
        self._edge_lo = lo
        self._edge_hi = hi

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
            # 押し込みが途切れた: 蓄積をリセット (ピン留めしたまま様子を見る)
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
        # PC から出た側の反対側のエッジから iPad に入る
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
        """共有エッジからの深さ (iPad の内側方向が正)。負ならエッジを突き抜けている。"""
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
            # 共有エッジを突き抜けた量を蓄積 (勢いよく戻せば一発で戻れる)
            self._return_acc += -depth_after + max(0.0, depth_before)
        elif depth_after > depth_before:
            self._return_acc = 0.0  # iPad の内側へ動いたらリセット

        self._vx = min(float(self.remote_w - 1), max(0.0, nx))
        self._vy = min(float(self.remote_h - 1), max(0.0, ny))

        if self._return_acc >= self.return_threshold:
            self.state = State.LOCAL
            return RemoteMotion(sdx, sdy, True, self._exit_point())
        return RemoteMotion(sdx, sdy, False)

    def force_local(self) -> tuple[int, int]:
        """フェイルセーフ (切断・ホットキー): 即座に LOCAL へ戻す。"""
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
