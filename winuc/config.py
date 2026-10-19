"""Read and write configuration."""

from __future__ import annotations

from .i18n import t

import json
import math
import os
import re
import tempfile
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
    language: str = "auto"  # UI preference; independent of keyboard layout.
    # BLE
    device_name: str = "Windows Pointer & Keyboard"
    manufacturer_name: str = "Glideleaf"
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

    def validate(self) -> None:
        """Reject settings that can break motion or the emergency return key."""
        from .i18n import LANGUAGES
        if self.language not in LANGUAGES:
            raise ValueError(t("지원하지 않는 언어입니다."))
        if self.edge not in ("right", "left", "top", "bottom"):
            raise ValueError(t("iPad 방향을 선택해 주세요."))
        if not isinstance(self.speed, (int, float)) or not math.isfinite(self.speed) or not 0.2 <= self.speed <= 5:
            raise ValueError(t("포인터 속도는 0.2~5 사이여야 합니다."))
        for name in ("push_threshold_px", "return_threshold_px", "drag_scroll_px"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 1000:
                raise ValueError(t("{name}: 1~1000 사이의 정수를 입력해 주세요.", name=name))
        if len(self.ipad_screen) != 2 or any(type(v) is not int or not 1 <= v <= 10000 for v in self.ipad_screen):
            raise ValueError(t("iPad 화면 크기는 1~10000 사이의 정수여야 합니다."))
        if not isinstance(self.device_name, str) or not self.device_name.strip():
            raise ValueError(t("블루투스 이름을 입력해 주세요."))
        if not isinstance(self.transport, str) or not self.transport.strip():
            raise ValueError(t("동글 연결 경로를 입력해 주세요."))
        if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", self.address) or int(self.address[:2], 16) & 0xC0 != 0xC0:
            raise ValueError(t("유효한 Static Random BLE 주소를 입력해 주세요."))
        if not re.fullmatch(r"(?i)(?:(?:ctrl|alt|shift|win)\+)+[a-z0-9]", self.release_hotkey):
            raise ValueError(t("복귀 단축키는 ctrl+alt+q처럼 보조키와 영문 또는 숫자를 사용해 주세요."))
        if any(k not in ("x1", "x2", "middle") or v not in ("drag_scroll", "wheel_up", "wheel_down") for k, v in self.button_actions.items()):
            raise ValueError(t("마우스 버튼 동작이 올바르지 않습니다."))

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
        config = cls(pnp=pnp, ipad_screen=ipad_screen, **known)
        config.validate()
        return config

    def save(self, path: str | Path) -> None:
        self.validate()
        data = asdict(self)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Replace only after the complete file has reached disk.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(data, indent=2, ensure_ascii=False))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
