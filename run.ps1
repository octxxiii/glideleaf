# WinUC 起動スクリプト
$env:BUMBLE_RTK_FIRMWARE_DIR = Join-Path $PSScriptRoot "firmware"
& (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") -m winuc @args

