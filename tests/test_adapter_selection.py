import asyncio
import sys
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from winuc import driver
from winuc.config import Config


def radio(vid, pid, instance, service="WinUSB", container=""):
    return {"InstanceId": rf"USB\VID_{vid:04X}&PID_{pid:04X}\{instance}",
            "FriendlyName": f"Bluetooth {instance}", "Class": "Bluetooth",
            "Service": service, "ContainerId": container, "Location": instance}


INTEL = radio(0x8087, 0x0026, "port-1", "BTHUSB")
REALTEK = radio(0x0BDA, 0x8771, "port-2")


def test_identical_models_are_distinct_physical_choices():
    dongles = driver.list_dongles(devices=[REALTEK, radio(0x0BDA, 0x8771, "port-3")])
    assert len(dongles) == 2
    assert dongles[0].identity != dongles[1].identity


def test_composite_interfaces_are_grouped_without_hiding_another_adapter():
    first = {**REALTEK, "ContainerId": "first"}
    interface = {**first, "InstanceId": r"USB\VID_0BDA&PID_8771&MI_00\interface"}
    other = {**radio(0x0BDA, 0x8771, "port-3"), "ContainerId": "second"}
    assert len(driver.list_dongles(devices=[first, interface, other])) == 2


def test_transport_targets_selected_vid_pid_and_chipset():
    realtek, intel = driver.list_dongles(devices=[REALTEK, INTEL])
    assert realtek.transport == "usb:[driver=rtk]0bda:8771"
    assert intel.transport == "usb:8087:0026"
    assert not realtek.transport.endswith("]0")


def test_saved_selection_does_not_fall_back_to_other_adapter(monkeypatch):
    selected = driver.list_dongles(devices=[REALTEK])[0]
    monkeypatch.setattr(driver, "_pnp_query", lambda: [INTEL])
    with pytest.raises(RuntimeError):
        driver.require_selected_adapter(selected.identity, selected.transport)


def test_identical_vid_pid_is_rejected_before_usb_open(monkeypatch):
    selected = driver.list_dongles(devices=[REALTEK])[0]
    monkeypatch.setattr(driver, "_pnp_query", lambda: [REALTEK, radio(0x0BDA, 0x8771, "port-3")])
    with pytest.raises(RuntimeError):
        driver.require_selected_adapter(selected.identity, selected.transport)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows app")
@pytest.mark.asyncio
async def test_missing_saved_adapter_fails_before_opening_any_radio(monkeypatch):
    from winuc import app as app_module
    selected = driver.list_dongles(devices=[REALTEK])[0]
    monkeypatch.setattr(driver, "_pnp_query", lambda: [INTEL])
    opened = AsyncMock()
    monkeypatch.setattr(app_module, "open_transport", opened)
    app = app_module.UniversalControlApp(Config(adapter_id=selected.identity, transport=selected.transport))
    with pytest.raises(RuntimeError):
        await app.run(enable_capture=False)
    opened.assert_not_called()


