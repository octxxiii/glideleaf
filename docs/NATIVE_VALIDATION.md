# Native setup validation — 2026-10-19

Status: **Windows inbox WinUSB selection validated read-only; physical CSR setup and public binary release still unqualified.**

| Check | Current evidence |
| --- | --- |
| Automated suite | 131 passed; one existing Bumble deprecation warning |
| Windows model probe | `--driver-check` returned ready; selected `WINUSB` from Microsoft-signed `C:\Windows\INF\winusb.inf` |
| Exact-device probe | A transient SetupAPI set selected that model for the local Intel instance; no driver installation was called |
| Target guards | Only declared USB IDs, exact selected instance, non-composite, and unique present VID/PID proceed to installation |
| Virtual BLE controller | `python -m glideleaf --selftest` previously passed; no physical radio opened |
| Real driver change | Not performed on the development PC; CSR is on another PC |
| Production app signing | Not performed; no credential provided here |

The default installer now uses `DiInstallDevice` with the existing Microsoft WinUSB model and no custom catalog. Old WDK-generated INF/CAT test outputs under ignored `build/native-win10-win11` remain optional development artifacts, not runtime dependencies. The `--driver-check` result is a system capability probe, not proof that this CSR adapter can actually run BLE through WinUSB. The unsigned development build is not a qualified binary release.

Before release, test the actual CSR PC: UAC and any security policy result, exact USB ID, WinUSB binding, pairing and sustained pointer/keyboard operation with an iPad, disconnect/reconnect, reboot, and restoration of normal Bluetooth. Same-user UAC and different-admin elevation also need separate checks. See [DRIVER_TOOL.md](DRIVER_TOOL.md).
