from winuc import keymap


def test_letters_and_digits():
    assert keymap.scan_to_usage(0x1E, False) == 0x04  # A
    assert keymap.scan_to_usage(0x2C, False) == 0x1D  # Z
    assert keymap.scan_to_usage(0x02, False) == 0x1E  # 1
    assert keymap.scan_to_usage(0x0B, False) == 0x27  # 0


def test_modifiers():
    assert keymap.scan_to_usage(0x1D, False) == 0xE0  # LCtrl
    assert keymap.scan_to_usage(0x1D, True) == 0xE4   # RCtrl
    assert keymap.scan_to_usage(0x5B, True) == 0xE3   # LWin → LGUI (Cmd)
    assert keymap.scan_to_usage(0x38, False) == 0xE2  # LAlt → Option
    assert keymap.scan_to_usage(0x38, True) == 0xE6   # RAlt


def test_navigation_extended():
    assert keymap.scan_to_usage(0x48, True) == 0x52  # Up
    assert keymap.scan_to_usage(0x50, True) == 0x51  # Down
    assert keymap.scan_to_usage(0x53, True) == 0x4C  # Delete
    assert keymap.scan_to_usage(0x48, False) == 0x60  # KP 8 (非拡張)


def test_pause_via_vk():
    assert keymap.scan_to_usage(0x45, False, vk=0x13) == 0x48  # Pause
    assert keymap.scan_to_usage(0x45, False) == 0x53  # Num Lock


def test_jis_mac_style():
    # 変換 → かな, 無変換 → 英数
    assert keymap.scan_to_usage(0x79, False, jis_mac_style=True) == 0x90
    assert keymap.scan_to_usage(0x7B, False, jis_mac_style=True) == 0x91
    # raw モードでは International4/5
    assert keymap.scan_to_usage(0x79, False, jis_mac_style=False) == 0x8A
    assert keymap.scan_to_usage(0x7B, False, jis_mac_style=False) == 0x8B
    # ¥ と ろ は共通
    assert keymap.scan_to_usage(0x7D, False) == 0x89
    assert keymap.scan_to_usage(0x73, False) == 0x87


def test_unknown_scan_returns_none():
    assert keymap.scan_to_usage(0xFF, False) is None


def test_swap_alt_gui():
    assert keymap.swap_alt_gui(0xE2) == 0xE3
    assert keymap.swap_alt_gui(0xE3) == 0xE2
    assert keymap.swap_alt_gui(0x04) == 0x04


def test_keyboard_state_basic():
    state = keymap.KeyboardState()
    assert state.press(0xE0)  # Ctrl down
    assert state.press(0x04)  # A down
    assert state.snapshot() == (0x01, (0x04,))
    assert not state.press(0x04)  # リピートは変化なし
    assert state.release(0x04)
    assert state.release(0xE0)
    assert state.snapshot() == (0, ())


def test_keyboard_state_rollover():
    state = keymap.KeyboardState()
    for usage in range(0x04, 0x0B):  # 7キー押下 → 最古が押し出される
        state.press(usage)
    _, keys = state.snapshot()
    assert len(keys) == 6
    assert 0x04 not in keys
    assert 0x0A in keys


def test_media_vk_mapping():
    assert keymap.VK_TO_CONSUMER[0xAF] == 0x00E9  # VolUp
    assert keymap.VK_TO_CONSUMER[0xB3] == 0x00CD  # Play/Pause
