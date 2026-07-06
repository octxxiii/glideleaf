# WinUC: prepare a Bluetooth dongle by switching it to the WinUSB driver.
#
# WinUC bypasses the Windows Bluetooth stack and drives the USB dongle directly,
# so the dongle's driver must be switched to WinUSB with Zadig.
#
# NOTE: The GUI build does this automatically (Setup / Dongle... wizard). This
# script is the manual fallback for running from source.
#
# WARNING: While bound to WinUSB, the dongle can no longer be used for normal
#   Windows Bluetooth (earbuds, controllers, etc.). If you want to keep using
#   Bluetooth normally, use a dedicated dongle for WinUC (RTL8761B family,
#   roughly $10-15).

$ErrorActionPreference = "Stop"

Write-Host "=== WinUC dongle setup ===" -ForegroundColor Cyan

# 1. Detect the Bluetooth USB dongle
Write-Host "`n[1/3] Searching for Bluetooth adapters..."
$adapters = Get-PnpDevice -Class Bluetooth -Status OK |
    Where-Object { $_.InstanceId -like "USB\*" }
if ($adapters) {
    foreach ($a in $adapters) {
        Write-Host ("  Found: {0}  ({1})" -f $a.FriendlyName, $a.InstanceId) -ForegroundColor Green
    }
} else {
    Write-Host "  No USB Bluetooth adapter found (it may already be on WinUSB)." -ForegroundColor Yellow
}

# 2. Download Zadig
Write-Host "`n[2/3] Downloading Zadig..."
$zadig = Join-Path $PSScriptRoot "zadig.exe"
if (-not (Test-Path $zadig)) {
    $url = "https://github.com/pbatard/libwdi/releases/download/v1.5.1/zadig-2.9.exe"
    Invoke-WebRequest -Uri $url -OutFile $zadig
    Write-Host "  Saved to: $zadig" -ForegroundColor Green
} else {
    Write-Host "  Already downloaded: $zadig" -ForegroundColor Green
}

# 3. Manual steps
Write-Host @"

[3/3] Do the following manually:

  1. Run $zadig as administrator
  2. Menu: Options > List All Devices (checked)
  3. In the dropdown, select the Bluetooth dongle
     (e.g. "Realtek Bluetooth 5.0 Adapter" / USB\VID_0411&PID_0374)
  4. Make sure the target driver on the right is "WinUSB", then click
     "Replace Driver"
  5. When done, it should appear under "Universal Serial Bus devices"
     in Device Manager

  To restore: run  .\scripts\restore_dongle.ps1
    (removes the WinUSB package and reapplies the in-box driver)

"@ -ForegroundColor Yellow

