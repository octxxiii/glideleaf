"""CLI / GUI entry point: python -m winuc"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from .config import Config
from .paths import config_path, log_path


def _set_firmware_dir() -> None:
    """Register the bundled firmware/ directory for bumble's Realtek loader."""
    from .paths import firmware_dir

    fw = firmware_dir()
    if fw.is_dir():
        os.environ.setdefault("BUMBLE_RTK_FIRMWARE_DIR", str(fw))


def _fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def _setup_logging(verbose: bool, to_file: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if to_file:
        try:
            handlers.append(logging.FileHandler(log_path(), encoding="utf-8"))
        except OSError:
            pass
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )
    if not verbose:
        logging.getLogger("bumble").setLevel(logging.WARNING)


def main() -> int:
    _fix_console_encoding()
    parser = argparse.ArgumentParser(
        prog="winuc",
        description="WinUC - Universal Control for Windows (control an iPad from your PC)",
    )
    parser.add_argument("--config", default=None, help="Path to a config file")
    parser.add_argument("--tray", action="store_true", help="Run as a system-tray app (GUI)")
    parser.add_argument("--setup", action="store_true", help="Open the setup wizard (GUI)")
    parser.add_argument("--selftest", action="store_true",
                        help="Validate the BLE layer on a virtual controller (no dongle)")
    parser.add_argument("--no-capture", action="store_true",
                        help="Start BLE only, without input hooks (for pairing checks)")
    parser.add_argument("--verbose", "-v", action="store_true")
    # Elevated driver verbs (invoked by the GUI via UAC; not for normal use).
    parser.add_argument("--driver-install", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--driver-restore", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--vid", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--pid", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    _setup_logging(args.verbose, to_file=args.tray)

    # --- Elevated driver operations (run in a short-lived elevated process) ---
    if args.driver_install or args.driver_restore:
        from . import driver

        vid = int(args.vid, 0)
        pid = int(args.pid, 0)
        try:
            if args.driver_install:
                driver.install_winusb(vid, pid)
            else:
                driver.restore_inbox(vid, pid)
        except Exception as exc:  # surfaced to caller via exit code
            print(f"driver operation failed: {exc}", file=sys.stderr)
            return 1
        return 0

    config_file = Path(args.config) if args.config else config_path()
    config = Config.load(config_file)
    if not config_file.exists():
        config.save(config_file)

    # --- Virtual self-test (no hardware) ---
    if args.selftest:
        from .selftest import run_selftest

        result = asyncio.run(run_selftest(config, keystore_file="selftest_keys.json"))
        Path("selftest_keys.json").unlink(missing_ok=True)
        print("Self-test passed. Received reports:")
        for report_id, values in result.items():
            print(f"  Report {report_id}: {values}")
        return 0

    if sys.platform != "win32":
        print("WinUC runs on Windows only.", file=sys.stderr)
        return 1

    _set_firmware_dir()

    # --- GUI modes ---
    if args.tray or args.setup:
        from .gui.tray import main as tray_main

        return tray_main(first_run=args.setup)

    # --- Headless console mode (original behaviour) ---
    from .app import UniversalControlApp
    from .paths import keystore_path

    app = UniversalControlApp(config, keystore_file=str(keystore_path()))
    print()
    print("=" * 64)
    print(f"  On your iPad, open Settings > Bluetooth and connect to")
    print(f"  \"{config.device_name}\".")
    print(f"  Then push the mouse cursor into the {config.edge} screen edge")
    print(f"  to move over to the iPad.  Force-return: {config.release_hotkey}")
    print("=" * 64)
    print()

    async def _run() -> None:
        import signal

        loop = asyncio.get_running_loop()
        task = asyncio.ensure_future(app.run(enable_capture=not args.no_capture))
        try:
            loop.add_signal_handler(signal.SIGINT, app.request_stop)
        except (NotImplementedError, RuntimeError):
            pass
        await task

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        app.request_stop()
        print("\nStopping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
