# PyInstaller spec for WinUC (GUI tray build).
# Build:  pyinstaller packaging/winuc.spec  (run from the repo root)

from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = Path(SPECPATH).parent

hiddenimports = (
    collect_submodules("bumble")
    + collect_submodules("pystray")
    + collect_submodules("PIL")
    + ["libusb_package", "usb1"]
)

datas = [(str(ROOT / "LICENSE"), "."), (str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")]
datas += [(str(ROOT / "winuc" / "licenses"), "winuc/licenses")]
datas += [(str(ROOT / "winuc" / "gui" / "assets" / "glideleaf-mark.png"), "winuc/gui/assets")]
driver_packages = os.environ.get("GLIDELEAF_DRIVER_PACKAGES")
if driver_packages:
    import sys
    sys.path.insert(0, str(ROOT))
    from winuc.native_driver import readiness
    package_root = Path(driver_packages).resolve()
    status = readiness(root=package_root)
    if not status["ready"]:
        raise RuntimeError(f"Native driver packages are not release-ready: {status}")
    datas += [(str(package_root), "driver-packages")]
notices = ROOT / "build" / "licenses"
if not (notices / "dependencies.json").is_file():
    raise RuntimeError("Run python scripts/collect_licenses.py before packaging")
datas += [(str(notices), "licenses")]
# Optional firmware; external driver installers are downloaded and verified.
fw = ROOT / "firmware"
if fw.is_dir():
    datas += [(str(p), "firmware") for p in fw.glob("*.bin")]
# libusb backend DLL shipped by libusb_package.
datas += collect_data_files("libusb_package")

block_cipher = None

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "_pytest"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Glideleaf",
    debug=False,
    strip=False,
    upx=False,
    console=False,           # windowed (no console) — tray app
    icon=str(ROOT / "packaging" / "winuc.ico") if (ROOT / "packaging" / "winuc.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Glideleaf",
)
