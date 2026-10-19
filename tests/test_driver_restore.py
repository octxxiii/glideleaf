from types import SimpleNamespace

from winuc import driver


def test_restore_requires_device_identity_and_winusb():
    target = "vid_0411&pid_0374"
    assert driver._block_matches(["USB\\VID_0411&PID_0374", "Include=winusb.inf"], target)
    assert not driver._block_matches(["winusb.inf", "USB\\VID_9999&PID_0001"], target)
    assert not driver._block_matches(["USB\\VID_0411&PID_0374", "BthUsb"], target)
    assert not driver._block_matches(["winusb", "USB\\VID_0411&PID_03740"], target)


def test_localized_list_checks_actual_inf(tmp_path, monkeypatch):
    directory = tmp_path / "INF"
    directory.mkdir()
    (directory / "oem1.inf").write_text("WinUSB\nUSB\\VID_0411&PID_0374", encoding="utf-16")
    (directory / "oem2.inf").write_text("WinUSB\nUSB\\VID_9999&PID_0001", encoding="utf-8")
    monkeypatch.setenv("WINDIR", str(tmp_path))
    monkeypatch.setattr(driver, "_run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="게시된 이름: oem1.inf\n게시된 이름: oem2.inf\n게시된 이름: oem3.inf"))
    assert driver._enum_winusb_oem_infs(0x0411, 0x0374) == ["oem1.inf"]


def test_restore_never_deletes_unrelated_winusb(tmp_path, monkeypatch):
    from winuc import inbox_driver
    selected = driver.Dongle(0x0411, 0x0374, r"USB\VID_0411&PID_0374\selected", "Selected", "winusb")
    monkeypatch.setattr(driver, "is_admin", lambda: True)
    monkeypatch.setattr(driver, "list_dongles", lambda: [selected])
    restore = []
    monkeypatch.setattr(inbox_driver, "restore", lambda instance: restore.append(instance) or False)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        raise AssertionError("Restore must not call pnputil")
    monkeypatch.setattr(driver, "_run", run)
    monkeypatch.setattr(driver, "list_dongles", lambda: [driver.Dongle(0x0411, 0x0374, selected.instance_id, "Selected", "inbox")] if restore else [selected])
    driver.restore_inbox(0x0411, 0x0374, adapter_id=selected.identity)
    assert restore == [selected.instance_id]
    assert not calls
