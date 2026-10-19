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
import os
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
    container_id: str = ""
    location: str = ""

    @property
    def vidpid(self) -> tuple[int, int]:
        return (self.vid, self.pid)

    @property
    def label(self) -> str:
        return KNOWN_DONGLES.get(self.vidpid, self.friendly_name or "Bluetooth dongle")

    @property
    def is_winusb(self) -> bool:
        return self.driver == "winusb"

    @property
    def identity(self) -> str:
        """Persist the physical selection independently of the driver name."""
        return f"{self.vid:04x}:{self.pid:04x}/{self.container_id or self.instance_id}".casefold()

    @property
    def transport(self) -> str:
        # Preserve the upstream firmware-loader override for its Realtek IDs.
        realtek = self.vidpid in ((0x0411, 0x0374), (0x0BDA, 0x8771), (0x0BDA, 0xC820))
        prefix = "[driver=rtk]" if realtek else ""
        return f"usb:{prefix}{self.vid:04x}:{self.pid:04x}"


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
    from .driver_tool import cached_tool
    return cached_tool()


# --------------------------------------------------------------- detection

class DongleDetectionError(RuntimeError):
    """USB enumeration failed; this must not be presented as 'no device'."""


_PNP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
try {
    $devices = @(Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
        Where-Object { $_.Present -and $_.PNPDeviceID -like 'USB\VID_*' } |
        ForEach-Object {
            [PSCustomObject]@{
                InstanceId = $_.PNPDeviceID
                FriendlyName = $_.Name
                Class = $_.PNPClass
                Status = $_.Status
                Service = $_.Service
                CompatibleIds = @($_.CompatibleID)
                ProblemCode = $_.ConfigManagerErrorCode
            }
        })
} catch {
    $devices = @(Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Where-Object { $_.InstanceId -like 'USB\VID_*' } |
        ForEach-Object {
            $device = $_
            $props = @(Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName DEVPKEY_Device_Service,DEVPKEY_Device_CompatibleIds -ErrorAction Stop)
            [PSCustomObject]@{
                InstanceId = $device.InstanceId
                FriendlyName = $device.FriendlyName
                Class = $device.Class
                Status = $device.Status
                Service = ($props | Where-Object KeyName -eq 'DEVPKEY_Device_Service').Data
                CompatibleIds = @(($props | Where-Object KeyName -eq 'DEVPKEY_Device_CompatibleIds').Data)
            }
        })
}
# Optional physical grouping and port labels. A single batch avoids querying
# PnP properties once for every USB node; CIM remains usable without this module.
if ($devices.Count -gt 0) {
    try {
        $properties = @(Get-PnpDeviceProperty -InstanceId @($devices.InstanceId) -KeyName DEVPKEY_Device_ContainerId,DEVPKEY_Device_LocationInfo -ErrorAction Stop)
        $metadata = @{}
        foreach ($property in $properties) {
            if (-not $metadata.ContainsKey($property.InstanceId)) { $metadata[$property.InstanceId] = @{} }
            $metadata[$property.InstanceId][$property.KeyName] = $property.Data
        }
        foreach ($device in $devices) {
            if ($metadata.ContainsKey($device.InstanceId)) {
                $device | Add-Member -NotePropertyName ContainerId -NotePropertyValue ([string]$metadata[$device.InstanceId]['DEVPKEY_Device_ContainerId'])
                $device | Add-Member -NotePropertyName Location -NotePropertyValue ([string]$metadata[$device.InstanceId]['DEVPKEY_Device_LocationInfo'])
            }
        }
    } catch { } # Optional identity metadata must not hide a successful scan.
}
ConvertTo-Json -InputObject @($devices) -Compress -Depth 4
"""


def _pnp_query() -> list[dict]:
    """Enumerate USB nodes with UTF-8 output, actual service and HCI class IDs."""
    if sys.platform != "win32":
        return []
    import json
    import shutil

    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    executable = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    shell = str(executable) if executable.is_file() else shutil.which("powershell.exe")
    if shell is None:
        raise DongleDetectionError("Windows PowerShell was not found")
    try:
        result = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command", _PNP_SCRIPT],
            capture_output=True, timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise DongleDetectionError("USB enumeration timed out after 30 seconds") from exc
    except OSError as exc:
        raise DongleDetectionError(f"Could not start USB enumeration: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8-sig", errors="replace").strip()
        raise DongleDetectionError(f"USB enumeration failed (exit {result.returncode}): {detail[:1200]}")
    try:
        data = json.loads(result.stdout.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DongleDetectionError("USB enumeration returned invalid UTF-8 JSON") from exc
    # Accept the old single-object shape, but reject error text and malformed data.
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise DongleDetectionError("USB enumeration returned an unexpected data format")
    return data


_VIDPID_RE = re.compile(r"USB\\VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})", re.IGNORECASE)


def list_dongles(known_only: bool = False, *, devices: list[dict] | None = None) -> list[Dongle]:
    """Enumerate present USB Bluetooth dongles and their current driver binding.

    Composite interfaces are grouped by physical container when available;
    distinct adapters with the same VID/PID remain separate. Only known
    dongles, Bluetooth-class devices, and WinUSB-bound
    devices with Bluetooth HCI evidence are reported -- unrelated USB gear
    (including generic WinUSB devices and HID receivers) is skipped.
    """
    by_identity: dict[str, Dongle] = {}
    for entry in _pnp_query() if devices is None else devices:
        instance_id = entry.get("InstanceId") or ""
        match = _VIDPID_RE.match(instance_id)
        if not match:
            continue
        vid = int(match.group(1), 16)
        pid = int(match.group(2), 16)
        cls = (entry.get("Class") or "").lower()
        name = entry.get("FriendlyName") or ""
        is_known = (vid, pid) in KNOWN_DONGLES
        looks_bluetooth = cls == "bluetooth" or "bluetooth" in name.lower()
        service = (entry.get("Service") or "").lower()
        if cls == "hidclass" or service in ("hidusb", "usbccgp"):
            continue  # A keyboard/mouse receiver is not a USB Bluetooth radio.
        compatible_ids = entry.get("CompatibleIds") or []
        if isinstance(compatible_ids, str):
            compatible_ids = [compatible_ids]
        has_hci_interface = any(str(value).lower().startswith("usb\\class_e0&subclass_01&prot_01") for value in compatible_ids)
        looks_bluetooth = looks_bluetooth or service == "bthusb" or has_hci_interface
        # USBDevice is a generic setup class used by non-Bluetooth devices too.
        is_winusb = service == "winusb" or cls == "winusb"

        if not (is_known or looks_bluetooth):
            continue
        if known_only and not is_known:
            continue

        driver = "winusb" if is_winusb else "inbox" if cls == "bluetooth" or service == "bthusb" else "unknown"
        # A WinUSB-bound known dongle has no meaningful Class name; trust the
        # known list for its label. Prefer the active binding per physical group.
        container_id = str(entry.get("ContainerId") or "").casefold()
        if container_id.strip("{}0-") == "":
            container_id = ""
        dongle = Dongle(vid, pid, instance_id, name, driver, container_id, str(entry.get("Location") or ""))
        existing = by_identity.get(dongle.identity)
        rank = {"unknown": 0, "inbox": 1, "winusb": 2}
        if existing is None or rank[driver] > rank[existing.driver]:
            by_identity[dongle.identity] = dongle
    return list(by_identity.values())


def resolve_selected_adapter(identity: str) -> Dongle:
    """Resolve the exact choice and reject ambiguous VID/PID-only USB opens."""
    from .i18n import t
    dongles = list_dongles()
    chosen = next((device for device in dongles if device.identity == identity), None)
    if chosen is None:
        raise RuntimeError(t("적용한 동글을 찾지 못했습니다. 다시 연결하거나 목록에서 다른 동글을 적용해 주세요."))
    if sum(device.vidpid == chosen.vidpid for device in dongles) > 1:
        raise RuntimeError(t("같은 USB ID의 동글이 여러 개입니다. 사용할 동글 하나만 연결한 뒤 다시 검색해 주세요."))
    return chosen


def require_selected_adapter(identity: str, transport: str) -> Dongle:
    """Fail before opening USB if the saved physical selection is unavailable."""
    from .i18n import t
    chosen = resolve_selected_adapter(identity)
    if chosen.transport != transport:
        raise RuntimeError(t("동글 선택과 연결 설정이 일치하지 않습니다. 동글을 다시 적용해 주세요."))
    if not chosen.is_winusb:
        raise RuntimeError(t("선택한 동글을 WinUSB로 전환한 뒤 연결을 시작해 주세요."))
    return chosen


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
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def install_winusb(vid: int, pid: int, name: str = "Glideleaf Bluetooth") -> None:
    """Force-bind the dongle to WinUSB using wdi-simple. Requires admin."""
    exe = wdi_simple_path()
    if exe is None:
        raise FileNotFoundError(
            "wdi-simple.exe not found. Run scripts/fetch_wdi.ps1 or build libwdi."
        )
    from .paths import data_dir
    extraction = data_dir() / "drivers" / f"{vid:04x}-{pid:04x}"
    extraction.mkdir(parents=True, exist_ok=True)
    result = _run([
        str(exe),
        "--vid", f"0x{vid:04X}",
        "--pid", f"0x{pid:04X}",
        "--type", "0",  # 0 = WinUSB
        "--name", name,
        "--timeout", "120000",
        "--dest", str(extraction),
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
    hwid = f"VID_{vid:04X}&PID_{pid:04X}".lower()
    if result.returncode != 0:
        raise RuntimeError("Could not enumerate installed driver packages")
    # OEM filenames survive OS localization. Check the actual hardware ID.
    directory = Path(os.environ.get("WINDIR", r"C:\Windows")) / "INF"
    for name in dict.fromkeys(re.findall(r"\boem\d+\.inf\b", result.stdout.lower())):
        try:
            raw = (directory / name).read_bytes()
            text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        except (OSError, UnicodeError):
            continue  # Never delete a package we could not identify.
        if _block_matches(text.splitlines(), hwid):
            infs.append(name)
    return infs


def _block_matches(block: list[str], hwid: str) -> bool:
    text = "\n".join(block).lower()
    return "winusb" in text and re.search(re.escape(hwid.lower()) + r"(?![0-9a-f])", text) is not None


def restore_inbox(vid: int, pid: int) -> None:
    """Remove the WinUSB package and let Windows reapply the in-box driver."""
    for inf in _enum_winusb_oem_infs(vid, pid):
        result = _run(["pnputil", "/delete-driver", inf, "/uninstall", "/force"], timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"Could not restore driver package {inf}: {result.stderr.strip()}")
    if _run(["pnputil", "/scan-devices"], timeout=60).returncode != 0:
        raise RuntimeError("Windows device scan failed")


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
    # UAC may start a source checkout in System32, where `-m winuc` cannot
    # resolve our package. Use the package root explicitly.
    info.lpDirectory = str(Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                           else Path(__file__).resolve().parent.parent)
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


def install_winusb_elevated(vid: int, pid: int, name: str = "Glideleaf Bluetooth") -> None:
    # Prepare before UAC. The elevated child verifies the cached hash again.
    if wdi_simple_path() is None:
        from .driver_tool import ensure_tool
        ensure_tool()
    if is_admin():
        install_winusb(vid, pid, name)
        return
    code = _relaunch_elevated(
        ["--driver-install", "--vid", f"0x{vid:04X}", "--pid", f"0x{pid:04X}"]
    )
    if code != 0:
        from .paths import log_path
        raise RuntimeError(f"elevated driver install failed (exit {code}). Details: {log_path()}")


def restore_inbox_elevated(vid: int, pid: int) -> None:
    if is_admin():
        restore_inbox(vid, pid)
        return
    code = _relaunch_elevated(
        ["--driver-restore", "--vid", f"0x{vid:04X}", "--pid", f"0x{pid:04X}"]
    )
    if code != 0:
        from .paths import log_path
        raise RuntimeError(f"elevated driver restore failed (exit {code}). Details: {log_path()}")
