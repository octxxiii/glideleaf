"""Read-only release gate: exact INF content and Windows catalog trust."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from winuc.native_driver import readiness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = readiness(root=args.root.resolve())
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
