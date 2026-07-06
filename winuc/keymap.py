"""Convert Windows key input -> USB HID usage.

Treats the Set-1 scan code + extended flag obtained from the
low-level keyboard hook (WH_KEYBOARD_LL) as the physical-key identifier,
and converts it to a usage on the HID Keyboard/Keypad usage page (0x07).
(VK codes are layout-dependent so we avoid them, except media keys, etc., which are matched by VK.)

Modifier interpretation on the iPad side: GUI(Win) = Cmd, Alt = Option, Ctrl = Ctrl.
"""

from __future__ import annotations

# --- HID modifier usages (0xE0-0xE7) → modifier bits ---
MODIFIER_USAGES = {
    0xE0: 0x01,  # Left Control
    0xE1: 0x02,  # Left Shift
    0xE2: 0x04,  # Left Alt (iPad: Option)
    0xE3: 0x08,  # Left GUI (iPad: Command)
    0xE4: 0x10,  # Right Control
    0xE5: 0x20,  # Right Shift
    0xE6: 0x40,  # Right Alt
    0xE7: 0x80,  # Right GUI
}

# --- Set-1 scan codes (non-extended) → HID usage ---
_BASE = {
    0x01: 0x29,  # Esc
    0x02: 0x1E, 0x03: 0x1F, 0x04: 0x20, 0x05: 0x21, 0x06: 0x22,  # 1-5
    0x07: 0x23, 0x08: 0x24, 0x09: 0x25, 0x0A: 0x26, 0x0B: 0x27,  # 6-0
    0x0C: 0x2D,  # - =
    0x0D: 0x2E,  # = ^ (JIS)
    0x0E: 0x2A,  # Backspace
    0x0F: 0x2B,  # Tab
    0x10: 0x14, 0x11: 0x1A, 0x12: 0x08, 0x13: 0x15, 0x14: 0x17,  # QWERT
    0x15: 0x1C, 0x16: 0x18, 0x17: 0x0C, 0x18: 0x12, 0x19: 0x13,  # YUIOP
    0x1A: 0x2F,  # [ (JIS: @)
    0x1B: 0x30,  # ] (JIS: [)
    0x1C: 0x28,  # Enter
    0x1D: 0xE0,  # Left Ctrl
    0x1E: 0x04, 0x1F: 0x16, 0x20: 0x07, 0x21: 0x09, 0x22: 0x0A,  # ASDFG
    0x23: 0x0B, 0x24: 0x0D, 0x25: 0x0E, 0x26: 0x0F,              # HJKL
    0x27: 0x33,  # ;
    0x28: 0x34,  # ' (JIS: :)
    0x29: 0x35,  # ` (JIS: 半角/全角)
    0x2A: 0xE1,  # Left Shift
    0x2B: 0x31,  # \ (JIS: ])
    0x2C: 0x1D, 0x2D: 0x1B, 0x2E: 0x06, 0x2F: 0x19, 0x30: 0x05,  # ZXCVB
    0x31: 0x11, 0x32: 0x10,                                       # NM
    0x33: 0x36,  # ,
    0x34: 0x37,  # .
    0x35: 0x38,  # /
    0x36: 0xE5,  # Right Shift
    0x37: 0x55,  # Keypad *
    0x38: 0xE2,  # Left Alt
    0x39: 0x2C,  # Space
    0x3A: 0x39,  # Caps Lock (JIS: 英数)
    0x3B: 0x3A, 0x3C: 0x3B, 0x3D: 0x3C, 0x3E: 0x3D, 0x3F: 0x3E,  # F1-F5
    0x40: 0x3F, 0x41: 0x40, 0x42: 0x41, 0x43: 0x42, 0x44: 0x43,  # F6-F10
    0x45: 0x53,  # Num Lock
    0x46: 0x47,  # Scroll Lock
    0x47: 0x5F, 0x48: 0x60, 0x49: 0x61,  # KP 7 8 9
    0x4A: 0x56,                          # KP -
    0x4B: 0x5C, 0x4C: 0x5D, 0x4D: 0x5E,  # KP 4 5 6
    0x4E: 0x57,                          # KP +
    0x4F: 0x59, 0x50: 0x5A, 0x51: 0x5B,  # KP 1 2 3
    0x52: 0x62,  # KP 0
    0x53: 0x63,  # KP .
    0x56: 0x64,  # Non-US \ (ISO 102nd key)
    0x57: 0x44,  # F11
    0x58: 0x45,  # F12
    0x59: 0x67,  # KP =
    0x64: 0x68, 0x65: 0x69, 0x66: 0x6A, 0x67: 0x6B, 0x68: 0x6C,  # F13-F17
    0x69: 0x6D, 0x6A: 0x6E, 0x6B: 0x6F, 0x6C: 0x70, 0x6D: 0x71,  # F18-F22
    0x6E: 0x72, 0x76: 0x73,                                       # F23, F24
    # --- JIS (OADG109) ---
    0x70: 0x88,  # ひらがな/カタカナ (Hiragana/Katakana) → International2
    0x73: 0x87,  # ろ (\_) → International1
    0x79: 0x8A,  # 変換 (Convert) → International4
    0x7B: 0x8B,  # 無変換 (Non-convert) → International5
    0x7D: 0x89,  # ¥ → International3
}

