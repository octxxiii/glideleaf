"""Tests for v2 additions: config round-trip, service lifecycle, driver parsing."""

import sys

import pytest

from winuc.config import Config


def test_config_roundtrip_new_fields(tmp_path):
    path = tmp_path / "c.json"
    c = Config()
    c.button_actions = {"x1": "drag_scroll"}
    c.passthrough_buttons = ("x2",)
    c.drag_scroll_px = 25
    c.forward_injected = False
    c.save(path)

    loaded = Config.load(path)
    assert loaded.button_actions == {"x1": "drag_scroll"}
    assert loaded.passthrough_buttons == ("x2",)
    assert loaded.drag_scroll_px == 25
    assert loaded.forward_injected is False
    assert isinstance(loaded.ipad_screen, tuple)


def test_config_load_missing_returns_defaults(tmp_path):
    c = Config.load(tmp_path / "does_not_exist.json")
    assert c.edge == "right"
    assert c.button_actions == {}


def test_service_lifecycle_no_leak():
    """start() then stop() must join the worker thread and end in STOPPED."""
    from winuc.config import Config
    from winuc import service as service_mod
    from winuc.service import Service, STATUS_STOPPED

    # Stub the app so no real BLE transport is opened.
    import threading

    class FakeApp:
        def __init__(self, *a, **k):
            self.on_status = None
            self._stop = threading.Event()

        async def run(self, enable_capture=True):
            import asyncio

            if self.on_status:
                self.on_status("advertising")
            # Wait until request_stop sets the event.
            while not self._stop.is_set():
                await asyncio.sleep(0.02)

        def request_stop(self):
            self._stop.set()

    original = service_mod.UniversalControlApp
    service_mod.UniversalControlApp = FakeApp
    try:
        svc = Service()
        statuses = []
        svc.on_status_change = statuses.append
        svc.start(Config())
        # Give the worker a moment to reach 'advertising'.
        import time

        for _ in range(100):
            if svc.status == "advertising":
                break
            time.sleep(0.02)
        assert svc.running
        svc.stop(timeout=3)
        assert not svc.running
        assert svc.status == STATUS_STOPPED
    finally:
        service_mod.UniversalControlApp = original


def test_driver_vidpid_regex():
    from winuc.driver import _VIDPID_RE

    m = _VIDPID_RE.match(r"USB\VID_0411&PID_0374\00E04C239987")
    assert m and int(m.group(1), 16) == 0x0411 and int(m.group(2), 16) == 0x0374
    assert _VIDPID_RE.match(r"HID\SOMETHING") is None


def test_driver_dongle_label():
    from winuc.driver import Dongle

    known = Dongle(0x0411, 0x0374, "id", "Generic", "winusb")
    assert "RTL8761B" in known.label
    assert known.is_winusb
    unknown = Dongle(0x1234, 0x5678, "id", "My Radio", "inbox")
    assert unknown.label == "My Radio"


@pytest.mark.skipif(sys.platform != "win32", reason="autostart is Windows-only")
def test_autostart_roundtrip():
    from winuc import autostart

    was = autostart.is_enabled()
    try:
        autostart.enable()
        assert autostart.is_enabled()
        autostart.disable()
        assert not autostart.is_enabled()
    finally:
        autostart.set_enabled(was)
