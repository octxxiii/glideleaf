# WinUC: restore the dongle to the standard Windows Bluetooth driver.
#
# Removes the WinUSB driver package installed by Zadig, then re-scans so
# Windows reapplies its in-box Bluetooth driver (bthusb). Requires admin
# (it will self-elevate via a UAC prompt if needed).
#
# Usage:  .\scripts\restore_dongle.ps1
#         .\scripts\restore_dongle.ps1 -VidPid "VID_XXXX&PID_YYYY"  # other dongle

param(
    [string]$VidPid = "VID_0411&PID_0374",
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

# --- Admin check (self-elevate if needed) ---
$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Administrator rights required. Relaunching elevated..." -ForegroundColor Yellow
    Start-Process (Get-Process -Id $PID).Path -Verb RunAs -ArgumentList @(
        "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-VidPid", "`"$VidPid`""
    )
    exit
}

Write-Host "=== WinUC dongle restore (WinUSB -> Windows in-box driver) ===" -ForegroundColor Cyan

try {
    # --- 1. Find the device ---
    $device = Get-PnpDevice | Where-Object { $_.InstanceId -like "USB\$VidPid*" } | Select-Object -First 1
    if (-not $device) {
        throw "No device found for USB\$VidPid. Make sure the dongle is plugged in."
    }
    Write-Host ("`n[1/4] Target: {0} ({1})" -f $device.FriendlyName, $device.InstanceId)
    Write-Host ("      Current class: {0}" -f $device.Class)

    if ($device.Class -eq "Bluetooth") {
        Write-Host "`nAlready on the standard Windows Bluetooth driver. Nothing to do." -ForegroundColor Green
        if (-not $NoPause) { Read-Host "Press Enter to close" }
        exit 0
    }

    # --- 2. Identify and remove the Zadig (WinUSB) driver package ---
    $inf = (Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName DEVPKEY_Device_DriverInfPath).Data
    Write-Host "`n[2/4] Current driver INF: $inf"
    if ($inf -like "oem*.inf") {
        Write-Host "      Removing the third-party package..."
        pnputil /delete-driver $inf /uninstall /force | Out-Host
    } else {
        Write-Host "      In-box INF ($inf); skipping removal." -ForegroundColor Yellow
    }

    # --- 3. Re-enumerate so Windows reapplies the in-box driver ---
    Write-Host "`n[3/4] Re-enumerating devices..."
    pnputil /remove-device "$($device.InstanceId)" | Out-Host
    pnputil /scan-devices | Out-Host
    Start-Sleep -Seconds 5

    # --- 4. Verify ---
    $restored = Get-PnpDevice -Class Bluetooth -Status OK -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -like "USB\$VidPid*" }
    if ($restored) {
        Write-Host "`n[4/4] Restored: $($restored.FriendlyName) is back in the Bluetooth class." -ForegroundColor Green
        Write-Host "      Your Bluetooth devices (earbuds, etc.) can be used again."
    } else {
        Write-Host "`n[4/4] Not back in the Bluetooth class yet." -ForegroundColor Yellow
        Write-Host "      Physically unplugging and replugging the dongle will force reinstallation."
    }
} catch {
    Write-Host "`nError: $_" -ForegroundColor Red
}

if (-not $NoPause) { Read-Host "Press Enter to close" }

