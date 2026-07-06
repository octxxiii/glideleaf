"""HID レポートマップとレポートのパッキング。

構成 (1つの HID サービスに 3 レポート):
  Report ID 1: キーボード (8バイト: modifiers, reserved, key1..key6) + LED 出力
  Report ID 2: コンシューマ (2バイト: 16bit usage, 0 で解放)
  Report ID 3: マウス (7バイト: buttons, dx16, dy16, wheel8, hwheel8)

BLE では Report ID は Report Reference ディスクリプタで伝えるため、
notify のペイロードに ID バイトは含めない。
"""

from __future__ import annotations

import struct

REPORT_ID_KEYBOARD = 1
REPORT_ID_CONSUMER = 2
REPORT_ID_MOUSE = 3

KEYBOARD_REPORT_SIZE = 8
CONSUMER_REPORT_SIZE = 2
MOUSE_REPORT_SIZE = 7

# HID Information: bcdHID=1.11, bCountryCode=15 (Japan), Flags=RemoteWake|NormallyConnectable
HID_INFORMATION = bytes([0x11, 0x01, 0x0F, 0x03])

# fmt: off
REPORT_MAP = bytes([
    # ---------- Keyboard (Report ID 1) ----------
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x06,        # Usage (Keyboard)
    0xA1, 0x01,        # Collection (Application)
    0x85, REPORT_ID_KEYBOARD,  # . Report ID (1)
    0x05, 0x07,        # . Usage Page (Keyboard/Keypad)
    0x19, 0xE0,        # . Usage Minimum (LeftControl)
    0x29, 0xE7,        # . Usage Maximum (Right GUI)
    0x15, 0x00,        # . Logical Minimum (0)
    0x25, 0x01,        # . Logical Maximum (1)
    0x75, 0x01,        # . Report Size (1)
    0x95, 0x08,        # . Report Count (8)
    0x81, 0x02,        # . Input (Data, Var, Abs)     ; modifier bits
    0x75, 0x08,        # . Report Size (8)
    0x95, 0x01,        # . Report Count (1)
    0x81, 0x01,        # . Input (Const)              ; reserved byte
    0x05, 0x08,        # . Usage Page (LEDs)
    0x19, 0x01,        # . Usage Minimum (Num Lock)
    0x29, 0x05,        # . Usage Maximum (Kana)
    0x75, 0x01,        # . Report Size (1)
    0x95, 0x05,        # . Report Count (5)
    0x91, 0x02,        # . Output (Data, Var, Abs)    ; LED bits
    0x75, 0x03,        # . Report Size (3)
    0x95, 0x01,        # . Report Count (1)
    0x91, 0x01,        # . Output (Const)             ; LED padding
    0x05, 0x07,        # . Usage Page (Keyboard/Keypad)
    0x19, 0x00,        # . Usage Minimum (0)
    0x29, 0xFF,        # . Usage Maximum (255)
    0x15, 0x00,        # . Logical Minimum (0)
    0x26, 0xFF, 0x00,  # . Logical Maximum (255)
    0x75, 0x08,        # . Report Size (8)
    0x95, 0x06,        # . Report Count (6)
    0x81, 0x00,        # . Input (Data, Array)        ; 6KRO keys
    0xC0,              # End Collection

    # ---------- Consumer Control (Report ID 2) ----------
    0x05, 0x0C,        # Usage Page (Consumer)
    0x09, 0x01,        # Usage (Consumer Control)
    0xA1, 0x01,        # Collection (Application)
    0x85, REPORT_ID_CONSUMER,  # . Report ID (2)
    0x15, 0x00,        # . Logical Minimum (0)
    0x26, 0xFF, 0x03,  # . Logical Maximum (0x3FF)
    0x19, 0x00,        # . Usage Minimum (0)
    0x2A, 0xFF, 0x03,  # . Usage Maximum (0x3FF)
    0x75, 0x10,        # . Report Size (16)
    0x95, 0x01,        # . Report Count (1)
    0x81, 0x00,        # . Input (Data, Array)        ; 16bit usage ID
    0xC0,              # End Collection

    # ---------- Mouse (Report ID 3) ----------
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x85, REPORT_ID_MOUSE,  # . Report ID (3)
    0x09, 0x01,        # . Usage (Pointer)
    0xA1, 0x00,        # . Collection (Physical)
    0x05, 0x09,        # .. Usage Page (Buttons)
    0x19, 0x01,        # .. Usage Minimum (1)
    0x29, 0x05,        # .. Usage Maximum (5)
    0x15, 0x00,        # .. Logical Minimum (0)
    0x25, 0x01,        # .. Logical Maximum (1)
    0x75, 0x01,        # .. Report Size (1)
    0x95, 0x05,        # .. Report Count (5)
    0x81, 0x02,        # .. Input (Data, Var, Abs)    ; button bits
    0x75, 0x03,        # .. Report Size (3)
    0x95, 0x01,        # .. Report Count (1)
    0x81, 0x01,        # .. Input (Const)             ; padding
    0x05, 0x01,        # .. Usage Page (Generic Desktop)
    0x09, 0x30,        # .. Usage (X)
    0x09, 0x31,        # .. Usage (Y)
    0x16, 0x01, 0x80,  # .. Logical Minimum (-32767)
    0x26, 0xFF, 0x7F,  # .. Logical Maximum (32767)
    0x75, 0x10,        # .. Report Size (16)
    0x95, 0x02,        # .. Report Count (2)
    0x81, 0x06,        # .. Input (Data, Var, Rel)    ; dx, dy
    0x09, 0x38,        # .. Usage (Wheel)
    0x15, 0x81,        # .. Logical Minimum (-127)
    0x25, 0x7F,        # .. Logical Maximum (127)
    0x75, 0x08,        # .. Report Size (8)
    0x95, 0x01,        # .. Report Count (1)
    0x81, 0x06,        # .. Input (Data, Var, Rel)    ; vertical wheel
    0x05, 0x0C,        # .. Usage Page (Consumer)
    0x0A, 0x38, 0x02,  # .. Usage (AC Pan)
    0x15, 0x81,        # .. Logical Minimum (-127)
    0x25, 0x7F,        # .. Logical Maximum (127)
    0x75, 0x08,        # .. Report Size (8)
    0x95, 0x01,        # .. Report Count (1)
    0x81, 0x06,        # .. Input (Data, Var, Rel)    ; horizontal wheel
    0xC0,              # . End Collection
    0xC0,              # End Collection
])
# fmt: on


