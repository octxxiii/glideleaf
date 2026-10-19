# Native setup validation — 2026-10-19

Status: **implementation/build validated; production signatures and physical
CSR qualification outstanding. Not a qualified binary release.**

| Check | Current evidence |
| --- | --- |
| Automated suite | 128 passed; one existing Bumble deprecation warning |
| Real desktop GUI | Korean and English smoke checks passed using simulated adapter records |
| BLE virtual controller | Public `python -m glideleaf --selftest` passed; no physical radio opened |
| Windows signing API | Actual `SetupVerifyInfFileW` accepted installed Microsoft `winusb.inf`; rejected unsigned test/catalog packages |
| WDK structural/signability check | All 4 hardware-specific INFs passed with zero errors and warnings; unsigned CATs generated |
| WDK build tool source | Microsoft.Windows.WDK.x64 NuGet 10.0.28000.2526 |
| Inf2Cat OS targets | 10_VB_X64, 10_CO_X64, 10_NI_X64, 10_GE_X64, 10_25H2_X64 |
| App build | PyInstaller portable development build completed |
| Frozen read-only checks | `--driver-check` returned not-ready (exit 1); `--diagnose` returned exit 0 and JSON output |
| Release gate | Actual unsigned app was rejected by `packaging/verify_release.ps1` |
| Safety boundaries | Missing/untrusted packages fail before UAC/service stop; duplicate/disconnected/composite targets fail without native update; config-save failure prevents installation; reboot is distinct from success |
| Real driver change | Not performed on the development PC |
| Production app/catalog signing | Not performed; no signing credential/profile provided |

Generated catalogs are in the ignored `build/native-win10-win11` directory;
machine-specific diagnostics and GUI captures are in ignored `artifacts`.
The development app is `dist/Glideleaf/Glideleaf.exe`. Those files are not
published as release assets. Sources, verification commands and signing steps
are documented in [DRIVER_TOOL.md](DRIVER_TOOL.md).

Before release, the actual CSR PC must confirm install/UAC behavior, WinUSB
binding, iPad pairing and continuous input, disconnect/reconnect, normal
Bluetooth restoration, reboot handling, and standard-user elevation scenarios.
Signability tests establish package structure, not physical compatibility.
