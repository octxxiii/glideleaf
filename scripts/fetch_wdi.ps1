# Fetch a prebuilt wdi-simple.exe (the scriptable libwdi CLI behind Zadig).
#
# WinUC uses wdi-simple.exe to force-bind the Bluetooth dongle to WinUSB.
# libwdi ships no official prebuilt binary, so this pulls a community build.
# You are strongly encouraged to verify / re-sign it before redistributing.
#
# License: libwdi is LGPL-3.0. wdi-simple.exe is shipped as a separate invoked
# executable (not linked into WinUC), which keeps WinUC's own MIT license clean.
# Keep the LGPL notice in tools/ alongside the binary.

$ErrorActionPreference = "Stop"
$toolsDir = Join-Path (Split-Path $PSScriptRoot -Parent) "tools"
New-Item -ItemType Directory -Force $toolsDir | Out-Null

$dest = Join-Path $toolsDir "wdi-simple.exe"
if (Test-Path $dest) {
    Write-Host "wdi-simple.exe already present: $dest" -ForegroundColor Green
    return
}

# Unofficial prebuilt release (community). Pin to a known asset.
$url = "https://github.com/Timocop/libwdi-wdi-releases/releases/download/1.0/wdi-simple.exe"
Write-Host "Downloading wdi-simple.exe ..." -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $url -OutFile $dest
    Write-Host "Saved: $dest" -ForegroundColor Green
} catch {
    Write-Host "Automatic download failed: $_" -ForegroundColor Yellow
    Write-Host @"
Please obtain wdi-simple.exe manually and place it at:
    $dest
Options:
  - Build libwdi from source (Visual Studio / MSYS2): https://github.com/pbatard/libwdi
  - Community prebuilt: https://github.com/Timocop/libwdi-wdi-releases/releases
"@ -ForegroundColor Yellow
    exit 1
}

# LGPL notice next to the binary.
@"
wdi-simple.exe is built from libwdi (https://github.com/pbatard/libwdi),
licensed under the GNU LGPL v3.0. It is distributed here as a separate,
independently-invoked executable. Source and license:
  https://github.com/pbatard/libwdi
  https://www.gnu.org/licenses/lgpl-3.0.html
"@ | Set-Content -Path (Join-Path $toolsDir "wdi-simple.LICENSE.txt") -Encoding utf8