def make_tray(tmp_path):
    from winuc.gui.tray import TrayApp
    app = TrayApp.__new__(TrayApp)
    app.config = Config()
    app.config_file = tmp_path / "config.json"
    app.service = SimpleNamespace(running=False, start=Mock(), stop=Mock())
    app._on_main = Mock()
    app._refresh_icon = Mock()
    app._settings_win = None
    return app


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop UI")
def test_list_select_apply_persists_exact_choice_and_restores_it(tmp_path, monkeypatch, desktop_root):
    import tkinter as tk
    from winuc.gui.setup_wizard import SetupWizard
    from winuc.i18n import t
    records = [INTEL, REALTEK]
    monkeypatch.setattr(driver, "_pnp_query", lambda: records)
    install = Mock()
    monkeypatch.setattr(driver, "install_winusb_elevated", install)
    app = make_tray(tmp_path)
    root = desktop_root
    wizard = SetupWizard(root, on_apply=app._apply_dongle)
    def settle():
        root.after(300, root.quit)
        root.mainloop()
    try:
        settle()
        assert len(wizard.devices.get_children()) == 2
        assert wizard._dongle is None
        assert str(wizard.apply_btn["state"]) == "disabled"
        assert not app.config_file.exists()
        wizard.devices.selection_set("1")
        settle()
        assert wizard._dongle.vidpid == (0x0BDA, 0x8771)
        assert not app.config_file.exists()  # Preview is not apply.
        wizard.apply_btn.invoke()
        settle()
        saved = Config.load(app.config_file)
        assert saved.transport == "usb:[driver=rtk]0bda:8771"
        assert saved.adapter_id == wizard._dongle.identity
        assert wizard.devices.item("1", "values")[-1] == t("적용됨")
        install.assert_not_called()  # Apply never switches a driver.
        app.service.start.assert_not_called()
        wizard._close()
        records.reverse()  # Enumeration order must not affect persisted selection.
        wizard = SetupWizard(root, on_apply=app._apply_dongle, active_adapter_id=saved.adapter_id)
        settle()
        assert wizard._dongle.identity == saved.adapter_id
        assert wizard.devices.selection() == ("0",)
        records[:] = [INTEL]
        wizard.refresh()
        settle()
        assert wizard._dongle is None
        assert str(wizard.apply_btn["state"]) == "disabled"
        assert Config.load(app.config_file).adapter_id == saved.adapter_id
    finally:
        wizard._close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop UI")
def test_connect_action_targets_preview_then_applies_and_starts(monkeypatch, desktop_root):
    import tkinter as tk
    from winuc.gui.setup_wizard import SetupWizard
    records = [INTEL, {**REALTEK, "Service": "BTHUSB"}]
    monkeypatch.setattr(driver, "_pnp_query", lambda: records)
    install, apply, ready = Mock(), Mock(), Mock()
    monkeypatch.setattr("winuc.native_driver.prepare_package", Mock())
    monkeypatch.setattr(driver, "install_winusb_elevated", install)
    monkeypatch.setattr("winuc.gui.setup_wizard.messagebox.askyesno", lambda *args, **kwargs: True)
    root = desktop_root
    wizard = SetupWizard(root, on_apply=apply, on_ready=ready)
    try:
        root.after(300, root.quit)
        root.mainloop()
        wizard.devices.selection_set("1")
        root.update()
        wizard.action_btn.invoke()
        root.after(300, root.quit)
        root.mainloop()
        install.assert_called_once_with(0x0BDA, 0x8771, adapter_id=wizard._dongle.identity)
        apply.assert_called_once()
        ready.assert_called_once()
    finally:
        wizard._close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows app")
def test_apply_stops_old_session_but_does_not_start_non_winusb_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "_pnp_query", lambda: [INTEL, REALTEK])
    app = make_tray(tmp_path)
    app.service.running = True
    app.service.stop.side_effect = lambda: setattr(app.service, "running", False)
    selected = driver.list_dongles(devices=[INTEL])[0]
    app._apply_dongle(selected)
    app.service.stop.assert_called_once()
    app.service.start.assert_not_called()
    assert Config.load(app.config_file).transport == "usb:8087:0026"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows app")
def test_apply_save_failure_preserves_config_and_restores_previous_session(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "_pnp_query", lambda: [REALTEK])
    app = make_tray(tmp_path)
    previous = replace(app.config)
    app.config.save(app.config_file)
    original = app.config_file.read_bytes()
    app.service.running = True
    app.service.stop.side_effect = lambda: setattr(app.service, "running", False)
    monkeypatch.setattr(Config, "save", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        app._apply_dongle(driver.list_dongles(devices=[REALTEK])[0])
    assert app.config == previous
    assert app.config_file.read_bytes() == original
    app.service.start.assert_called_once_with(previous)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows app")
def test_apply_restarts_active_session_on_the_selected_winusb_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "_pnp_query", lambda: [INTEL, REALTEK])
    app = make_tray(tmp_path)
    app.service.running = True
    app.service.stop.side_effect = lambda: setattr(app.service, "running", False)
    selected = driver.list_dongles(devices=[REALTEK])[0]
    app._apply_dongle(selected)
    app.service.stop.assert_called_once()
    app.service.start.assert_called_once_with(app.config)
    assert app.config.adapter_id == selected.identity
    assert app.config.transport == selected.transport


