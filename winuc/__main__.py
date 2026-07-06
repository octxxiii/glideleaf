"""CLI エントリポイント: python -m winuc"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from .config import Config


def _set_firmware_dir() -> None:
    """同梱の firmware/ ディレクトリを bumble の Realtek FW 検索パスに登録。"""
    firmware_dir = Path(__file__).resolve().parent.parent / "firmware"
    if firmware_dir.is_dir():
        os.environ.setdefault("BUMBLE_RTK_FIRMWARE_DIR", str(firmware_dir))


def main() -> int:
    # cp932 コンソールでも Unicode 文字で落ちないように
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        prog="winuc",
        description="WinUC - Windows 版 Universal Control (iPad を画面端から操作)",
    )
    parser.add_argument(
        "--config", default="config.json", help="設定ファイル (無ければ既定値で作成)"
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="実機ドングルなしで BLE 層を仮想コントローラ上で検証",
    )
    parser.add_argument(
        "--no-capture",
        action="store_true",
        help="入力フックを張らずに BLE のみ起動 (ペアリング確認用)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # bumble のログは冗長なので抑制
    if not args.verbose:
        logging.getLogger("bumble").setLevel(logging.WARNING)

    config_path = Path(args.config)
    config = Config.load(config_path)
    if not config_path.exists():
        config.save(config_path)
        print(f"既定の設定を {config_path} に作成しました。")

    if args.selftest:
        from .selftest import run_selftest

        result = asyncio.run(run_selftest(config, keystore_file="selftest_keys.json"))
        Path("selftest_keys.json").unlink(missing_ok=True)
        print("セルフテスト成功。受信レポート:")
        for report_id, values in result.items():
            print(f"  Report {report_id}: {values}")
        return 0

    if sys.platform != "win32":
        print("このアプリは Windows 専用です。", file=sys.stderr)
        return 1

    from .app import UniversalControlApp

    _set_firmware_dir()
    app = UniversalControlApp(config)
    try:
        asyncio.run(app.run(enable_capture=not args.no_capture))
    except KeyboardInterrupt:
        print("\n終了します。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
