"""Glideleaf-owned WinUSB setup using Windows APIs and signed INF packages.

No third-party installer, generated trust certificate, security exclusions or
unsigned fallback. Package generation is separate from production signing.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from dataclasses import dataclass
from pathlib import Path
import platform
import struct
import sys

from .i18n import t

SUPPORTED_IDS = ((0x0A12, 0x0001), (0x0411, 0x0374), (0x0BDA, 0x8771), (0x0BDA, 0xC820))
INTERFACE_GUID = "{F2B4D753-8538-4A7D-933B-57002C4FBB57}"
REBOOT_EXIT_CODE = 3010


class RebootRequired(RuntimeError):
    def __init__(self):
        super().__init__(t("드라이버 전환을 완료하려면 Windows를 다시 시작한 뒤 연결해 주세요."))


@dataclass(frozen=True)
class Package:
    inf: Path
    catalog: Path
    signer: str


def package_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "driver-packages"


def package_name(vid: int, pid: int) -> str:
    if (vid, pid) not in SUPPORTED_IDS:
        raise RuntimeError(t("이 동글의 자체 설치 패키지는 아직 지원하지 않습니다."))
    return f"{vid:04x}-{pid:04x}"


def inf_bytes(vid: int, pid: int) -> bytes:
    """Canonical source: no downloaded/generated executable or kernel driver."""
    package_name(vid, pid)
    text = f'''[Version]
Signature="$Windows NT$"
Class=USBDevice
ClassGuid={{88BAE032-5A81-49f0-BC3D-A4FF138216D6}}
Provider=%Provider%
CatalogFile=glideleaf.cat
DriverVer=10/19/2026,0.1.0.0
PnpLockdown=1

[Manufacturer]
%Provider%=Models,NTamd64

[Models.NTamd64]
%DeviceName%=Install,USB\\VID_{vid:04X}&PID_{pid:04X}

[Install]
Include=winusb.inf
Needs=WINUSB.NT

[Install.Services]
Include=winusb.inf
Needs=WINUSB.NT.Services

[Install.HW]
AddReg=Interface

[Interface]
HKR,,DeviceInterfaceGUIDs,0x00010000,"{INTERFACE_GUID}"

[Strings]
Provider="Glideleaf"
DeviceName="Glideleaf dedicated Bluetooth adapter ({vid:04X}:{pid:04X})"
'''
    return text.replace("\n", "\r\n").encode("utf-16")


class _SignerInfo(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("CatalogFile", wt.WCHAR * 260),
                ("DigitalSigner", wt.WCHAR * 260), ("DigitalSignerVersion", wt.WCHAR * 260)]


def verify_inf(inf: Path) -> str:
    """Verify that this INF is covered by a trusted catalog, without installing."""
    api = ctypes.WinDLL("setupapi.dll", use_last_error=True)
    verify = api.SetupVerifyInfFileW
    verify.argtypes = [wt.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(_SignerInfo)]
    verify.restype = wt.BOOL
    info = _SignerInfo()
    info.cbSize = ctypes.sizeof(info)
    if not verify(str(inf), None, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return info.DigitalSigner


def prepare_package(vid: int, pid: int, *, root: Path | None = None) -> Package:
    name = package_name(vid, pid)
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64") or struct.calcsize("P") != 8:
        raise RuntimeError(t("자체 동글 설치는 현재 Windows x64에서 지원합니다."))
    folder = (root if root is not None else package_root()) / name
    inf, cat = folder / "glideleaf.inf", folder / "glideleaf.cat"
    if not inf.is_file() or not cat.is_file():
        raise RuntimeError(t("서명된 동글 설치 패키지가 아직 준비되지 않았습니다. 이 빌드에서는 드라이버를 변경하지 않습니다."))
    if inf.read_bytes() != inf_bytes(vid, pid):
        raise RuntimeError(t("동글 설치 패키지가 앱의 대상 장치와 일치하지 않습니다. 설치를 중단했습니다."))
    try:
        signer = verify_inf(inf.resolve())
    except OSError as exc:
        raise RuntimeError(t("동글 설치 패키지의 Windows 서명 검증에 실패했습니다. 설치를 중단했습니다.")) from exc
    return Package(inf.resolve(), cat.resolve(), signer)


def update_driver(vid: int, pid: int, package: Package) -> bool:
    """Call only after elevation and exact physical target revalidation."""
    api = ctypes.WinDLL("newdev.dll", use_last_error=True)
    update = api.UpdateDriverForPlugAndPlayDevicesW
    update.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.POINTER(wt.BOOL)]
    update.restype = wt.BOOL
    reboot = wt.BOOL(False)
    # FORCE is required to replace a higher-ranked inbox Bluetooth driver.
    # Do not use NONINTERACTIVE: Windows may need to show security/error UI.
    if not update(None, f"USB\\VID_{vid:04X}&PID_{pid:04X}", str(package.inf), 1, ctypes.byref(reboot)):
        raise ctypes.WinError(ctypes.get_last_error())
    return bool(reboot.value)


def readiness(*, root: Path | None = None, verify: bool = True) -> dict:
    packages = []
    for vid, pid in SUPPORTED_IDS:
        if not verify:
            folder = (root if root is not None else package_root()) / package_name(vid, pid)
            packages.append({"usb_id": f"{vid:04X}:{pid:04X}", "present":
                             all((folder / name).is_file() for name in ("glideleaf.inf", "glideleaf.cat"))})
            continue
        try:
            package = prepare_package(vid, pid, root=root)
            packages.append({"usb_id": f"{vid:04X}:{pid:04X}", "ready": True, "signer": package.signer})
        except (OSError, RuntimeError) as exc:
            packages.append({"usb_id": f"{vid:04X}:{pid:04X}", "ready": False, "error": str(exc)})
    return {"backend": "windows-native", "external_installer": False,
            "ready": all(p["ready"] for p in packages) if verify else None,
            "verification_performed": verify, "packages": packages}
