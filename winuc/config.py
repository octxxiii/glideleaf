"""Read and write configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class PnpId:
    vendor_id_source: int = 0x02  # USB Implementers Forum
    vendor_id: int = 0x1209       # pid.codes (VID for open source)
    product_id: int = 0x0001
    product_version: int = 0x0100


@dataclass
class Config:
    # BLE
    device_name: str = "Windows Pointer & Keyboard"
    manufacturer_name: str = "WinUC"
    # bumble transport specifier. [driver=rtk] forces the Realtek FW loader.
    transport: str = "usb:[driver=rtk]0"
    # Static random address (top 2 bits must be 11)
    address: str = "F0:F1:F2:AA:BB:CC"
    pnp: PnpId = field(default_factory=PnpId)

    # Edge / motion
    edge: str = "right"              # right | left | top | bottom
    push_threshold_px: int = 80      # Push distance required to "break through" the screen edge
    return_threshold_px: int = 80    # Push-back distance required to return from the iPad side
    speed: float = 1.0               # Multiplier for the motion sent to the iPad
    natural_scroll: bool = False     # Invert scroll direction
    ipad_screen: tuple[int, int] = (1194, 834)  # For virtual cursor estimation (pt)

    # Keyboard
    swap_alt_win: bool = False       # Swap Alt<->Win (use Alt as Cmd)
    jis_mac_style: bool = True       # 変換/無変換 → かな/英数
    release_hotkey: str = "ctrl+alt+q"  # Key to forcibly return to Windows

    # Integration with other tools (X-Mouse Button Control, etc.)
    forward_injected: bool = True    # Also forward converted events injected by other tools
    # Buttons to pass to downstream hooks (XMBC, etc.) for conversion even during REMOTE
    passthrough_buttons: tuple[str, ...] = ()  # e.g. ("x1", "x2", "middle")

    # Button-to-scroll conversion while operating the iPad (WinUC does the XMBC equivalent)
    # Values: "drag_scroll" (scroll by moving while held) | "wheel_up" | "wheel_down"
    button_actions: dict[str, str] = field(default_factory=dict)  # e.g. {"x1": "drag_scroll"}
    drag_scroll_px: int = 30         # How many pixels of movement per scroll notch
    drag_scroll_invert: bool = False # Invert drag-scroll direction

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
