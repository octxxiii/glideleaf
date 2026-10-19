"""Prepare the official signed Zadig release; never execute a community build."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import urllib.request

from .paths import data_dir

SOURCE = "https://github.com/pbatard/libwdi"
VERSION = "2.9"
URL = SOURCE + "/releases/download/v1.5.1/zadig-2.9.exe"
SHA256 = "4ecaa95df3da3621486a043aef8b3050b8bafe7c901402871e816229ef82039b"
LIMIT = 32 * 1024 * 1024
_lock = threading.Lock()


def _destination() -> Path:
    return data_dir() / "tools" / "zadig-2.9" / "zadig.exe"


def _verified(path: Path) -> bool:
    try:
        return path.stat().st_size <= LIMIT and hashlib.sha256(path.read_bytes()).hexdigest() == SHA256
    except OSError:
        return False


def _verify_signature(path: Path) -> None:
    shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    literal = str(path).replace("'", "''")
    module = str(shell.parent / "Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1").replace("'", "''")
    script = ("$ErrorActionPreference='Stop'; "
              "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
              "Import-Module '" + module + "'; "
              "$s=Get-AuthenticodeSignature -LiteralPath '" + literal + "'; "
              "@{Status=$s.Status.ToString();Signer=if($s.SignerCertificate){"
              "$s.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false)}else{''}} | ConvertTo-Json -Compress")
    result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, timeout=45, check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        signature = json.loads(result.stdout.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Could not verify the official installer signature") from exc
    if result.returncode or signature.get("Status") != "Valid" or signature.get("Signer") != "Akeo Consulting":
        raise RuntimeError("Official installer signature is not valid for Akeo Consulting. Setup stopped.")


def cached_tool() -> Path | None:
    # Discovery is read-only and never triggers certificate/network checks.
    path = _destination()
    return path if _verified(path) else None


def ensure_tool() -> Path:
    """Download pinned official bytes; require a valid publisher signature."""
    with _lock:
        path = _destination()
        if _verified(path):
            _verify_signature(path)
            return path
        temp = None
        try:
            request = urllib.request.Request(URL, headers={"User-Agent": "Glideleaf-driver-setup"})
            with urllib.request.urlopen(request, timeout=60) as response:
                executable = response.read(LIMIT + 1)
            if len(executable) > LIMIT or hashlib.sha256(executable).hexdigest() != SHA256:
                raise ValueError("official installer SHA-256 mismatch")
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".exe", delete=False) as output:
                temp = Path(output.name)
                output.write(executable)
                output.flush()
                os.fsync(output.fileno())
            _verify_signature(temp)
            for name in ("COPYING", "COPYING-LGPL"):
                (path.parent / name).write_bytes((Path(__file__).parent / "licenses" / name).read_bytes())
            (path.parent / "NOTICE.txt").write_text(
                f"Official Zadig {VERSION}, Akeo Consulting\nDownload: {URL}\n"
                f"Corresponding source: {SOURCE}/tree/v1.5.1\n"
                f"License: GPL-3.0-or-later (libwdi: LGPL-3.0-or-later)\nSHA-256: {SHA256}\n", encoding="utf-8")
            os.replace(temp, path)
            return path
        except Exception as exc:
            raise RuntimeError(f"Official driver tool preparation failed: {exc}. Setup stopped.") from exc
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)


if __name__ == "__main__":
    print(ensure_tool())
