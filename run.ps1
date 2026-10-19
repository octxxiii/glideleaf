# Glideleaf launcher (dev). Pass --tray for the GUI, or no args for console mode.
$env:BUMBLE_RTK_FIRMWARE_DIR = Join-Path $PSScriptRoot "firmware"
& (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") -m glideleaf @args


