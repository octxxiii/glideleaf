# Build the WinUC installer end to end.
#
#   packaging\build.ps1
#
# Steps: ensure venv deps + PyInstaller, fetch firmware + wdi-simple, run
# PyInstaller (dist\WinUC), then compile the Inno Setup installer if ISCC is
# available (dist\installer\WinUC-Setup-*.exe).

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "venv not found; run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt" }

Write-Host "[1/5] Installing build dependencies..." -ForegroundColor Cyan
& $py -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller

Write-Host "[2/5] Fetching Realtek firmware..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force (Join-Path $root "firmware") | Out-Null
& (Join-Path $root ".venv\Scripts\bumble-rtk-fw-download.exe") --output-dir (Join-Path $root "firmware")

Write-Host "[3/5] Checking for wdi-simple.exe (WinUSB installer)..." -ForegroundColor Cyan
# Not auto-downloaded: bundling wdi-simple.exe (libwdi, LGPL-3.0) in a
# redistributable build requires LGPL compliance (license text + source link).
# To include it deliberately, run scripts\fetch_wdi.ps1 (or drop a self-built
# wdi-simple.exe into tools\) BEFORE building. Absent => automatic driver
# switching is disabled; the setup wizard falls back to manual Zadig.
if (Test-Path (Join-Path $root "tools\wdi-simple.exe")) {
    Write-Host "  Found tools\wdi-simple.exe -> automatic WinUSB switching enabled." -ForegroundColor Green
} else {
    Write-Host "  tools\wdi-simple.exe not present -> shipping without auto driver switch." -ForegroundColor Yellow
}

Write-Host "[4/5] Running PyInstaller..." -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "winuc.spec")

Write-Host "[5/5] Compiling the installer (Inno Setup)..." -ForegroundColor Cyan
$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $guess = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $guess) { $iscc = $guess } else { $iscc = $null }
}
if ($iscc) {
    & $iscc (Join-Path $PSScriptRoot "winuc.iss")
    Write-Host "Installer written to dist\installer\" -ForegroundColor Green
} else {
    Write-Host "ISCC.exe (Inno Setup) not found. Portable build is in dist\WinUC\." -ForegroundColor Yellow
    Write-Host "Install Inno Setup 6 to produce the .exe installer: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
}

