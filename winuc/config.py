"""設定の読み書き。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class PnpId:
    vendor_id_source: int = 0x02  # USB Implementers Forum
    vendor_id: int = 0x1209       # pid.codes (オープンソース用 VID)
    product_id: int = 0x0001
    product_version: int = 0x0100


@dataclass
class Config:
    # BLE
    device_name: str = "Windows Pointer & Keyboard"
    manufacturer_name: str = "WinUC"
    # bumble のトランスポート指定。[driver=rtk] で Realtek FW ローダを強制。
    transport: str = "usb:[driver=rtk]0"
    # 静的ランダムアドレス (先頭2bit が 11 であること)
    address: str = "F0:F1:F2:AA:BB:CC"
    pnp: PnpId = field(default_factory=PnpId)

    # エッジ / 移動
    edge: str = "right"              # right | left | top | bottom
    push_threshold_px: int = 80      # 画面端を「突き抜ける」のに必要な押し込み量
    return_threshold_px: int = 80    # iPad 側から戻るのに必要な押し戻し量
    speed: float = 1.0               # iPad へ送る移動量の倍率
    natural_scroll: bool = False     # スクロール方向反転
    ipad_screen: tuple[int, int] = (1194, 834)  # 仮想カーソル推定用 (pt)

    # キーボード
    swap_alt_win: bool = False       # Alt⇔Win を入れ替え (Alt を Cmd として使う)
    jis_mac_style: bool = True       # 変換/無変換 → かな/英数
    release_hotkey: str = "ctrl+alt+q"  # 強制的に Windows へ戻るキー

    # 他ツール連携 (X-Mouse Button Control 等)
    forward_injected: bool = True    # 他ツールが注入した変換後イベントも転送する
    # REMOTE 中も下流のフック (XMBC 等) へ渡して変換させるボタン
    passthrough_buttons: tuple[str, ...] = ()  # 例: ("x1", "x2", "middle")

    # iPad 操作中のボタン→スクロール変換 (XMBC 相当を WinUC 側で行う)
    # 値: "drag_scroll" (押しながら移動でスクロール) | "wheel_up" | "wheel_down"
    button_actions: dict[str, str] = field(default_factory=dict)  # 例: {"x1": "drag_scroll"}
    drag_scroll_px: int = 30         # 何ピクセルの移動で 1 ノッチスクロールするか
    drag_scroll_invert: bool = False # ドラッグスクロールの方向反転

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path)
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        pnp = PnpId(**data.pop("pnp", {}))
        ipad_screen = tuple(data.pop("ipad_screen", (1194, 834)))
        if "passthrough_buttons" in data:
            data["passthrough_buttons"] = tuple(data["passthrough_buttons"])
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(pnp=pnp, ipad_screen=ipad_screen, **known)

    def save(self, path: str | Path) -> None:
        data = asdict(self)
        Path(path).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
