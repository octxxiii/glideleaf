# WinUC 用: Bluetooth ドングルを WinUSB ドライバに切り替える準備スクリプト
#
# WinUC は Windows 標準の Bluetooth スタックを迂回して USB ドングルを直接制御する。
# そのためドングルのドライバを Zadig で WinUSB に切り替える必要がある。
#
# ⚠ 注意: WinUSB に切り替えている間、そのドングルは Windows の通常の
#   Bluetooth (イヤホン・コントローラ等) には使えなくなる。
#   普段使いの Bluetooth と併用したい場合は WinUC 専用のドングルを
#   もう 1 本用意することを強く推奨 (RTL8761B 系、1000〜1500 円程度)。

$ErrorActionPreference = "Stop"

Write-Host "=== WinUC ドングルセットアップ ===" -ForegroundColor Cyan

# 1. Bluetooth USB ドングルの検出
Write-Host "`n[1/3] Bluetooth アダプタを検索..."
$adapters = Get-PnpDevice -Class Bluetooth -Status OK |
    Where-Object { $_.InstanceId -like "USB\*" }
if ($adapters) {
    foreach ($a in $adapters) {
        Write-Host ("  検出: {0}  ({1})" -f $a.FriendlyName, $a.InstanceId) -ForegroundColor Green
    }
} else {
    Write-Host "  USB Bluetooth アダプタが見つかりません (既に WinUSB 化済みかも)" -ForegroundColor Yellow
}

# 2. Zadig のダウンロード
Write-Host "`n[2/3] Zadig をダウンロード..."
$zadig = Join-Path $PSScriptRoot "zadig.exe"
if (-not (Test-Path $zadig)) {
    $url = "https://github.com/pbatard/libwdi/releases/download/v1.5.1/zadig-2.9.exe"
    Invoke-WebRequest -Uri $url -OutFile $zadig
    Write-Host "  保存先: $zadig" -ForegroundColor Green
} else {
    Write-Host "  既にダウンロード済み: $zadig" -ForegroundColor Green
}

# 3. 手順の案内
Write-Host @"

[3/3] 次の手順を手動で実行してください:

  1. $zadig を管理者として実行
  2. メニュー Options > List All Devices にチェック
  3. ドロップダウンから Bluetooth ドングル
     (例: "Realtek Bluetooth 5.0 Adapter" / USB\VID_0411&PID_0374) を選択
  4. ドライバ欄の右側が「WinUSB」になっていることを確認して
     「Replace Driver」をクリック
  5. 完了後、デバイスマネージャーで「ユニバーサル シリアル バス デバイス」
     配下に移動していれば成功

  ▶ 元に戻すには:  .\scripts\restore_dongle.ps1  を実行するだけ
    (WinUSB パッケージを削除して Windows 標準ドライバを再適用します)

"@ -ForegroundColor Yellow

