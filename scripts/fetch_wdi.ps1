# Optional verified prefetch; no driver is installed by this script.
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }
Push-Location $repo
try {
    & $python -m winuc.driver_tool
    if ($LASTEXITCODE -ne 0) { throw "Verified driver-tool download failed." }
} finally {
    Pop-Location
}
