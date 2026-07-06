"""Run WinUC at Windows sign-in.

Uses the per-user registry Run key (HKCU\\...\\Run), which needs no admin
rights and is trivial to remove. The value points at the installed launcher
(the frozen exe) started minimized to the tray.
"""

from __future__ import annotations

import sys

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "WinUC"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        # Installed build: the exe launches straight into the tray.
        return f'"{sys.executable}" --tray'
    # Dev run: python -m winuc --tray
    return f'"{sys.executable}" -m winuc --tray'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False


def enable() -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _launch_command())


def disable() -> None:
    if sys.platform != "win32":
        return
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except FileNotFoundError:
        pass


def set_enabled(enabled: bool) -> None:
    enable() if enabled else disable()
