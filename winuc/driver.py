"""Automated WinUSB driver management for the Bluetooth dongle.

WinUC drives the dongle in user space (via bumble/libusb), which requires the
dongle to be bound to the WinUSB driver instead of the in-box Bluetooth stack.

A Bluetooth radio is already claimed by a higher-ranked in-box driver, so
`pnputil /add-driver /install` will not force WinUSB onto it. The reliable way
to force-rebind is libwdi (the engine behind Zadig); we ship its scriptable
CLI, `wdi-simple.exe`, and shell out to it. Restoring the in-box driver is done
with `pnputil`.

All install/restore operations require Administrator. The GUI calls the
`*_elevated` helpers, which re-launch this module's CLI verbs elevated (one UAC
prompt) when the current process is not already elevated.
"""

from __future__ import annotations

import ctypes
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# VID/PID of Bluetooth USB dongles we know how to drive. The RTL8761B family is
# the tested reference; add more as they are verified.
KNOWN_DONGLES: dict[tuple[int, int], str] = {
    (0x0411, 0x0374): "Buffalo / Realtek RTL8761B",
    (0x0BDA, 0x8771): "Realtek RTL8761BU",
    (0x0BDA, 0xC820): "Realtek RTL8821C",
    (0x0A12, 0x0001): "Cambridge Silicon Radio (CSR) 4.0",
}


@dataclass
class Dongle:
    vid: int
    pid: int
    instance_id: str
    friendly_name: str
    driver: str  # "winusb" | "inbox" | "unknown"

    @property
    def vidpid(self) -> tuple[int, int]:
        return (self.vid, self.pid)

    @property
    def label(self) -> str:
        return KNOWN_DONGLES.get(self.vidpid, self.friendly_name or "Bluetooth dongle")

    @property
    def is_winusb(self) -> bool:
        return self.driver == "winusb"


def is_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def wdi_simple_path() -> Path | None:
    """Locate the bundled wdi-simple.exe (dev tree or PyInstaller bundle)."""
    candidates = [Path(__file__).resolve().parent.parent / "tools" / "wdi-simple.exe"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:  # PyInstaller bundle root (_internal in onedir)
        candidates.insert(0, Path(meipass) / "tools" / "wdi-simple.exe")
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).resolve().parent / "tools" / "wdi-simple.exe")
    for path in candidates:
        if path.is_file():
            return path
    return None


# --------------------------------------------------------------- detection

