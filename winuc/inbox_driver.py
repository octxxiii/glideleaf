"""Select Microsoft's installed WinUSB model on one exact device instance.

Driver-list/selection APIs only change our in-memory device information set.
Only install() and restore() call DiInstallDevice or touch device parameters.
No custom INF, certificate, security setting or downloaded executable is used.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
from pathlib import Path
import uuid

from .native_driver import INTERFACE_GUID, verify_inf

SPDIT_CLASSDRIVER = 1
DI_ENUMSINGLEINF = 0x00010000
DI_FLAGSEX_ALLOWEXCLUDEDDRVS = 0x00000800
DIOD_INHERIT_CLASSDRVS = 2
ERROR_NO_MORE_ITEMS = 259


class GUID(C.Structure):
    _fields_ = [("Data1", W.DWORD), ("Data2", W.WORD), ("Data3", W.WORD), ("Data4", W.BYTE * 8)]


class DeviceInfo(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("ClassGuid", GUID), ("DevInst", W.DWORD), ("Reserved", C.c_size_t)]


class InstallParams(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("Flags", W.DWORD), ("FlagsEx", W.DWORD),
                ("hwndParent", W.HWND), ("InstallMsgHandler", C.c_void_p),
                ("InstallMsgHandlerContext", C.c_void_p), ("FileQueue", C.c_void_p),
                ("ClassInstallReserved", C.c_size_t), ("Reserved", W.DWORD), ("DriverPath", W.WCHAR * 260)]


class DriverInfo(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("DriverType", W.DWORD), ("Reserved", C.c_size_t),
                ("Description", W.WCHAR * 256), ("MfgName", W.WCHAR * 256),
                ("ProviderName", W.WCHAR * 256), ("DriverDate", W.FILETIME), ("DriverVersion", C.c_ulonglong)]


class DriverDetail(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("InfDate", W.FILETIME), ("CompatIDsOffset", W.DWORD),
                ("CompatIDsLength", W.DWORD), ("Reserved", C.c_size_t),
                ("SectionName", W.WCHAR * 256), ("InfFileName", W.WCHAR * 260),
                ("DrvDescription", W.WCHAR * 256), ("HardwareID", W.WCHAR * 1)]


def sized(cls):
    obj = cls()
    obj.cbSize = C.sizeof(obj)
    return obj


@dataclass(frozen=True)
class Candidate:
    inf: Path
    section: str
    description: str
    signer: str


def windows_directory() -> Path:
    api = C.WinDLL("kernel32.dll", use_last_error=True)
    api.GetWindowsDirectoryW.argtypes = [W.LPWSTR, W.UINT]
    api.GetWindowsDirectoryW.restype = W.UINT
    value = C.create_unicode_buffer(32768)
    length = api.GetWindowsDirectoryW(value, len(value))
    if not length or length >= len(value):
        raise C.WinError(C.get_last_error())
    return Path(value.value)


class DeviceSet:
    def __init__(self):
        self.api = C.WinDLL("setupapi.dll", use_last_error=True)
        self.handle = None
        self.built = False
        signatures = {
            "SetupDiCreateDeviceInfoList": ([C.c_void_p, W.HWND], C.c_void_p),
            "SetupDiDestroyDeviceInfoList": ([C.c_void_p], W.BOOL),
            "SetupDiGetDeviceInstallParamsW": ([C.c_void_p, C.c_void_p, C.POINTER(InstallParams)], W.BOOL),
            "SetupDiSetDeviceInstallParamsW": ([C.c_void_p, C.c_void_p, C.POINTER(InstallParams)], W.BOOL),
            "SetupDiBuildDriverInfoList": ([C.c_void_p, C.c_void_p, W.DWORD], W.BOOL),
            "SetupDiDestroyDriverInfoList": ([C.c_void_p, C.c_void_p, W.DWORD], W.BOOL),
            "SetupDiEnumDriverInfoW": ([C.c_void_p, C.c_void_p, W.DWORD, W.DWORD, C.POINTER(DriverInfo)], W.BOOL),
            "SetupDiGetDriverInfoDetailW": ([C.c_void_p, C.c_void_p, C.POINTER(DriverInfo), C.c_void_p, W.DWORD, C.POINTER(W.DWORD)], W.BOOL),
            "SetupDiSetSelectedDriverW": ([C.c_void_p, C.c_void_p, C.POINTER(DriverInfo)], W.BOOL),
            "SetupDiGetSelectedDriverW": ([C.c_void_p, C.c_void_p, C.POINTER(DriverInfo)], W.BOOL),
            "SetupDiOpenDeviceInfoW": ([C.c_void_p, W.LPCWSTR, W.HWND, W.DWORD, C.POINTER(DeviceInfo)], W.BOOL),
            "SetupDiGetDeviceRegistryPropertyW": ([C.c_void_p, C.POINTER(DeviceInfo), W.DWORD, C.POINTER(W.DWORD), C.c_void_p, W.DWORD, C.POINTER(W.DWORD)], W.BOOL),
            "SetupDiOpenDevRegKey": ([C.c_void_p, C.POINTER(DeviceInfo), W.DWORD, W.DWORD, W.DWORD, W.DWORD], W.HKEY),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result

    def __enter__(self):
        # No class restriction: the existing Bluetooth device and USBDevice
        # model may have different setup classes, just as in Device Manager.
        self.handle = self.api.SetupDiCreateDeviceInfoList(None, None)
        if self.handle in (None, C.c_void_p(-1).value):
            raise C.WinError(C.get_last_error())
        return self

    def __exit__(self, *_):
        if self.built:
            self.api.SetupDiDestroyDriverInfoList(self.handle, None, SPDIT_CLASSDRIVER)
        self.api.SetupDiDestroyDeviceInfoList(self.handle)

    def check(self, result):
        if not result:
            raise C.WinError(C.get_last_error())

    def select_winusb(self) -> Candidate:
        inf = windows_directory() / "INF" / "winusb.inf"
        signer = verify_inf(inf)
        if not signer.casefold().startswith("microsoft windows"):
            raise RuntimeError("The installed WinUSB INF is not signed by Microsoft Windows")
        params = sized(InstallParams)
        self.check(self.api.SetupDiGetDeviceInstallParamsW(self.handle, None, C.byref(params)))
        params.Flags |= DI_ENUMSINGLEINF
        # The Microsoft PnP model is excluded from ordinary class lists.
        params.FlagsEx |= DI_FLAGSEX_ALLOWEXCLUDEDDRVS
        params.DriverPath = str(inf)
        self.check(self.api.SetupDiSetDeviceInstallParamsW(self.handle, None, C.byref(params)))
        self.check(self.api.SetupDiBuildDriverInfoList(self.handle, None, SPDIT_CLASSDRIVER))
        self.built = True
        index = 0
        while True:
            driver = sized(DriverInfo)
            if not self.api.SetupDiEnumDriverInfoW(self.handle, None, SPDIT_CLASSDRIVER, index, C.byref(driver)):
                if C.get_last_error() == ERROR_NO_MORE_ITEMS:
                    break
                raise C.WinError(C.get_last_error())
            index += 1
            required = W.DWORD()
            self.api.SetupDiGetDriverInfoDetailW(self.handle, None, C.byref(driver), None, 0, C.byref(required))
            if required.value > 1024 * 1024:
                raise RuntimeError("Unexpected driver detail size")
            buffer = C.create_string_buffer(max(required.value, C.sizeof(DriverDetail)))
            detail = C.cast(buffer, C.POINTER(DriverDetail)).contents
            detail.cbSize = C.sizeof(DriverDetail)
            self.check(self.api.SetupDiGetDriverInfoDetailW(self.handle, None, C.byref(driver), buffer, len(buffer), C.byref(required)))
            if detail.SectionName.casefold() not in ("winusb", "winusb.nt", "winusb.ntamd64"):
                continue  # Never choose the ADB, billboard or lower-filter model.
            if str(Path(detail.InfFileName)).casefold() != str(inf).casefold():
                raise RuntimeError("Driver list did not resolve to the system WinUSB INF")
            self.check(self.api.SetupDiSetSelectedDriverW(self.handle, None, C.byref(driver)))
            return Candidate(inf, detail.SectionName, driver.Description, signer)
        raise RuntimeError("Windows does not expose a selectable inbox WinUSB model")

    def open_device(self, instance_id: str, *, inherit: bool = False) -> DeviceInfo:
        if not instance_id or not instance_id.upper().startswith("USB\\"):
            raise ValueError("An exact USB device instance is required")
        info = sized(DeviceInfo)
        self.check(self.api.SetupDiOpenDeviceInfoW(self.handle, instance_id, None,
                   DIOD_INHERIT_CLASSDRVS if inherit else 0, C.byref(info)))
        return info

    def service(self, info: DeviceInfo) -> str:
        buffer = C.create_unicode_buffer(1024)
        self.check(self.api.SetupDiGetDeviceRegistryPropertyW(self.handle, C.byref(info), 4,
                   None, buffer, C.sizeof(buffer), None))
        return buffer.value

    def install_selected(self, info: DeviceInfo, *, default: bool = False) -> bool:
        driver = sized(DriverInfo)
        if not default:
            self.check(self.api.SetupDiGetSelectedDriverW(self.handle, C.byref(info), C.byref(driver)))
        api = C.WinDLL("newdev.dll", use_last_error=True)
        api.DiInstallDevice.argtypes = [W.HWND, C.c_void_p, C.POINTER(DeviceInfo), C.POINTER(DriverInfo), W.DWORD, C.POINTER(W.BOOL)]
        api.DiInstallDevice.restype = W.BOOL
        reboot = W.BOOL()
        self.check(api.DiInstallDevice(None, self.handle, C.byref(info), None if default else C.byref(driver), 0, C.byref(reboot)))
        return bool(reboot.value)

    def interface_guid(self, info: DeviceInfo, *, add: bool):
        import winreg
        key = self.api.SetupDiOpenDevRegKey(self.handle, C.byref(info), 1, 0, 1, winreg.KEY_READ | winreg.KEY_WRITE)
        if key in (None, C.c_void_p(-1).value):
            raise C.WinError(C.get_last_error())
        try:
            try:
                params = (winreg.CreateKeyEx(key, "Device Parameters", 0, winreg.KEY_READ | winreg.KEY_WRITE)
                          if add else winreg.OpenKey(key, "Device Parameters", 0, winreg.KEY_READ | winreg.KEY_WRITE))
            except FileNotFoundError:
                return False
            with params:
                try:
                    values, kind = winreg.QueryValueEx(params, "DeviceInterfaceGUIDs")
                    if kind != winreg.REG_MULTI_SZ:
                        raise RuntimeError("Unexpected existing device interface GUID value type")
                except FileNotFoundError:
                    values = []
                updated = merge_guids(values, add=add)
                if updated != values:
                    if updated:
                        winreg.SetValueEx(params, "DeviceInterfaceGUIDs", 0, winreg.REG_MULTI_SZ, updated)
                    else:
                        winreg.DeleteValue(params, "DeviceInterfaceGUIDs")
                return updated != values
        finally:
            winreg.CloseKey(key)


def merge_guids(values: list[str], *, add: bool) -> list[str]:
    for value in values:
        uuid.UUID(value.strip("{}"))  # Preserve other well-formed registrations.
    ours = uuid.UUID(INTERFACE_GUID.strip("{}"))
    if add:
        return list(values) if any(uuid.UUID(v.strip("{}")) == ours for v in values) else [*values, INTERFACE_GUID]
    return [v for v in values if uuid.UUID(v.strip("{}")) != ours]


def probe(instance_id: str | None = None) -> Candidate:
    """Read-only. Selecting a driver in a transient set does not install it."""
    with DeviceSet() as devices:
        candidate = devices.select_winusb()
        if instance_id:
            info = devices.open_device(instance_id, inherit=True)
            selected = sized(DriverInfo)
            devices.check(devices.api.SetupDiGetSelectedDriverW(devices.handle, C.byref(info), C.byref(selected)))
        return candidate


def install(instance_id: str) -> bool:
    with DeviceSet() as devices:
        devices.select_winusb()  # Recheck Microsoft's catalog inside elevation.
        info = devices.open_device(instance_id, inherit=True)
        added_guid = devices.interface_guid(info, add=True)
        try:
            return devices.install_selected(info)
        except Exception:
            if added_guid:
                try:
                    if devices.service(info).casefold() != "winusb":
                        devices.interface_guid(info, add=False)
                except OSError:
                    pass  # Preserve the installation failure for the caller.
            raise


def restore(instance_id: str) -> bool:
    with DeviceSet() as devices:
        info = devices.open_device(instance_id)
        reboot = devices.install_selected(info, default=True)
        if not reboot and devices.service(info).casefold() != "winusb":
            devices.interface_guid(info, add=False)
        return reboot


def readiness() -> dict:
    """Read-only check of the Windows supplied driver, not a hardware test."""
    try:
        candidate = probe()
    except Exception as exc:
        return {"ready": False, "method": "windows-inbox-winusb", "error": str(exc)}
    return {"ready": True, "method": "windows-inbox-winusb", "inf": str(candidate.inf),
            "section": candidate.section, "signer": candidate.signer,
            "hardware_verified": False}