# --- Set-1 scan codes (E0 extended) → HID usage ---
_EXTENDED = {
    0x1C: 0x58,  # Keypad Enter
    0x1D: 0xE4,  # Right Ctrl
    0x35: 0x54,  # Keypad /
    0x37: 0x46,  # Print Screen
    0x38: 0xE6,  # Right Alt
    0x47: 0x4A,  # Home
    0x48: 0x52,  # Up
    0x49: 0x4B,  # Page Up
    0x4B: 0x50,  # Left
    0x4D: 0x4F,  # Right
    0x4F: 0x4D,  # End
    0x50: 0x51,  # Down
    0x51: 0x4E,  # Page Down
    0x52: 0x49,  # Insert
    0x53: 0x4C,  # Delete
    0x5B: 0xE3,  # Left Win → Left GUI (Cmd)
    0x5C: 0xE7,  # Right Win → Right GUI
    0x5D: 0x65,  # Menu → Application
}

# --- Mapping to make JIS keys Mac-style (かな/英数) ---
# Apple's JIS keyboard sends Lang1(かな)=0x90 / Lang2(英数)=0x91.
JIS_MAC_STYLE = {
    0x8A: 0x90,  # 変換 → かな (Lang1)
    0x8B: 0x91,  # 無変換 → 英数 (Lang2)
    0x88: 0x90,  # ひらがな/カタカナ → かな (Lang1)
}

# --- Media keys, etc.: VK code → Consumer page usage ---
VK_TO_CONSUMER = {
    0xAD: 0x00E2,  # VK_VOLUME_MUTE
    0xAE: 0x00EA,  # VK_VOLUME_DOWN
    0xAF: 0x00E9,  # VK_VOLUME_UP
    0xB0: 0x00B5,  # VK_MEDIA_NEXT_TRACK
    0xB1: 0x00B6,  # VK_MEDIA_PREV_TRACK
    0xB2: 0x00B7,  # VK_MEDIA_STOP
    0xB3: 0x00CD,  # VK_MEDIA_PLAY_PAUSE
}

# Consumer usage: Globe key (AC Next Keyboard Layout Select)
CONSUMER_GLOBE = 0x029D


def scan_to_usage(
    scan: int,
    extended: bool,
    vk: int = 0,
    jis_mac_style: bool = True,
) -> int | None:
    """Convert a Set-1 scan code to a HID usage. None if unknown.

    The Pause key arrives at the LL hook with an E1 prefix as vk=VK_PAUSE,
    scan=0x45 (non-extended), so it is special-cased by VK.
    """
    if vk == 0x13:  # VK_PAUSE
        return 0x48
    usage = (_EXTENDED if extended else _BASE).get(scan)
    if usage is not None and jis_mac_style:
        usage = JIS_MAC_STYLE.get(usage, usage)
    return usage


def swap_alt_gui(usage: int) -> int:
    """Swap Alt and GUI(Win) (an option for fingers used to the Mac layout)."""
    return {0xE2: 0xE3, 0xE3: 0xE2, 0xE6: 0xE7, 0xE7: 0xE6}.get(usage, usage)


class KeyboardState:
    """Track pressed keys/modifiers and build the contents of the 8-byte report."""

    def __init__(self) -> None:
        self.modifiers = 0
        self.keys: list[int] = []  # Non-modifier usages in press order (6KRO)

    def press(self, usage: int) -> bool:
        """Update state. True if the report contents changed."""
        if usage in MODIFIER_USAGES:
            bit = MODIFIER_USAGES[usage]
            if self.modifiers & bit:
                return False
            self.modifiers |= bit
            return True
        if usage in self.keys:
            return False  # Key repeat is not sent over HID (the host handles it)
        if len(self.keys) >= 6:
            self.keys.pop(0)
        self.keys.append(usage)
        return True

    def release(self, usage: int) -> bool:
        if usage in MODIFIER_USAGES:
            bit = MODIFIER_USAGES[usage]
            if not (self.modifiers & bit):
                return False
            self.modifiers &= ~bit
            return True
        if usage in self.keys:
            self.keys.remove(usage)
            return True
        return False

    def clear(self) -> None:
        self.modifiers = 0
        self.keys.clear()

    def snapshot(self) -> tuple[int, tuple[int, ...]]:
        return self.modifiers, tuple(self.keys)
