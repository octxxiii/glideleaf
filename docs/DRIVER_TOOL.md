# App-owned adapter setup and release signing

## User flow

Select a dedicated Bluetooth USB adapter, click **Connect adapter**, and approve
Windows elevation. With a qualified signed release, Glideleaf performs selection
saving, native driver installation, binding verification and connection startup
inside its own flow. There is no Zadig, wdi-simple or downloaded installer.
**Restore normal Bluetooth** uses the same exact-selection/elevation boundary.

## Implementation and trust boundary

- `winuc/native_driver.py` supplies canonical, hardware-specific INF sources,
  Windows `SetupVerifyInfFileW` catalog verification and
  `UpdateDriverForPlugAndPlayDevicesW` installation.
- `winuc/driver.py` invokes the app itself as the elevated helper, passing the
  selected physical identity, VID/PID and a per-operation result file. Both
  caller and child revalidate the selection. Duplicate present VID/PIDs are
  rejected because the Windows update API matches hardware IDs.
- The driver is Microsoft's existing WinUSB (`winusb.sys`), not a new kernel
  binary. Our INF assigns a stable interface GUID for userspace access.
- Only four declared USB IDs have templates. Listing a template is not physical
  chipset qualification. The current native package target is Windows x64. Composite USB interfaces
  are rejected before elevation to avoid replacing a parent and its Wi-Fi/HID siblings.
- The INF must match the app's exact expected bytes, and Windows must verify its
  signed catalog. Modified/missing/untrusted packages stop before UAC. The
  elevated child repeats package checks before any device change.
- The Windows update call uses FORCE only to replace the higher-ranked inbox
  Bluetooth driver. No unsigned install flags, generated trusted certificates,
  security exclusions, policy changes or unverified fallbacks are used.
- Helper errors return through structured per-operation results; a reboot request
  is distinguished from failure. Success also requires the actual selected
  adapter to be bound to WinUSB. Configuration save failure stops installation.
- Diagnostic enumeration checks file presence only; signature and installation
  operations do not run on the Tk UI thread or during ordinary enumeration.
- Restore checks actual OEM INF content for the target VID/PID and WinUSB before
  deletion and confirms that inbox Bluetooth is active afterward.

Microsoft references:
[WinUSB installation](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/winusb-installation),
[INF signature verification](https://learn.microsoft.com/en-us/windows/win32/api/setupapi/nf-setupapi-setupverifyinffilew),
[native update API](https://learn.microsoft.com/en-us/windows/win32/api/newdev/nf-newdev-updatedriverforplugandplaydevicesw).

## Build and sign

1. Generate exact INF sources with
   `.venv/Scripts/python.exe scripts/prepare_native_drivers.py --templates-only`.
2. With WDK installed, use a fresh output directory and run
   `scripts/prepare_native_drivers.py --inf2cat <Inf2Cat.exe>` to validate the INF
   sources and generate **unsigned** catalogs. Set `--os` for the Windows versions
   qualified by that WDK. Existing catalogs are never overwritten.
3. Obtain production catalog signatures accepted by the target Windows driver
   signing policy (for example through the eligible Microsoft hardware signing
   process). This is distinct from signing the app. Do not install test roots or
   turn off signature enforcement for a public release. Returned INF bytes must
   still match the canonical source; review source/version changes explicitly.
4. Verify the returned packages with
   `scripts/check_native_release.py --root <signed-package-directory>`.
5. Build using `packaging/build.ps1 -Release -DriverPackageDir <directory>
   -CertificateThumbprint <thumbprint> -Publisher <certificate-publisher>
   -SignToolPath <signtool.exe>`. Signing uses an existing private key in the local
   certificate store; no private key/password is committed or requested in chat.
   A hardware/cloud signer can be integrated once the real signing profile is
   available. The current script supports the local certificate-store route.
6. The build verifies the app signature and publisher, plus the **bundled** driver
   package signatures. A development portable build is explicitly unsigned and
   cannot be presented as a qualified release. PyInstaller refuses to bundle
   untrusted packages supplied through `GLIDELEAF_DRIVER_PACKAGES`.

For source development, signed packages can be placed in the ignored
`driver-packages/` directory. Build outputs, signing keys and certificates are
not committed. `python -m glideleaf --driver-check [report.json]` checks package
readiness without changing drivers, even when user config is invalid.

## Outstanding release evidence

Local generation was validated with Microsoft.Windows.WDK.x64 NuGet
10.0.28000.2526 (package SHA-256
`63c939fb5a79295bf40e941db592681272219b04edff095fe2f3d123e5579a90`).
All four INF sources passed Inf2Cat with no errors/warnings for
`10_VB_X64,10_CO_X64,10_NI_X64,10_GE_X64,10_25H2_X64`; unsigned catalogs
were produced under `build/native-win10-win11`. Build tools are not shipped.

No production signing credential/profile has been provided. Signed application
and catalog release artifacts therefore remain incomplete. No physical CSR
adapter is available on the development PC. Before release, record Windows
version, actual CSR USB ID, install/UAC behavior, WinUSB binding, iPad pairing,
continuous keyboard/pointer input, unplug/reconnect, restore and reboot behavior.
Automated/mocked tests and an unsigned portable build do not replace that record.

The initial elevated result channel supports same-user UAC elevation. Standard-user installation with a different administrator account remains unqualified and may stop before mutation if its temporary result directory differs. Include this in device/release testing.
