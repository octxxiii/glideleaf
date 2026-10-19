from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from winuc import driver


def test_download_failure_is_reported_before_uac(monkeypatch):
    from winuc import driver_tool
    monkeypatch.setattr(driver, "wdi_simple_path", lambda: None)
    monkeypatch.setattr(driver_tool, "ensure_tool", Mock(side_effect=RuntimeError("download failed")))
    elevate = Mock()
    monkeypatch.setattr(driver, "_relaunch_elevated", elevate)
    with pytest.raises(RuntimeError, match="download failed"):
        driver.install_winusb_elevated(0x0A12, 1)
    elevate.assert_not_called()


def test_missing_installer_is_prepared_before_uac(monkeypatch):
    from winuc import driver_tool
    order = []
    monkeypatch.setattr(driver, "wdi_simple_path", lambda: None)
    monkeypatch.setattr(driver, "is_admin", lambda: False)
    monkeypatch.setattr(driver_tool, "ensure_tool", lambda: order.append("download"))
    monkeypatch.setattr(driver, "_relaunch_elevated", lambda args: order.append("uac") or 0)
    driver.install_winusb_elevated(0x0A12, 1)
    assert order == ["download", "uac"]


def test_elevated_failure_points_to_persistent_log(monkeypatch, tmp_path):
    from winuc import paths
    monkeypatch.setattr(driver, "wdi_simple_path", lambda: tmp_path / "wdi-simple.exe")
    monkeypatch.setattr(driver, "is_admin", lambda: False)
    monkeypatch.setattr(driver, "_relaunch_elevated", lambda args: 1)
    monkeypatch.setattr(paths, "log_path", lambda: tmp_path / "winuc.log")
    with pytest.raises(RuntimeError, match="winuc.log"):
        driver.install_winusb_elevated(0x0A12, 1)


def test_windowless_driver_failure_is_logged(monkeypatch):
    import sys
    from winuc import __main__ as cli
    setup = Mock()
    logger = Mock()
    monkeypatch.setattr(cli, "_setup_logging", setup)
    monkeypatch.setattr(cli, "logging", SimpleNamespace(getLogger=lambda name: logger))
    monkeypatch.setattr(sys, "argv", ["glideleaf", "--driver-install", "--vid", "0x0a12", "--pid", "1"])
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(driver, "install_winusb_elevated", Mock(side_effect=RuntimeError("install detail")))
    assert cli.main() == 1
    assert setup.call_args.kwargs["to_file"] is True
    logger.exception.assert_called_once()
