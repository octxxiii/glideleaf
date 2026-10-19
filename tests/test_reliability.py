import asyncio
import threading
from unittest.mock import AsyncMock

import pytest

from winuc.config import Config


@pytest.mark.parametrize("values", [
    {"speed": float("nan")}, {"speed": -1}, {"edge": "invalid"},
    {"ipad_screen": (0, 834)}, {"release_hotkey": "ctrl+escape"},
    {"release_hotkey": "q"}, {"address": "00:11:22:33:44:55"},
    {"button_actions": {"x1": "bad"}}, {"drag_scroll_px": 0},
])
def test_invalid_config_preserves_previous_file(tmp_path, values):
    path = tmp_path / "config.json"
    Config().save(path)
    original = path.read_bytes()
    with pytest.raises(ValueError):
        Config(**values).save(path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_service_constructor_failure_surfaces_error(monkeypatch):
    from winuc import service
    def fail(*args, **kwargs):
        raise RuntimeError("test constructor failure")
    monkeypatch.setattr(service, "UniversalControlApp", fail)
    svc = service.Service()
    svc.start(Config())
    svc._thread.join(2)
    assert not svc.running
    assert svc.status == "error"
    assert "constructor failure" in svc.last_error


def test_stop_timeout_keeps_worker_and_prevents_duplicate_start(monkeypatch):
    from winuc import service
    entered, finish = threading.Event(), threading.Event()
    class App:
        def __init__(self, *args, **kwargs):
            pass
        async def run(self, **kwargs):
            entered.set()
            while not finish.is_set():
                await asyncio.sleep(0.01)
        def request_stop(self):
            pass
    monkeypatch.setattr(service, "UniversalControlApp", App)
    svc = service.Service()
    svc.start(Config())
    try:
        assert entered.wait(2)
        worker = svc._thread
        svc.stop(timeout=0.01)
        assert svc.running
        assert svc.status == "error"
        svc.start(Config())
        assert svc._thread is worker
    finally:
        finish.set()
        svc.stop(timeout=2)
    assert not svc.running


@pytest.mark.asyncio
async def test_return_clears_scroll_and_pressed_keys():
    from winuc.app import UniversalControlApp
    app = UniversalControlApp(Config())
    app.peripheral.release_all = AsyncMock()
    app.keyboard_state.press(4)
    app._buttons = 1
    app._consumer_down = 0xE9
    app._wheel_acc = 0.7
    app._hwheel_acc = -0.5
    app._drag_buttons.add(3)
    await app._handle_state("local")
    assert app.keyboard_state.snapshot() == (0, ())
    assert app._wheel_acc == app._hwheel_acc == app._buttons == 0
    assert app._consumer_down is None
    assert not app._drag_buttons
    app.peripheral.release_all.assert_awaited_once()
