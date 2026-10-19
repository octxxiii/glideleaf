"""Pinned optional libwdi community build, downloaded only for driver setup.

No installer is executed here. Verify both the release archive and the sole
executable we extract; never extract arbitrary archive paths.
"""
from __future__ import annotations

import hashlib
import io
import os
import platform
from pathlib import Path
import tempfile
import threading
import urllib.request
import zipfile

from .paths import data_dir

SOURCE = "https://github.com/Timocop/libwdi-wdi-releases"
VERSION = "v1.0"
BUILDS = {
    "x64": ("d5aace13a3c1d5980113a5938fbee2edaa788ed625e3c554ff47da24cde39cda",
            "27b6d9847d874674b7c412af124acf64b0b1efa397e3bbea8eab9950a6a08ee0"),
    "x86": ("ac37a6a24eb9e550135218e5af30669d6e8a3d78c5d36f9b4ab6c1f6232ef266",
            "da0e280cf66d7261ceb436ff48d45bbd6f5ab9b70180b487a41a2957f9723bf6"),
}
LIMIT = 32 * 1024 * 1024
_lock = threading.Lock()


def _architecture() -> str:
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        return "x64"
    if machine in ("x86", "i386", "i686"):
        return "x86"
    raise RuntimeError(f"Automatic driver setup does not support {machine}")


def _destination(arch: str) -> Path:
    return data_dir() / "tools" / VERSION / arch / "wdi-simple.exe"


def _verified(path: Path, digest: str) -> bool:
    try:
        return path.stat().st_size <= LIMIT and hashlib.sha256(path.read_bytes()).hexdigest() == digest
    except OSError:
        return False


def cached_tool() -> Path | None:
    try:
        arch = _architecture()
    except RuntimeError:
        return None
    path = _destination(arch)
    return path if _verified(path, BUILDS[arch][1]) else None


def ensure_tool() -> Path:
    """Fetch once, reuse only verified bytes, and leave no partial executable."""
    with _lock:
        arch = _architecture()
        path = _destination(arch)
        archive_hash, executable_hash = BUILDS[arch]
        if _verified(path, executable_hash):
            return path
        url = f"{SOURCE}/releases/download/{VERSION}/{arch}.zip"
        request = urllib.request.Request(url, headers={"User-Agent": "Glideleaf-driver-setup"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                archive = response.read(LIMIT + 1)
            if len(archive) > LIMIT or hashlib.sha256(archive).hexdigest() != archive_hash:
                raise ValueError("driver archive SHA-256 mismatch")
            with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                entry = zipped.getinfo("wdi-simple.exe")
                if entry.file_size > LIMIT:
                    raise ValueError("driver executable exceeds size limit")
                executable = zipped.read(entry)
            if hashlib.sha256(executable).hexdigest() != executable_hash:
                raise ValueError("driver executable SHA-256 mismatch")
            path.parent.mkdir(parents=True, exist_ok=True)
            for license_name in ("COPYING", "COPYING-LGPL"):
                (path.parent / license_name).write_bytes(
                    (Path(__file__).parent / "licenses" / license_name).read_bytes())
            notice = (f"libwdi wdi-simple community build {VERSION} ({arch})\n"
                      f"Binary source: {SOURCE}/releases/tag/{VERSION}\n"
                      f"Source code: {SOURCE}/tree/{VERSION}\n"
                      "License: LGPL-3.0-or-later\n"
                      "https://www.gnu.org/licenses/lgpl-3.0.html\n"
                      f"Executable SHA-256: {executable_hash}\n")
            (path.parent / "NOTICE.txt").write_text(notice, encoding="utf-8")
            temp = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as output:
                    temp = Path(output.name)
                    output.write(executable)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temp, path)
            finally:
                if temp is not None:
                    temp.unlink(missing_ok=True)
            return path
        except Exception as exc:
            raise RuntimeError(f"Driver tool download/verification failed: {exc}. Retry WinUSB setup.") from exc


if __name__ == "__main__":
    print(ensure_tool())
