# Automatic WinUSB installer

The adapter wizard prepares `wdi-simple.exe` only after the user confirms
Switch to WinUSB. Apply, discovery, diagnostics and ordinary startup never
download or install a driver. Windows UAC remains required for the driver change.

The separate executable is an **unofficial community build** of libwdi:

- Release: https://github.com/Timocop/libwdi-wdi-releases/releases/tag/v1.0
- Source snapshot: https://github.com/Timocop/libwdi-wdi-releases/tree/v1.0
- Upstream: https://github.com/pbatard/libwdi
- License: LGPL-3.0-or-later; GPL/LGPL texts are in `winuc/licenses`.

The release archives contain other programs too. Glideleaf extracts only
`wdi-simple.exe`, without executing the archive or extracting archive paths.
The executable is invoked as a separate process, with the selected VID/PID and
WinUSB driver type. Driver output goes to the app's per-user data directory.
An explicitly supplied local tool in the existing `tools` location remains
available for users providing their own build.

| Artifact | SHA-256 |
| --- | --- |
| x64.zip | d5aace13a3c1d5980113a5938fbee2edaa788ed625e3c554ff47da24cde39cda |
| x64 wdi-simple.exe | 27b6d9847d874674b7c412af124acf64b0b1efa397e3bbea8eab9950a6a08ee0 |
| x86.zip | ac37a6a24eb9e550135218e5af30669d6e8a3d78c5d36f9b4ab6c1f6232ef266 |
| x86 wdi-simple.exe | da0e280cf66d7261ceb436ff48d45bbd6f5ab9b70180b487a41a2957f9723bf6 |

These hashes pin the inspected release bytes; they do not establish a
reproducible build or an official upstream signature. Updating the tool requires
reviewing provenance and updating both hashes deliberately. There is no fallback
to an unverified download.

Downloads are limited to 32 MiB, timeout after 60 seconds of network inactivity,
and are verified before an atomic write under `%LOCALAPPDATA%\WinUC\tools`.
The hash of a cached download is checked before reuse, including in the elevated
child. Interrupted downloads leave no executable. Network failures can be
retried from the wizard; errors after elevation point to
`%LOCALAPPDATA%\WinUC\winuc.log`.

Local validation covers download/cache/integrity/error handling and GUI behavior.
Physical CSR/iPad pairing and driver installation remain unverified on the
development PC.
