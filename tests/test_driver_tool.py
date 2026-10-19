import hashlib
import io
import zipfile
from unittest.mock import Mock

import pytest

from winuc import driver_tool as tool


@pytest.fixture
def download(monkeypatch, tmp_path):
    executable = b"test-executable-not-run"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("wdi-simple.exe", executable)
        archive.writestr("../unwanted.exe", b"must never extract")
    data = output.getvalue()
    monkeypatch.setattr(tool, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(tool, "_architecture", lambda: "x64")
    monkeypatch.setitem(tool.BUILDS, "x64", (
        hashlib.sha256(data).hexdigest(), hashlib.sha256(executable).hexdigest()))
    fetch = Mock(side_effect=lambda *a, **k: io.BytesIO(data))
    monkeypatch.setattr(tool.urllib.request, "urlopen", fetch)
    return tmp_path, executable, fetch


def test_download_verifies_extracts_only_tool_and_reuses_cache(download):
    root, executable, fetch = download
    path = tool.ensure_tool()
    assert path.read_bytes() == executable
    assert tool.cached_tool() == path
    assert (path.parent / "COPYING-LGPL").is_file()
    assert (path.parent / "NOTICE.txt").is_file()
    assert not list(root.rglob("unwanted.exe"))
    assert not list(root.rglob("*.part"))
    assert tool.ensure_tool() == path
    fetch.assert_called_once()


def test_corrupted_cache_is_not_executed_or_reused(download):
    _, _, fetch = download
    path = tool.ensure_tool()
    path.write_bytes(b"tampered")
    assert tool.cached_tool() is None
    tool.ensure_tool()
    assert fetch.call_count == 2
    assert tool.cached_tool() == path


@pytest.mark.parametrize("failure", ["archive", "executable", "network"])
def test_failed_download_leaves_no_executable(download, monkeypatch, failure):
    root, _, fetch = download
    if failure == "network":
        fetch.side_effect = TimeoutError("offline")
    else:
        hashes = list(tool.BUILDS["x64"])
        hashes[0 if failure == "archive" else 1] = "0" * 64
        monkeypatch.setitem(tool.BUILDS, "x64", tuple(hashes))
    with pytest.raises(RuntimeError, match="download/verification failed"):
        tool.ensure_tool()
    assert not list(root.rglob("*.exe"))
    assert not list(root.rglob("*.part"))