@pytest.mark.skipif(sys.platform != "win32", reason="Windows app")
def test_stop_failure_does_not_commit_a_different_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "_pnp_query", lambda: [REALTEK])
    app = make_tray(tmp_path)
    previous = replace(app.config)
    app.service.running = True  # Simulate a worker that cannot stop yet.
    with pytest.raises(RuntimeError):
        app._apply_dongle(driver.list_dongles(devices=[REALTEK])[0])
    assert app.config == previous
    assert not app.config_file.exists()
    app.service.start.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows app")
def test_gui_start_opens_picker_instead_of_default_usb_index(tmp_path):
    app = make_tray(tmp_path)
    app._open_wizard = Mock()
    app._toggle_running()
    app._open_wizard.assert_called_once()
    app.service.start.assert_not_called()
    # An explicit legacy/manual transport is still an intentional user choice.
    app.config.transport = "usb:1234:5678"
    app._toggle_running()
    app.service.start.assert_called_once_with(app.config)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows app")
@pytest.mark.parametrize("service", ["BTHUSB", "WinUSB", "missing"])
def test_start_checks_selected_csr_before_starting_ble(tmp_path, monkeypatch, service):
    csr = radio(0x0A12, 0x0001, "csr-port", "BTHUSB")
    selected = driver.list_dongles(devices=[csr])[0]
    app = make_tray(tmp_path)
    app.config = replace(app.config, adapter_id=selected.identity, transport=selected.transport)
    app._open_wizard = Mock()
    monkeypatch.setattr(driver, "_pnp_query", lambda: (
        [] if service == "missing" else [{**csr, "Service": service}]))
    info = Mock()
    monkeypatch.setattr("winuc.gui.tray.messagebox.showinfo", info)
    app.root = Mock()
    app._toggle_running()
    if service == "WinUSB":
        app.service.start.assert_called_once_with(app.config)
        app._open_wizard.assert_not_called()
    else:
        app.service.start.assert_not_called()
        app._open_wizard.assert_called_once()
        # Execute queued UI work on the UI side, as production does.
        for call in app._on_main.call_args_list:
            call.args[0]()
        info.assert_called_once()
        if service == "BTHUSB":
            assert "WinUSB" in info.call_args.args[1]


@pytest.mark.parametrize("failure", ["package", "save"])
def test_connect_failure_never_installs_or_starts(monkeypatch, desktop_root, failure):
    from winuc.gui.setup_wizard import SetupWizard
    monkeypatch.setattr(driver, "_pnp_query", lambda: [INTEL])
    preflight = Mock(side_effect=RuntimeError("untrusted") if failure == "package" else None)
    monkeypatch.setattr("winuc.native_driver.prepare_package", preflight)
    monkeypatch.setattr("winuc.gui.setup_wizard.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("winuc.gui.setup_wizard.messagebox.showerror", Mock())
    install, ready, prepare = Mock(), Mock(), Mock()
    apply = Mock(side_effect=OSError("disk full") if failure == "save" else None)
    monkeypatch.setattr(driver, "install_winusb_elevated", install)
    wizard = SetupWizard(desktop_root, on_apply=apply, on_ready=ready, prepare_driver=prepare)
    def settle():
        desktop_root.after(300, desktop_root.quit)
        desktop_root.mainloop()
    try:
        settle()
        wizard.devices.selection_set("0")
        desktop_root.update()
        wizard.action_btn.invoke()
        settle()
        install.assert_not_called()
        ready.assert_not_called()
        if failure == "package":
            prepare.assert_not_called()
            apply.assert_not_called()
        else:
            apply.assert_called_once()
    finally:
        wizard._close()
