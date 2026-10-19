import hashlib
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from winuc import driver_tool as tool


@pytest.fixture
def download(monkeypatch, tmp_path):
    executable = b"test-executable-not-run"
    monkeypatch.setattr(tool, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(tool, "SHA256", hashlib.sha256(executable).hexdigest())
    signature = Mock()
    monkeypatch.setattr(tool, "_verify_signature", signature)
    fetch = Mock(side_effect=lambda *a, **k: io.BytesIO(executable))
    monkeypatch.setattr(tool.urllib.request, "urlopen", fetch)
    return tmp_path, executable, fetch, signature


def test_download_checks_hash_and_signature_then_reuses_cache(download):
    root, executable, fetch, signature = download
    path = tool.ensure_tool()
    assert path.read_bytes() == executable
    assert tool.cached_tool() == path
    assert (path.parent / "COPYING").is_file()
    assert (path.parent / "NOTICE.txt").is_file()
    assert tool.ensure_tool() == path
    fetch.assert_called_once()
    assert signature.call_count == 2  # Cached bytes still need a valid signature.
    assert list(root.rglob("*.exe")) == [path]


def test_old_community_cache_is_never_used(download):
    root, _, fetch, _ = download
    old = root / "tools/v1.0/x64/wdi-simple.exe"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"legacy")
    assert tool.cached_tool() is None
    assert tool.ensure_tool().name == "zadig.exe"
    fetch.assert_called_once()


def test_corrupted_cache_is_not_reused(download):
    _, _, fetch, _ = download
    path = tool.ensure_tool()
    path.write_bytes(b"tampered")
    assert tool.cached_tool() is None
    tool.ensure_tool()
    assert fetch.call_count == 2


@pytest.mark.parametrize("failure", ["hash", "signature", "network"])
def test_failed_preparation_never_publishes_an_executable(download, monkeypatch, failure):
    root, _, fetch, signature = download
    if failure == "network":
        fetch.side_effect = TimeoutError("offline")
    elif failure == "signature":
        signature.side_effect = RuntimeError("invalid signature")
    else:
        monkeypatch.setattr(tool, "SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="preparation failed"):
        tool.ensure_tool()
    assert not list(root.rglob("*.exe"))


@pytest.mark.parametrize("status,publisher", [("NotSigned", ""), ("Valid", "Other Publisher"), ("UnknownError", "Akeo Consulting")])
def test_untrusted_signature_is_rejected(monkeypatch, tmp_path, status, publisher):
    import json
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps({"Status": status, "Signer": publisher}).encode()))
    with pytest.raises(RuntimeError, match="signature is not valid"):
        tool._verify_signature(tmp_path / "zadig.exe")
