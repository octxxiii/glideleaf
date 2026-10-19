"""Read-only coverage of Windows' existing WinUSB model and target guards."""
import ctypes
import sys
from unittest.mock import Mock

import pytest

from winuc import driver, inbox_driver


def test_setupapi_abi_and_microsoft_model_are_available():
    if sys.platform != "win32":
        pytest.skip("Windows SetupAPI")
    assert [ctypes.sizeof(cls) for cls in (
        inbox_driver.DeviceInfo, inbox_driver.InstallParams,
        inbox_driver.DriverInfo, inbox_driver.DriverDetail,
    )] == [32, 584, 1568, 1584]
    report = inbox_driver.readiness()
    assert report["method"] == "windows-inbox-winusb"
    if report["ready"]:
        assert report["section"].casefold() == "winusb"
        assert report["signer"].casefold().startswith("microsoft windows")
        assert report["hardware_verified"] is False
    else:
        assert report["error"]  # Some CI images do not expose this model.


def test_interface_guid_merge_is_idempotent_and_preserves_other_entries():
    other = "{12345678-1234-1234-1234-123456789abc}"
    values = [other]
    added = inbox_driver.merge_guids(values, add=True)
    assert values == [other]
    assert added == [other, inbox_driver.INTERFACE_GUID]
    assert inbox_driver.merge_guids(added, add=True) == added
    assert inbox_driver.merge_guids(added, add=False) == [other]


def test_unsupported_internal_radio_never_enters_native_install(monkeypatch):
    internal = driver.Dongle(0x8087, 0x0026, r"USB\VID_8087&PID_0026\internal", "Intel", "inbox")
    monkeypatch.setattr(driver, "list_dongles", lambda: [internal])
    probe = Mock()
    monkeypatch.setattr(inbox_driver, "probe", probe)
    with pytest.raises(RuntimeError):
        driver.install_winusb_elevated(internal.vid, internal.pid, adapter_id=internal.identity)
    probe.assert_not_called()
