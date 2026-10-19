# PyInstaller spec for WinUC (GUI tray build).
# Build:  pyinstaller packaging/winuc.spec  (run from the repo root)

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = Path.cwd()

hiddenimports = (
    collect_submodules("bumble")
    + collect_submodules("pystray")
    + collect_submodules("PIL")
    + ["libusb_package", "usb1"]
)

datas = [(str(ROOT / "LICENSE"), "."), (str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")]
notices = ROOT / "build" / "licenses"
if not (notices / "dependencies.json").is_file():
    raise RuntimeError("Run python scripts/collect_licenses.py before packaging")
datas += [(str(notices), "licenses")]
# Bundle Realtek firmware and the wdi-simple tool if present.
fw = ROOT / "firmware"
if fw.is_dir():
    datas += [(str(p), "firmware") for p in fw.glob("*.bin")]
tools = ROOT / "tools"
if tools.is_dir():
    datas += [(str(p), "tools") for p in tools.iterdir() if p.is_file()]
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
