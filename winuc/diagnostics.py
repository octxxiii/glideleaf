"""Read-only USB diagnostics. Never open a radio, switch drivers or read keys."""
from __future__ import annotations

import json
import platform
from datetime import datetime, timezone

from . import __version__
from . import driver
from .native_driver import readiness


def build_report(devices: list[dict], error: str | None = None) -> dict:
    native = readiness(verify=False)
    adapters = driver.list_dongles(devices=devices)
    usb = []
    for entry in devices:
        match = driver._VIDPID_RE.match(entry.get("InstanceId") or "")
        if not match:
            continue
        key = (int(match.group(1), 16), int(match.group(2), 16))
        individual = driver.list_dongles(devices=[entry])
        candidate = individual[0] if individual else None
        usb.append({
            "usb_id": f"{key[0]:04X}:{key[1]:04X}",
            # Keep interface identity, omit the trailing device serial/instance.
            "hardware_id": entry["InstanceId"].split("\\", 2)[1],
            "name": entry.get("FriendlyName") or "",
            "class": entry.get("Class") or "",
            "service": entry.get("Service") or "",
            "usb_location": entry.get("Location") or "",
            "status": entry.get("Status") or "",
            "problem_code": entry.get("ProblemCode"),
            "compatible_ids": entry.get("CompatibleIds") or [],
            "bluetooth_candidate": candidate is not None,
            "driver_binding": candidate.driver if candidate else None,
        })
    return {
        "schema_version": 1,
        "app": "Glideleaf",
        "app_version": __version__,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "system": platform.system(),
        "windows_version": platform.win32_ver()[0],
        "python_version": platform.python_version(),
        "enumeration_error": error,
        "usb_node_count": len(usb),
        "bluetooth_candidate_count": len(adapters),
        "automatic_driver_tool_present": all(p["present"] for p in native["packages"]),
        "native_driver": native,
        "usb_devices": usb,
        "scope": "Read-only enumeration. No radio opened, driver changed, pairing keys or input logs read. Device serial suffixes omitted.",
    }


def collect_report() -> dict:
    try:
        return build_report(driver._pnp_query())
    except driver.DongleDetectionError as exc:
        return build_report([], str(exc))


def report_text(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)
