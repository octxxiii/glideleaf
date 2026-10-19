import ctypes
from pathlib import Path
from unittest.mock import Mock
import sys

import pytest

from winuc import native_driver as native


def make_package(root, vid=0x0A12, pid=1):
    folder = root / native.package_name(vid, pid)
    folder.mkdir(parents=True)
    (folder / "glideleaf.inf").write_bytes(native.inf_bytes(vid, pid))
    (folder / "glideleaf.cat").write_bytes(b"not-a-real-catalog")
    return folder


def test_canonical_inf_is_hardware_specific_and_uses_only_inbox_driver():
    for vid, pid in native.SUPPORTED_IDS:
        text = native.inf_bytes(vid, pid).decode("utf-16")
        assert f"USB\\VID_{vid:04X}&PID_{pid:04X}" in text
        assert text.count("USB\\VID_") == 1
        assert "Needs=WINUSB.NT" in text
        assert native.INTERFACE_GUID in text
        assert not any(value in text.lower() for value in ("copyfiles", ".sys", "coinstallers", "security"))


def test_unsigned_or_modified_package_stops_before_install(tmp_path, monkeypatch):
    folder = make_package(tmp_path)
    verifier = Mock(side_effect=OSError("untrusted catalog"))
    monkeypatch.setattr(native, "verify_inf", verifier)
    with pytest.raises(RuntimeError):
        native.prepare_package(0x0A12, 1, root=tmp_path)
    verifier.assert_called_once()
    verifier.reset_mock()
    (folder / "glideleaf.inf").write_text("another hardware ID")
    with pytest.raises(RuntimeError):
        native.prepare_package(0x0A12, 1, root=tmp_path)
    verifier.assert_not_called()


def test_valid_catalog_is_required_and_signer_is_reported(tmp_path, monkeypatch):
    folder = make_package(tmp_path)
    monkeypatch.setattr(native, "verify_inf", lambda inf: "Windows-trusted publisher")
    package = native.prepare_package(0x0A12, 1, root=tmp_path)
    assert package.signer == "Windows-trusted publisher"
    assert package.inf == (folder / "glideleaf.inf").resolve()


def test_readonly_diagnostics_never_perform_signature_or_install_calls(tmp_path, monkeypatch):
    verifier = Mock()
    monkeypatch.setattr(native, "verify_inf", verifier)
    report = native.readiness(root=tmp_path, verify=False)
    assert report["ready"] is None
    assert not report["verification_performed"]
    assert not any(p["present"] for p in report["packages"])
    verifier.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows signing API")
def test_actual_windows_verifier_rejects_unsigned_inf_without_mutating_devices(tmp_path):
    folder = make_package(tmp_path)
    with pytest.raises(OSError):
        native.verify_inf(folder / "glideleaf.inf")
    # SP_INF_SIGNER_INFO_W must match the Windows SDK ABI.
    assert ctypes.sizeof(native._SignerInfo) == 1564


def test_native_update_calls_only_selected_hardware_with_force_and_reports_reboot(tmp_path, monkeypatch):
    def invoke(hwnd, hardware_id, inf_path, flags, reboot):
        assert hardware_id == r"USB\VID_0A12&PID_0001"
        assert inf_path == str(tmp_path / "glideleaf.inf")
        assert flags == 1  # FORCE; no trust/security-policy bypass flags.
        reboot._obj.value = True
        return True
    update = Mock(side_effect=invoke)
    api = type("API", (), {"UpdateDriverForPlugAndPlayDevicesW": update})()
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: api)
    package = native.Package(tmp_path / "glideleaf.inf", tmp_path / "glideleaf.cat", "publisher")
    assert native.update_driver(0x0A12, 1, package) is True
    update.assert_called_once()
