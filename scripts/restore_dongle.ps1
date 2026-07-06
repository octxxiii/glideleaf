# WinUC 用: ドングルを Windows 標準の Bluetooth ドライバに戻すスクリプト
#
# Zadig でインストールした WinUSB ドライバパッケージを削除し、
# デバイスを再スキャンして Windows 標準ドライバ (bthusb) を再適用させる。
# 管理者権限が必要 (権限がなければ自動で昇格ダイアログを出す)。
#
# 使い方:  .\scripts\restore_dongle.ps1
#          .\scripts\restore_dongle.ps1 -VidPid "VID_XXXX&PID_YYYY"  # 別のドングル

param(
    [string]$VidPid = "VID_0411&PID_0374",
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

# --- 管理者チェック (必要なら自己昇格) ---
$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "管理者権限が必要です。昇格して再実行します..." -ForegroundColor Yellow
    Start-Process (Get-Process -Id $PID).Path -Verb RunAs -ArgumentList @(
        "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-VidPid", "`"$VidPid`""
    )
    exit
}

Write-Host "=== WinUC ドングル復元 (WinUSB → Windows 標準ドライバ) ===" -ForegroundColor Cyan

try {
    # --- 1. デバイスを探す ---
    $device = Get-PnpDevice | Where-Object { $_.InstanceId -like "USB\$VidPid*" } | Select-Object -First 1
    if (-not $device) {
        throw "USB\$VidPid のデバイスが見つかりません。ドングルが挿さっているか確認してください。"
    }
    Write-Host ("`n[1/4] 対象: {0} ({1})" -f $device.FriendlyName, $device.InstanceId)
    Write-Host ("      現在のクラス: {0}" -f $device.Class)

    if ($device.Class -eq "Bluetooth") {
        Write-Host "`nすでに Windows 標準の Bluetooth ドライバで動作しています。何もしません。" -ForegroundColor Green
        if (-not $NoPause) { Read-Host "Enter で閉じる" }
        exit 0
    }

    # --- 2. 現在の (Zadig 製) ドライバパッケージを特定して削除 ---
    $inf = (Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName DEVPKEY_Device_DriverInfPath).Data
    Write-Host "`n[2/4] 現在のドライバ INF: $inf"
    if ($inf -like "oem*.inf") {
        Write-Host "      サードパーティ製パッケージを削除します..."
        pnputil /delete-driver $inf /uninstall /force | Out-Host
    } else {
        Write-Host "      標準 INF ($inf) のため削除はスキップ" -ForegroundColor Yellow
    }

    # --- 3. デバイスを削除して再スキャン → Windows が標準ドライバを再適用 ---
    Write-Host "`n[3/4] デバイスを再列挙..."
    pnputil /remove-device "$($device.InstanceId)" | Out-Host
    pnputil /scan-devices | Out-Host
    Start-Sleep -Seconds 5

    # --- 4. 結果確認 ---
    $restored = Get-PnpDevice -Class Bluetooth -Status OK -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -like "USB\$VidPid*" }
    if ($restored) {
        Write-Host "`n[4/4] 復元成功: $($restored.FriendlyName) が Bluetooth クラスに戻りました ✓" -ForegroundColor Green
        Write-Host "      イヤホン等の Bluetooth 機器が再び使えます。"
    } else {
        Write-Host "`n[4/4] まだ Bluetooth クラスに現れていません。" -ForegroundColor Yellow
        Write-Host "      USB を物理的に抜き差しすると確実に再適用されます。"
    }
} catch {
    Write-Host "`nエラー: $_" -ForegroundColor Red
}

if (-not $NoPause) { Read-Host "Enter で閉じる" }