def _pnp_query() -> list[dict[str, str]]:
    """Return USB device info via PowerShell Get-PnpDevice (JSON)."""
    if sys.platform != "win32":
        return []
    script = (
        "Get-PnpDevice -PresentOnly | "
        "Where-Object { $_.InstanceId -like 'USB\\VID_*' } | "
        "Select-Object InstanceId, FriendlyName, Class, Status | "
        "ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return []
    if not out:
        return []
    import json

    data = json.loads(out)
    return data if isinstance(data, list) else [data]


_VIDPID_RE = re.compile(r"USB\\VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})")


def list_dongles(known_only: bool = False) -> list[Dongle]:
    """Enumerate present USB Bluetooth dongles and their current driver binding.

    Deduplicated by VID/PID (composite devices enumerate one node per
    interface). Only known dongles, Bluetooth-class devices, and WinUSB-bound
    devices are reported -- unrelated USB gear (mice, storage) is skipped.
    """
    by_vidpid: dict[tuple[int, int], Dongle] = {}
    for entry in _pnp_query():
        instance_id = entry.get("InstanceId", "")
        match = _VIDPID_RE.match(instance_id)
        if not match:
            continue
        vid = int(match.group(1), 16)
        pid = int(match.group(2), 16)
        cls = (entry.get("Class") or "").lower()
        name = entry.get("FriendlyName") or ""
        is_known = (vid, pid) in KNOWN_DONGLES
        looks_bluetooth = cls == "bluetooth" or "bluetooth" in name.lower()
        is_winusb = cls in ("usbdevice", "winusb")

        if not (is_known or looks_bluetooth or is_winusb):
            continue
        if known_only and not is_known:
            continue

        driver = "winusb" if is_winusb else "inbox" if cls == "bluetooth" else "unknown"
        # A WinUSB-bound known dongle has no meaningful Class name; trust the
        # known list for its label. Prefer the most informative record per VID/PID.
        existing = by_vidpid.get((vid, pid))
        if existing is None or (existing.driver == "unknown" and driver != "unknown"):
            by_vidpid[(vid, pid)] = Dongle(vid, pid, instance_id, name, driver)
    return list(by_vidpid.values())


def find_dongle(vid: int | None = None, pid: int | None = None) -> Dongle | None:
    dongles = list_dongles()
    if vid is not None and pid is not None:
        for d in dongles:
            if d.vidpid == (vid, pid):
                return d
        return None
    # Prefer a known dongle, else the first Bluetooth-looking one.
    for d in dongles:
        if d.vidpid in KNOWN_DONGLES:
            return d
    return dongles[0] if dongles else None


# ----------------------------------------------------------- admin actions
# These assume the current process is elevated. The GUI uses the *_elevated
# wrappers below.

def _run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    logger.info("run: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def install_winusb(vid: int, pid: int, name: str = "WinUC Bluetooth") -> None:
    """Force-bind the dongle to WinUSB using wdi-simple. Requires admin."""
    exe = wdi_simple_path()
    if exe is None:
        raise FileNotFoundError(
            "wdi-simple.exe not found. Run scripts/fetch_wdi.ps1 or build libwdi."
        )
    result = _run([
        str(exe),
        "--vid", f"0x{vid:04X}",
        "--pid", f"0x{pid:04X}",
        "--type", "0",  # 0 = WinUSB
        "--name", name,
        "--timeout", "120000",
    ])
    if result.returncode != 0:
        raise RuntimeError(
            f"wdi-simple failed (exit {result.returncode}): "
            f"{result.stdout.strip()} {result.stderr.strip()}"
        )


def _enum_winusb_oem_infs(vid: int, pid: int) -> list[str]:
    """Find oemNN.inf packages that bind our VID/PID to WinUSB."""
    result = _run(["pnputil", "/enum-drivers"], timeout=60)
    infs: list[str] = []
    current = None
    hwid = f"VID_{vid:04X}&PID_{pid:04X}".lower()
    block: list[str] = []
    for line in result.stdout.splitlines():
        if line.strip().lower().startswith("published name"):
            if current and _block_matches(block, hwid):
                infs.append(current)
            current = line.split(":", 1)[1].strip()
            block = []
        else:
            block.append(line.lower())
    if current and _block_matches(block, hwid):
        infs.append(current)
    return infs


def _block_matches(block: list[str], hwid: str) -> bool:
    text = "\n".join(block)
    return "winusb" in text or hwid in text


def restore_inbox(vid: int, pid: int) -> None:
    """Remove the WinUSB package and let Windows reapply the in-box driver."""
    for inf in _enum_winusb_oem_infs(vid, pid):
        _run(["pnputil", "/delete-driver", inf, "/uninstall", "/force"], timeout=120)
    _run(["pnputil", "/scan-devices"], timeout=60)


# ------------------------------------------------------------- elevation

def _relaunch_elevated(args: list[str], wait: bool = True) -> int:
    """Re-launch this program's driver CLI with the given args, elevated."""
    import ctypes.wintypes as wt

    if getattr(sys, "frozen", False):
        exe = sys.executable
        params = subprocess.list2cmdline(args)
    else:
        exe = sys.executable
        params = subprocess.list2cmdline(["-m", "winuc", *args])

    SEE_MASK_NOCLOSEPROCESS = 0x00000040

    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wt.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wt.HWND),
            ("lpVerb", wt.LPCWSTR),
            ("lpFile", wt.LPCWSTR),
            ("lpParameters", wt.LPCWSTR),
            ("lpDirectory", wt.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wt.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wt.LPCWSTR),
            ("hkeyClass", wt.HKEY),
            ("dwHotKey", wt.DWORD),
            ("hIcon", wt.HANDLE),
            ("hProcess", wt.HANDLE),
        ]

    info = SHELLEXECUTEINFO()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = params
    info.nShow = 0  # SW_HIDE
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        raise OSError("elevation was cancelled or failed")
    if not wait or not info.hProcess:
        return 0
    ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    code = wt.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(info.hProcess)
    return code.value


def install_winusb_elevated(vid: int, pid: int, name: str = "WinUC Bluetooth") -> None:
    if is_admin():
        install_winusb(vid, pid, name)
        return
    code = _relaunch_elevated(
        ["--driver-install", "--vid", f"0x{vid:04X}", "--pid", f"0x{pid:04X}"]
    )
    if code != 0:
        raise RuntimeError(f"elevated driver install failed (exit {code})")


def restore_inbox_elevated(vid: int, pid: int) -> None:
    if is_admin():
        restore_inbox(vid, pid)
        return
    code = _relaunch_elevated(
        ["--driver-restore", "--vid", f"0x{vid:04X}", "--pid", f"0x{pid:04X}"]
    )
    if code != 0:
        raise RuntimeError(f"elevated driver restore failed (exit {code})")
