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
    directory = tmp_path / "INF"
    directory.mkdir()
    (directory / "oem1.inf").write_text("WinUSB\nUSB\\VID_9999&PID_0001", encoding="utf-8")
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="Published Name: oem1.inf")
    monkeypatch.setenv("WINDIR", str(tmp_path))
    monkeypatch.setattr(driver, "_run", run)
    driver.restore_inbox(0x0411, 0x0374)
    assert not any("/delete-driver" in call for call in calls)