def _clamp(value: int, lo: int, hi: int) -> int:
    return lo if value < lo else hi if value > hi else value


def mouse_report(
    buttons: int, dx: int, dy: int, wheel: int = 0, hwheel: int = 0
) -> bytes:
    """buttons: bit0=左, bit1=右, bit2=中, bit3=X1, bit4=X2"""
    return struct.pack(
        "<Bhhbb",
        buttons & 0x1F,
        _clamp(dx, -32767, 32767),
        _clamp(dy, -32767, 32767),
        _clamp(wheel, -127, 127),
        _clamp(hwheel, -127, 127),
    )


def keyboard_report(modifiers: int, keys: tuple[int, ...] = ()) -> bytes:
    """modifiers: HID modifier ビットマスク、keys: 押下中の usage 最大6個。"""
    padded = (tuple(keys) + (0,) * 6)[:6]
    return struct.pack("<BB6B", modifiers & 0xFF, 0, *padded)


KEYBOARD_RELEASE_ALL = keyboard_report(0)


def consumer_report(usage: int) -> bytes:
    """usage: Consumer page の usage ID (0 で全解放)。"""
    return struct.pack("<H", usage & 0x3FF)


MOUSE_RELEASE_ALL = mouse_report(0, 0, 0)
CONSUMER_RELEASE = consumer_report(0)
