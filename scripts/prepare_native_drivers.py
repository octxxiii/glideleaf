"""Generate canonical INF sources and optionally unsigned WDK catalogs.

This command never installs a driver, adds a certificate or signs a package.
Use --templates-only on machines without WDK. Catalogs must subsequently obtain
production signatures before the app/release verifier will accept them.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from winuc.native_driver import SUPPORTED_IDS, inf_bytes, package_name


def generate(root: Path) -> list[Path]:
    folders = [root / package_name(vid, pid) for vid, pid in SUPPORTED_IDS]
    # Do not invalidate an existing signed package by regenerating its catalog.
    if any((folder / "glideleaf.cat").exists() for folder in folders):
        raise RuntimeError("Output already contains catalogs; use a fresh output directory")
    for (vid, pid), folder in zip(SUPPORTED_IDS, folders):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "glideleaf.inf").write_bytes(inf_bytes(vid, pid))
    return folders


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/native-drivers"))
    parser.add_argument("--templates-only", action="store_true")
    parser.add_argument("--inf2cat", default=None)
    parser.add_argument("--os", default="10_VB_X64,10_CO_X64,10_NI_X64,10_GE_X64,10_25H2_X64",
                        help="Inf2Cat OS targets, per installed WDK")
    args = parser.parse_args()
    try:
        folders = generate(args.output.resolve())
        print(f"Generated {len(folders)} hardware-specific WinUSB INF sources: {args.output}")
        if args.templates_only:
            print("UNSIGNED sources only. Driver installation and release are not ready.")
            return 0
        tool = args.inf2cat or shutil.which("Inf2Cat.exe")
        if not tool:
            raise RuntimeError("WDK Inf2Cat.exe is missing. Sources are ready; catalog generation/signing remains incomplete.")
        for folder in folders:
            subprocess.run([tool, f"/driver:{folder}", f"/os:{args.os}", "/uselocaltime"], check=True)
        print("Unsigned catalogs generated. Obtain production catalog signatures before release.")
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
