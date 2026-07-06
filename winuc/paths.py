"""Per-user data locations for WinUC.

Everything the running app writes (config, pairing keys, logs) lives under
%LOCALAPPDATA%\\WinUC so the installed program directory can stay read-only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / "WinUC"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "config.json"


def keystore_path() -> Path:
    return data_dir() / "pairing_keys.json"


def log_path() -> Path:
    return data_dir() / "winuc.log"


def firmware_dir() -> Path:
    """Bundled Realtek firmware (dev tree or PyInstaller bundle)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "firmware"
        if bundled.is_dir():
            return bundled
    return Path(__file__).resolve().parent.parent / "firmware"
