# Changelog

## Unreleased

- USB enumeration now uses explicit UTF-8 and actual driver service/HCI IDs,
  with a CIM query and a PnP fallback. Scan failures are surfaced separately
  from an empty result; generic USBDevice nodes no longer imply WinUSB.
- Added copyable USB diagnostics to adapter setup, a `--diagnose` CLI, and a
  standalone PowerShell report for the affected PC. No driver changes are made.
- HID keyboard/mouse receivers are excluded from Bluetooth-radio candidates.

## 0.1.0 — source preview

First Glideleaf source publication, derived from fuba/winuc.

- Nine-language desktop UI with system detection and persisted selection.
- Connection panel, diagnostics, translated settings and fuba acknowledgements.
- Validated atomic config saving and language-only updates without BLE restart.
- Service startup/stop and input-capture cleanup improvements.
- Device-specific driver restoration and removal of hard-coded uninstall driver actions.
- Windows test workflow, public documentation and dependency-notice collection.

Physical iPad/adapter and clean-machine installer qualification are pending.
This source preview does not advertise a stable binary release.

Upstream history is preserved in Git. The original project is
[fuba/winuc](https://github.com/fuba/winuc), MIT, Copyright (c) 2026 fuba.
