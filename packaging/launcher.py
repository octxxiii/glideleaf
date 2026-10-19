"""Frozen entry point: retain package-relative imports and default to the GUI."""
import sys

from winuc.__main__ import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("--tray")
    raise SystemExit(main())
