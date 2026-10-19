import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from winuc import driver
from winuc.diagnostics import build_report, report_text


def entry(**changes):
    return {"InstanceId": r"USB\VID_1234&PID_5678\PRIVATE-SERIAL", "FriendlyName": "Radio", "Class": "USBDevice", "Service": "", **changes}


def test_non_english_radio_detected_from_service_and_hci_ids():
    devices = [entry(FriendlyName="무선 어댑터", Class=None, Service="BTHUSB")]
    assert driver.list_dongles(devices=devices)[0].driver == "inbox"
    devices = [entry(FriendlyName="无线适配器", Service="WinUSB", CompatibleIds=[r"USB\Class_E0&SubClass_01&Prot_01"])]
    assert driver.list_dongles(devices=devices)[0].driver == "winusb"


def test_generic_usbdevice_does_not_mean_winusb():
    radio = driver.list_dongles(devices=[entry(FriendlyName="Bluetooth Adapter")])[0]
    assert radio.driver == "unknown"
    assert not radio.is_winusb


def test_unrelated_winusb_and_hid_receivers_are_not_radios():
    devices = [entry(FriendlyName="JTAG", Service="WinUSB"),
               entry(FriendlyName="Bluetooth keyboard receiver", Class="HIDClass", Service="HidUsb")]
    assert driver.list_dongles(devices=devices) == []


def test_known_radio_can_still_be_found_after_driver_rebind():
    item = entry(InstanceId=r"USB\VID_0BDA&PID_8771\serial", Service="WinUSB", FriendlyName="USB Device")
    assert driver.list_dongles(devices=[item])[0].is_winusb


@pytest.mark.skipif(sys.platform != "win32", reason="Windows enumeration")
def test_powershell_output_is_explicit_utf8_without_console(monkeypatch):
    records = [entry(FriendlyName="블루투스 어댑터", Class="Bluetooth", Service="BTHUSB")]
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(records, ensure_ascii=False).encode("utf-8-sig"), stderr=b""))
    monkeypatch.setattr(driver.subprocess, "run", run)
    assert driver._pnp_query() == records
    assert run.call_args.kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW


@pytest.mark.skipif(sys.platform != "win32", reason="Windows enumeration")
@pytest.mark.parametrize("result", [
    SimpleNamespace(returncode=1, stdout=b"", stderr=b"Access denied"),
    SimpleNamespace(returncode=0, stdout=b"not JSON", stderr=b""),
    SimpleNamespace(returncode=0, stdout=b"null", stderr=b""),
])
def test_enumeration_failures_are_never_reported_as_no_device(monkeypatch, result):
    monkeypatch.setattr(driver.subprocess, "run", Mock(return_value=result))
    with pytest.raises(driver.DongleDetectionError):
        driver._pnp_query()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows enumeration")
def test_enumeration_timeout_is_visible(monkeypatch):
    monkeypatch.setattr(driver.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("powershell", 30)))
    with pytest.raises(driver.DongleDetectionError, match="timed out"):
        driver._pnp_query()


def test_diagnostics_include_ignored_devices_but_omit_serial_suffixes():
    report = build_report([entry(FriendlyName="HID receiver", Class="HIDClass", Service="HidUsb")])
    assert report["usb_node_count"] == 1
    assert report["bluetooth_candidate_count"] == 0
    assert "HID receiver" in report_text(report)
    assert "PRIVATE-SERIAL" not in report_text(report)


def test_diagnostics_run_even_when_saved_configuration_is_broken(tmp_path, monkeypatch):
    from winuc import __main__
    path = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["glideleaf", "--diagnose", str(path)])
    monkeypatch.setattr(driver, "_pnp_query", lambda: [])
    monkeypatch.setattr(__main__.Config, "load", Mock(side_effect=AssertionError("must not load config or keys")))
    assert __main__.main() == 0
    assert json.loads(path.read_text(encoding="utf-8"))["usb_node_count"] == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop UI")
def test_setup_scan_failure_keeps_copyable_error_report(monkeypatch):
    import tkinter as tk
    from winuc.gui.setup_wizard import SetupWizard
    from winuc.i18n import t
    root = tk.Tk()
    root.withdraw()
    monkeypatch.setattr(driver, "_pnp_query", Mock(side_effect=driver.DongleDetectionError("query failed")))
    wizard = SetupWizard(root)
    try:
        root.after(300, root.quit)
        root.mainloop()
        assert wizard.status_var.get() == t("동글을 검색하지 못했습니다. 다시 시도해 주세요.")
        assert json.loads(wizard._diagnostic_text)["enumeration_error"] == "query failed"
        assert str(wizard.copy_btn["state"]) == "normal"
    finally:
        wizard._close()
        root.destroy()
