"""CLI / GUI entry point: python -m winuc"""

from __future__ import annotations

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
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
            handlers.append(RotatingFileHandler(log_path(), maxBytes=2_000_000, backupCount=3, encoding="utf-8"))
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
        prog="glideleaf",
        description="Glideleaf - share your Windows mouse and keyboard with iPad over Bluetooth LE",
    )
    parser.add_argument("--config", default=None, help="Path to a config file")
    parser.add_argument("--tray", action="store_true", help="Run as a system-tray app (GUI)")
    parser.add_argument("--setup", action="store_true", help="Open the setup wizard (GUI)")
    parser.add_argument("--selftest", action="store_true",
                        help="Validate the BLE layer on a virtual controller (no dongle)")
    parser.add_argument("--diagnose", nargs="?", const="-", metavar="FILE",
                        help="Read-only USB diagnostics as JSON (stdout, or the given file)")
    parser.add_argument("--no-capture", action="store_true",
                        help="Start BLE only, without input hooks (for pairing checks)")
    parser.add_argument("--driver-check", nargs="?", const="-", metavar="FILE",
                        help="Read-only native driver package signature/readiness check")
    parser.add_argument("--verbose", "-v", action="store_true")
    # Elevated driver verbs (invoked by the GUI via UAC; not for normal use).
    parser.add_argument("--driver-install", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--driver-restore", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--vid", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--pid", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--adapter-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--driver-result", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--driver-language", default="auto", help=argparse.SUPPRESS)
    args = parser.parse_args()

    _setup_logging(args.verbose, to_file=args.tray or args.driver_install or args.driver_restore)

    if args.driver_check is not None:
        import json
        from .inbox_driver import readiness
        report = readiness()
        output = json.dumps(report, ensure_ascii=False, indent=2)
        destination = args.driver_check
        if destination == "-" and getattr(sys, "frozen", False):
            from .paths import data_dir
            destination = str(data_dir() / "driver-readiness.json")
        if destination == "-":
            print(output)
        else:
            Path(destination).write_text(output, encoding="utf-8")
        return 0 if report["ready"] else 1

    if args.diagnose is not None:
        from .diagnostics import collect_report, report_text
        report = collect_report()
        text = report_text(report)
        destination = args.diagnose
        if destination == "-" and getattr(sys, "frozen", False):
            from .paths import data_dir
            destination = str(data_dir() / "usb-diagnostics.json")
        if destination == "-":
            print(text)
        else:
            Path(destination).write_text(text, encoding="utf-8")
        return 1 if report["enumeration_error"] else 0

    # --- Elevated driver operations (run in a short-lived elevated process) ---
    if args.driver_install or args.driver_restore:
        from . import driver
        from .native_driver import RebootRequired, REBOOT_EXIT_CODE
        from .i18n import set_language
        import json
        set_language(args.driver_language)
        operation = "install" if args.driver_install else "restore"
        code, error = 0, None
        result_file = None
        try:
            if args.driver_result:
                result_file = driver.driver_result_path(args.driver_result)
            vid, pid = int(args.vid, 0), int(args.pid, 0)
            if not driver.is_admin():
                raise PermissionError("Driver helper requires administrator approval")
            selected = driver._selected_target(vid, pid, args.adapter_id)
            if args.driver_install:
                driver.install_winusb(vid, pid, adapter_id=selected.identity)
            else:
                driver._check_native_target(selected)
                driver.restore_inbox(vid, pid, adapter_id=selected.identity)
        except RebootRequired as exc:
            code, error = REBOOT_EXIT_CODE, str(exc)
        except Exception as exc:  # A windowless UAC child has no usable stderr.
            logging.getLogger(__name__).exception("Driver operation failed")
            code, error = 1, str(exc)
        if result_file is not None:
            try:
                # Exclusive create: never overwrite a pre-existing/symlinked file
                # based on arguments received by the elevated process.
                with result_file.open("x", encoding="utf-8") as output:
                    output.write(json.dumps({
                        "operation": operation, "adapter_id": args.adapter_id,
                        "error": error, "reboot_required": code == REBOOT_EXIT_CODE,
                    }, ensure_ascii=False))
            except OSError:
                logging.getLogger(__name__).exception("Could not write driver result")
        return code

    config_file = Path(args.config) if args.config else config_path()
    config = Config.load(config_file)
    from .i18n import set_language
    set_language(config.language)
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
