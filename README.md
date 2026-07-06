# WinUC — Windows 版 Universal Control

Mac の Universal Control のように、**Windows のマウスとキーボードで iPad を操作**する。
マウスカーソルを画面の端に押し込むと iPad 側にカーソルが現れ、キーボード入力も iPad に切り替わる。
戻るときは iPad 側の共有エッジへカーソルを押し戻すだけ。**iPad には何もインストールしない。**

## 仕組み

iPadOS はネットワーク経由の外部入力注入を許可していないため、唯一の現実的な経路は
**Windows 自身を Bluetooth LE のマウス+キーボード (HID over GATT / HOGP) として振る舞わせる**こと。
iPadOS 13.4 以降は BLE マウスを OS 標準のポインタとして扱うので、iPad から見れば
「普通の Bluetooth マウス&キーボード」がつながっているだけになる。

ただし Windows 標準の Bluetooth スタックは HOGP ペリフェラルになれない
(GATT サーバーで Device Information Service の公開がブロックされている)。
そこで [Google bumble](https://github.com/google/bumble)(ユーザー空間 Bluetooth スタック)で
USB ドングルを WinUSB 経由で直接制御する。

```
┌─ Windows ────────────────────────────────┐      ┌─ iPad ─────────┐
│ WH_MOUSE_LL / WH_KEYBOARD_LL  (飲み込み)  │      │                │
│ Raw Input WM_INPUT            (生デルタ)  │      │  標準の BLE     │
│        │                                 │ BLE  │  マウス/キーボード│
│  エッジ状態機械 → HID レポート → bumble ──┼──────▶  として認識     │
│              (HOGP ペリフェラル)          │      │                │
└──────────────────────────────────────────┘      └────────────────┘
```

## 必要なもの

- Windows 10/11 + Python 3.10 以上
- **USB Bluetooth ドングル 1 本**(WinUC が占有する)
  - この PC の Buffalo ドングル (Realtek RTL8761B 系, `VID_0411&PID_0374`) は対応確認済みのチップ
  - ⚠ WinUSB 化している間、そのドングルは通常の Bluetooth(イヤホン等)に使えない。
    普段使いと併用するなら **WinUC 専用ドングルの追加購入を推奨**(RTL8761B 系 ~¥1,500)
- iPad (iPadOS 13.4 以降。キーボードショートカット等をフル活用するなら 15 以降推奨)

## セットアップ

```powershell
# 1. 依存のインストール
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2. Realtek ファームウェア (Linux カーネルの firmware リポジトリから取得)
.venv\Scripts\bumble-rtk-fw-download.exe --output-dir firmware

# 3. ドングルのドライバを WinUSB に切り替え (Zadig の操作のみ手動)
powershell -ExecutionPolicy Bypass -File scripts\setup_dongle.ps1

#    元に戻すとき (通常の Bluetooth に復帰させる):
powershell -ExecutionPolicy Bypass -File scripts\restore_dongle.ps1

# 4. 動作確認 (ドングル不要の仮想 BLE セルフテスト)
.\run.ps1 --selftest
```

## 使い方

```powershell
Copy-Item config.example.json config.json   # 初回のみ (無ければ既定値で自動生成)
.\run.ps1                                   # 起動
```

1. 起動すると「Windows Pointer & Keyboard」としてアドバタイズが始まる
2. iPad の **設定 > Bluetooth** から接続(ペアリングは自動。確認コード入力は不要)
3. **マウスカーソルを画面右端(設定変更可)にグッと押し込む** → iPad 側にカーソル出現
4. そのままマウス・キーボード・ホイール・メディアキーが iPad に流れる
5. **iPad 側で共有エッジ(左端)へカーソルを押し戻す** → Windows に復帰
6. 緊急時は `Ctrl+Alt+Q`(設定変更可)で強制復帰。BLE が切断された場合も自動復帰

管理者権限で実行すると、昇格したウィンドウ(タスクマネージャ等)が前面でも
入力を確実に奪えるようになる(推奨)。

## 設定 (config.json)

| キー | 既定値 | 説明 |
|---|---|---|
| `edge` | `"right"` | iPad がいる方向 (`right`/`left`/`top`/`bottom`) |
| `push_threshold_px` | `80` | 突き抜けに必要な押し込み量(Mac の「抵抗感」) |
| `return_threshold_px` | `80` | 戻りに必要な押し戻し量 |
| `speed` | `1.0` | iPad へ送る移動量の倍率 |
| `natural_scroll` | `false` | スクロール方向の反転 |
| `ipad_screen` | `[1194, 834]` | iPad の画面サイズ(pt)。戻り位置の推定精度に影響 |
| `swap_alt_win` | `false` | Alt⇔Win 入れ替え(Alt キーを Cmd として使う) |
| `jis_kana_mapping` → `jis_mac_style` | `true` | 変換/無変換 → かな/英数 (Apple JIS 風) |
| `release_hotkey` | `"ctrl+alt+q"` | 強制復帰ホットキー |
| `forward_injected` | `true` | X-Mouse Button Control 等が注入した変換後イベントも iPad へ転送 |
| `passthrough_buttons` | `[]` | REMOTE 中も XMBC 等に処理させるボタン (`"left"/"right"/"middle"/"x1"/"x2"`) |
| `transport` | `"usb:[driver=rtk]0"` | bumble のトランスポート指定 |

**ボタン→スクロール変換 (XMBC の代替)**: XMBC のスクロール変換はウィンドウへ直接
メッセージを送る方式のため iPad へは転送できない。代わりに `button_actions` で
WinUC 側が iPad 操作中の変換を行う (XMBC の「Mouse Button 4/5」= `x1`/`x2`):

```json
"button_actions": { "x1": "drag_scroll", "x2": "drag_scroll" }
```

- `drag_scroll`: ボタンを押しながらマウス移動でスクロール (感度は `drag_scroll_px`、
  方向は `drag_scroll_invert` で調整)
- `wheel_up` / `wheel_down`: 押すと 1 ノッチ、押しっぱなしで連続スクロール

`passthrough_buttons` は「iPad 操作中もローカルの XMBC 等に処理させたいボタン」を
列挙する上級者向けオプション (SendInput 型のツール向け)。`button_actions` と併用不可。

iPad 側の推奨設定: 設定 > 一般 > キーボード > ハードウェアキーボード > **キーボードの種類 = JIS**
(JIS 配列キーボードの場合)。ポインタ速度は 設定 > 一般 > トラックパッドとマウス で調整。

## キーの対応

- **Win キー → Cmd ⌘ / Alt → Option ⌥ / Ctrl → Ctrl** (iPad の 設定 > ハードウェアキーボード > 修飾キー で入れ替え可)
- 変換 → かな、無変換 → 英数(`jis_mac_style: false` で International4/5 の生マッピング)
- 音量・再生/停止などのメディアキー対応
- `Cmd+Tab`(Win+Tab として打つ)、`Cmd+Space` など iPad のショートカットがそのまま使える

## Mac の Universal Control との違い(原理的な限界)

| 機能 | Mac | WinUC |
|---|---|---|
| カーソル/キーボードのエッジ移動 | ✅ | ✅ |
| 突き抜けの抵抗感・押し戻しで復帰 | ✅ | ✅ |
| スクロール・メディアキー | ✅ | ✅ |
| 自動再接続 | ✅ | ✅ (ボンディング永続化) |
| ファイルのドラッグ&ドロップ | ✅ | ❌ 不可能 |
| ユニバーサルクリップボード | ✅ | ❌ 不可能 |

ドラッグ&ドロップとクリップボード共有は、Apple が Wi-Fi (AWDL) 上の Continuity
プロトコルで実現しているもので、Bluetooth HID の経路では原理的に再現できない
(iPad 側にアプリをインストールしない前提では代替手段が存在しない)。

その他の制限:

- UAC の昇格プロンプト(セキュアデスクトップ)表示中はキャプチャが中断される
- `Ctrl+Alt+Del` は OS 予約のため転送できない
- iPad 側のポインタ加速は iPadOS が独自に適用する(速度は iPad 側設定で調整)

## 開発

```powershell
.venv\Scripts\python.exe -m pytest tests        # 28 tests
.\run.ps1 --selftest                            # 仮想コントローラで BLE 一気通貫検証
.\run.ps1 --no-capture                          # フックなしで BLE のみ (ペアリング確認用)
.\run.ps1 -v                                    # bumble の詳細ログ
```

| モジュール | 役割 |
|---|---|
| `winuc/hid_reports.py` | HID レポートディスクリプタ & レポート組み立て |
| `winuc/keymap.py` | Set-1 スキャンコード → HID usage (JIS 対応) |
| `winuc/ble_peripheral.py` | bumble HOGP ペリフェラル (HID/Battery/DIS, Just Works ボンディング) |
| `winuc/capture.py` | LL フック + Raw Input + ClipCursor による入力キャプチャ |
| `winuc/edge.py` | LOCAL→PUSHING→REMOTE 状態機械 (純ロジック) |
| `winuc/app.py` | フックスレッド⇔asyncio 橋渡し、移動の合成送信 |
| `winuc/selftest.py` | 仮想コントローラ 2 台での統合検証 |

## ライセンス

[MIT License](LICENSE)。依存の [bumble](https://github.com/google/bumble) は Apache-2.0。
Realtek ファームウェアはリポジトリに含めていません (Realtek のライセンス条件に従い、
セットアップ時に Linux カーネルの firmware リポジトリから各自ダウンロードします)。
