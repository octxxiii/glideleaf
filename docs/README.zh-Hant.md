# Glideleaf — 用 Windows 滑鼠和鍵盤控制 iPad

Glideleaf 是一款開源 Windows 應用程式，透過低功耗藍牙將電腦的滑鼠和鍵盤輸入轉送到 iPad。
將游標推過所選螢幕邊緣即可切換到 iPad；反向推回或按 **Ctrl+Alt+Q** 可返回 Windows。
iPad 將其辨識為一般藍牙滑鼠和鍵盤，無需安裝 iPad 應用程式。

**需要相容的專用 USB 藍牙配接器。** 切換至 WinUSB 後，該配接器無法同時連接耳機、
遊戲控制器等一般藍牙裝置。不提供螢幕鏡像、共享剪貼簿或檔案拖放功能。

**目前為 Alpha 原始碼預覽。** 虛擬 BLE 和 Windows UI 已有測試；此分支的實體配接器與
iPad 配對、睡眠恢復及安裝程式驗證尚未完成。

[英文安裝指南](../README.md#run-from-source-on-windows) · [語言支援](../LANGUAGES.md) · [硬體驗證](HARDWARE_VALIDATION.md)

## 執行

準備 Windows 10/11 和 Python 3.10 或更新版本，依照英文指南安裝相依套件、所需韌體與配接器驅動程式。

```powershell
.\.venv\Scripts\pythonw.exe -m glideleaf --setup
.\.venv\Scripts\pythonw.exe -m glideleaf --tray
```

在 iPad 的 **設定 → 藍牙** 中選擇 **Windows Pointer & Keyboard** 進行配對。
在應用程式的 **游標與鍵盤 → 語言** 中可選擇介面語言，預設跟隨系統。介面語言與鍵盤配置分開設定。
在 **游標與鍵盤 → 螢幕配置** 中可拖曳 iPad 調整其相對於電腦的位置，並設定綠色跨越區域的中心與長度。

## 致謝

感謝 fuba 建立並開源 [WinUC](https://github.com/fuba/winuc)。您的付出讓 Glideleaf 成為可能。
本專案保留原始 Git 歷史、MIT 授權條款及 Copyright (c) 2026 fuba。
這是獨立衍生專案，並非 Apple 或 fuba 的官方產品。[授權條款](../LICENSE)
