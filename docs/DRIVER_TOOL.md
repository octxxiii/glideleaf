# Official WinUSB installer preparation

Glideleaf downloads **official Zadig 2.9**, not the unsigned community CLI used
in an earlier development revision. Existing community caches are never used
by the GUI installation path. No antivirus exclusions, security-policy changes,
or unverified fallbacks are applied.

- Publisher: Akeo Consulting
- Official page: https://zadig.akeo.ie/
- Release: https://github.com/pbatard/libwdi/releases/tag/v1.5.1
- Download: https://github.com/pbatard/libwdi/releases/download/v1.5.1/zadig-2.9.exe
- SHA-256: `4ecaa95df3da3621486a043aef8b3050b8bafe7c901402871e816229ef82039b`
- Corresponding source: https://github.com/pbatard/libwdi/tree/v1.5.1
- Zadig: GPL-3.0-or-later; libwdi: LGPL-3.0-or-later.
- License texts are preserved in `winuc/licenses` and copied beside the download.

After confirming Switch to WinUSB, Glideleaf verifies both the pinned file hash
and Windows Authenticode status `Valid` with signer `Akeo Consulting`. Cached
files are signature-checked again before launch. Download and signature failure
stop setup. Downloads are size-limited to 32 MiB and have a 60-second network
inactivity timeout. Partial files are removed on failure.

The official GUI opens visibly with its own administrator prompt. Glideleaf
shows the selected adapter name and USB VID/PID before opening it. **The user
must select that device, select WinUSB, and confirm installation in Zadig.**
Zadig is configured to list devices, hide hubs, default to WinUSB and close after
success. Glideleaf does not click controls or select the first device on the
user's behalf. Closing Zadig is not treated as success: the selected VID/PID
must be uniquely present and actually bound to WinUSB before success is shown.

Official Zadig is not a command-line drop-in replacement for wdi-simple.
This flow automates tool preparation, not the final device selection/confirmation.
The app's own executable remains unsigned; official tool signing is not a claim
that every security policy will permit either program. A reported security
block still requires its exact message/file/threat name to diagnose.

Read-only discovery, Apply and ordinary startup never download or install a
driver. The cached tool lives under `%LOCALAPPDATA%\WinUC\tools\zadig-2.9`.
For a developer-only prefetch, run `scripts/fetch_wdi.ps1` (legacy filename).

Local validation covers real download and Authenticode verification, isolated
failure tests, GUI behavior and packaging. Physical driver installation and
CSR/iPad pairing remain unverified on the development PC.
