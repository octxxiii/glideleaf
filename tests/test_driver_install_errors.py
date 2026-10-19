from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import json
import sys

import pytest

from winuc import driver, native_driver, inbox_driver


@pytest.fixture
def selected(monkeypatch):
    dongle = driver.Dongle(0x0A12, 1, r"USB\VID_0A12&PID_0001\csr-port", "CSR", "inbox")
    monkeypatch.setattr(driver, "list_dongles", lambda: [dongle])
    monkeypatch.setattr(driver, "is_admin", lambda: False)
    return dongle


def test_missing_signed_package_stops_before_uac(monkeypatch, selected):
    monkeypatch.setattr(inbox_driver, "probe", Mock(side_effect=RuntimeError("inbox driver unavailable")))
    elevate = Mock()
    monkeypatch.setattr(driver, "_relaunch_elevated", elevate)
    with pytest.raises(RuntimeError, match="inbox driver unavailable"):
        driver.install_winusb_elevated(selected.vid, selected.pid, adapter_id=selected.identity)
    elevate.assert_not_called()


def test_native_install_uses_only_applied_identity_and_verifies_binding(monkeypatch, selected):
    monkeypatch.setattr(inbox_driver, "probe", Mock())
    def elevate(args):
        assert "--driver-install" in args
        assert args[args.index("--adapter-id") + 1] == selected.identity
        assert not any("zadig" in value.lower() for value in args)
        monkeypatch.setattr(driver, "list_dongles", lambda: [replace(selected, driver="winusb")])
        return 0
    monkeypatch.setattr(driver, "_relaunch_elevated", elevate)
    driver.install_winusb_elevated(selected.vid, selected.pid, adapter_id=selected.identity)


def test_native_failure_returns_exact_child_detail(monkeypatch, selected):
    monkeypatch.setattr(inbox_driver, "probe", Mock())
    def elevate(args):
        Path(args[args.index("--driver-result") + 1]).write_text(json.dumps({
            "operation": "install", "adapter_id": selected.identity, "error": "Windows denied installation",
        }), encoding="utf-8")
        return 1
    from pathlib import Path
    monkeypatch.setattr(driver, "_relaunch_elevated", elevate)
    with pytest.raises(RuntimeError, match="Windows denied installation"):
        driver.install_winusb_elevated(selected.vid, selected.pid)


def test_process_success_without_winusb_is_not_install_success(monkeypatch, selected):
    monkeypatch.setattr(inbox_driver, "probe", Mock())
    monkeypatch.setattr(driver, "_relaunch_elevated", lambda args: 0)
    with pytest.raises(RuntimeError):
        driver.install_winusb_elevated(selected.vid, selected.pid)


def test_reboot_requirement_survives_elevation(monkeypatch, selected):
    monkeypatch.setattr(inbox_driver, "probe", Mock())
    monkeypatch.setattr(driver, "_relaunch_elevated", lambda args: native_driver.REBOOT_EXIT_CODE)
    with pytest.raises(native_driver.RebootRequired):
        driver.install_winusb_elevated(selected.vid, selected.pid)


def test_missing_exact_target_never_calls_native_update(monkeypatch, selected):
    monkeypatch.setattr(driver, "is_admin", lambda: True)
    monkeypatch.setattr(inbox_driver, "probe", Mock())
    monkeypatch.setattr(driver, "list_dongles", lambda: [replace(selected, instance_id="another-port")])
    update = Mock()
    monkeypatch.setattr(inbox_driver, "install", update)
    with pytest.raises(RuntimeError):
        driver.install_winusb(selected.vid, selected.pid, adapter_id=selected.identity)
    update.assert_not_called()


def test_duplicate_hardware_id_never_calls_native_update(monkeypatch, selected):
    monkeypatch.setattr(driver, "is_admin", lambda: True)
    monkeypatch.setattr(inbox_driver, "probe", Mock())
    monkeypatch.setattr(driver, "list_dongles", lambda: [selected, replace(selected, instance_id="duplicate")])
    update = Mock()
    monkeypatch.setattr(inbox_driver, "install", update)
    with pytest.raises(RuntimeError):
        driver.install_winusb(selected.vid, selected.pid, adapter_id=selected.identity)
    update.assert_not_called()


def test_windowless_driver_failure_is_logged_and_reported(monkeypatch, selected, tmp_path):
    import tempfile
    from winuc import __main__ as cli
    setup, logger = Mock(), Mock()
    monkeypatch.setattr(cli, "_setup_logging", setup)
    monkeypatch.setattr(cli, "logging", SimpleNamespace(getLogger=lambda name: logger))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    folder = tmp_path / "glideleaf-driver-test"
    folder.mkdir()
    result = folder / "result.json"
    monkeypatch.setattr(sys, "argv", ["glideleaf", "--driver-install", "--vid", "0x0a12", "--pid", "1", "--adapter-id", selected.identity, "--driver-result", str(result)])
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(driver, "is_admin", lambda: True)
    monkeypatch.setattr(driver, "install_winusb", Mock(side_effect=RuntimeError("install detail")))
    assert cli.main() == 1
    assert setup.call_args.kwargs["to_file"] is True
    logger.exception.assert_called_once()
    assert json.loads(result.read_text(encoding="utf-8"))["error"] == "install detail"


def test_restore_missing_target_never_elevates(monkeypatch, selected):
    elevate = Mock()
    monkeypatch.setattr(driver, "_relaunch_elevated", elevate)
    monkeypatch.setattr(driver, "list_dongles", lambda: [])
    with pytest.raises(RuntimeError):
        driver.restore_inbox_elevated(selected.vid, selected.pid, adapter_id=selected.identity)
    elevate.assert_not_called()


def test_privileged_result_destination_cannot_overwrite_existing_or_arbitrary_files(monkeypatch, tmp_path):
    import tempfile
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    arbitrary = tmp_path / "important.json"
    arbitrary.write_text("keep")
    with pytest.raises(ValueError):
        driver.driver_result_path(str(arbitrary))
    folder = tmp_path / "glideleaf-driver-check"
    folder.mkdir()
    result = folder / "result.json"
    assert driver.driver_result_path(str(result)) == result.resolve()
    result.write_text("keep")
    with pytest.raises(ValueError):
        driver.driver_result_path(str(result))
    assert arbitrary.read_text() == result.read_text() == "keep"


def test_composite_interface_never_replaces_parent_or_other_functions(monkeypatch, selected):
    interface = replace(selected, instance_id=r"USB\VID_0A12&PID_0001&MI_00\interface")
    monkeypatch.setattr(driver, "list_dongles", lambda: [interface])
    package, elevate, update = Mock(), Mock(), Mock()
    monkeypatch.setattr(inbox_driver, "probe", package)
    monkeypatch.setattr(driver, "_relaunch_elevated", elevate)
    monkeypatch.setattr(inbox_driver, "install", update)
    with pytest.raises(RuntimeError):
        driver.install_winusb_elevated(interface.vid, interface.pid, adapter_id=interface.identity)
    package.assert_not_called()
    elevate.assert_not_called()
    update.assert_not_called()
