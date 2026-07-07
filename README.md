# WinUC — Universal Control for Windows

Control your **iPad with the mouse and keyboard of your Windows PC**, the way
macOS Universal Control lets a Mac drive an iPad. Push the pointer past a screen
edge and it crosses onto the iPad; the keyboard follows. Push back through the
shared edge to return. **Nothing is installed on the iPad** — to iPadOS this is
just an ordinary Bluetooth mouse and keyboard.

> **v2** adds a system-tray app with a GUI: setup wizard, one-click WinUSB
> driver switching, settings, autostart, and an installer. The original
> command-line mode still works (`python -m winuc`).

## How it works

iPadOS does not allow injecting input over the network, so the only practical
path is to make **Windows itself act as a Bluetooth LE mouse + keyboard**
(HID over GATT, "HOGP"). Since iPadOS 13.4 a BLE mouse is a first-class pointer,
so the iPad sees a normal Bluetooth peripheral.

The in-box Windows Bluetooth stack cannot be a HOGP peripheral (it blocks
publishing the Device Information Service). WinUC therefore drives a USB
Bluetooth dongle directly in user space via [Google bumble](https://github.com/google/bumble),
with the dongle bound to the WinUSB driver.

```
┌─ Windows ────────────────────────────────┐      ┌─ iPad ─────────┐
│ WH_MOUSE_LL / WH_KEYBOARD_LL  (swallow)   │      │                │
│ Raw Input WM_INPUT            (raw delta) │ BLE  │  seen as a      │
│        │                                  ├──────▶  standard mouse │
│  edge state machine → HID reports → bumble│ HOGP │  + keyboard     │
│              (HOGP peripheral)            │      │                │
└──────────────────────────────────────────┘      └────────────────┘
```

## Requirements

- Windows 10/11, and (for running from source) Python 3.10+
- **One USB Bluetooth dongle** that WinUC takes over
  - Realtek RTL8761B-family dongles are the tested reference
  - ⚠ While bound to WinUSB, that dongle can't be used for normal Bluetooth
    (earbuds, controllers). Use a **dedicated dongle** if you want both.
- An iPad on iPadOS 13.4+ (15+ recommended for keyboard shortcuts)

## Install (end users)

Download and run **WinUC-Setup.exe** from the
[Releases](https://github.com/fuba/winuc/releases) page. It installs the app,
optionally starts it at sign-in, and launches the **setup wizard**:

1. The wizard detects your Bluetooth dongle.
2. Click **Switch to WinUSB** (one UAC prompt) to hand the dongle to WinUC.
3. On your iPad, open **Settings › Bluetooth** and connect to
   "Windows Pointer & Keyboard".
4. Push the mouse into your chosen screen edge to cross over.

WinUC then lives in the system tray. Right-click the tray icon for
**Enabled**, **Settings…**, **Setup / Dongle…**, **Start at sign-in**, and
**Quit**. The tray icon color shows status (grey = stopped, blue = waiting,
green = actively controlling the iPad, red = error).

To go back to normal Bluetooth on the dongle, open **Setup / Dongle…** and click
**Restore normal Bluetooth** (the uninstaller does this automatically too).

## Run from source (developers)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Realtek firmware (from the Linux kernel firmware repo)
.venv\Scripts\bumble-rtk-fw-download.exe --output-dir firmware

# Optional: fetch wdi-simple.exe for automatic WinUSB switching
powershell -ExecutionPolicy Bypass -File scripts\fetch_wdi.ps1

python -m winuc --tray        # GUI tray app
python -m winuc --setup       # just the setup wizard
python -m winuc               # headless console mode (v1 behaviour)
python -m winuc --selftest    # validate the BLE layer with no dongle
```

If you prefer not to automate the driver switch, `scripts\setup_dongle.ps1`
launches Zadig, and `scripts\restore_dongle.ps1` restores the in-box driver.

## Building the installer

```powershell
packaging\build.ps1
```

This downloads the Realtek firmware, runs PyInstaller (`dist\WinUC\`), and — if
[Inno Setup 6](https://jrsoftware.org/isdl.php) is installed — compiles
`dist\installer\WinUC-Setup-*.exe`.

`wdi-simple.exe` (for automatic WinUSB switching) is **not** bundled by default,
because redistributing it (libwdi, LGPL-3.0) requires shipping the LGPL license
text and a source link. To include it deliberately, place a `wdi-simple.exe`
under `tools\` (via `scripts\fetch_wdi.ps1` or your own libwdi build) before
running the build. Without it, the setup wizard falls back to manual Zadig
(`scripts\setup_dongle.ps1`).

## Settings

Settings live in the tray **Settings…** dialog (stored at
`%LOCALAPPDATA%\WinUC\config.json`).

| Setting | Default | Meaning |
|---|---|---|
| iPad edge | `right` | Which screen edge crosses to the iPad (`right`/`left`/`top`/`bottom`) |
| Pointer speed | `1.0` | Multiplier for motion sent to the iPad |
| Push-through / push-back distance | `80` px | Resistance before crossing / returning (the macOS "push through the edge" feel) |
| Natural scrolling | off | Invert scroll direction |
| iPad screen (pt) | `1194 × 834` | Used to estimate the return position |
| Swap Alt / Win | off | Use Alt as ⌘ instead of the Win key |
| JIS 変換/無変換 → かな/英数 | on | Map JIS conversion keys to Kana/Eisū |
| Force-return hotkey | `ctrl+alt+q` | Immediately return control to Windows |
| Mouse button actions | — | Assign `drag_scroll` / `wheel_up` / `wheel_down` to buttons `x1`/`x2`/`middle` |

**Key mapping:** Win → ⌘ Command, Alt → ⌥ Option, Ctrl → Control (remappable in
iPadOS Settings › Hardware Keyboard › Modifier Keys). Media keys work. On the
iPad, set Settings › General › Keyboard › Hardware Keyboard › **Keyboard Type =
JIS** for a JIS keyboard.

**Mouse buttons → scroll:** X-Mouse Button Control's scroll conversion sends
window messages that can't be captured, so assign scroll actions here instead —
WinUC does the conversion natively while you're controlling the iPad.

## Differences from macOS Universal Control

| Feature | macOS | WinUC |
|---|---|---|
| Cursor / keyboard edge crossing | ✅ | ✅ |
| Push-through resistance & push-back return | ✅ | ✅ |
| Scrolling & media keys | ✅ | ✅ |
| Automatic reconnect | ✅ | ✅ (persisted bonding) |
| File drag & drop | ✅ | ❌ not possible |
| Universal Clipboard | ✅ | ❌ not possible |

Drag-and-drop and clipboard sharing use Apple's Continuity over Wi-Fi (AWDL),
which cannot be reproduced over a Bluetooth HID link without an app on the iPad.

Other limits: capture pauses during UAC / secure-desktop prompts; `Ctrl+Alt+Del`
is reserved by Windows; iPadOS applies its own pointer acceleration (tune speed
on the iPad).

## Project layout

| Module | Role |
|---|---|
| `winuc/hid_reports.py` | HID report descriptor & report packing |
| `winuc/keymap.py` | Set-1 scancode → HID usage (incl. JIS) |
| `winuc/ble_peripheral.py` | bumble HOGP peripheral (HID/Battery/DIS, Just-Works bonding) |
| `winuc/capture.py` | LL hooks + Raw Input + ClipCursor input capture |
| `winuc/edge.py` | LOCAL→PUSHING→REMOTE state machine (pure logic) |
| `winuc/app.py` | Hook-thread ↔ asyncio bridge, coalesced sends |
| `winuc/service.py` | Background service supervisor (start/stop, status) |
| `winuc/driver.py` | Automatic WinUSB switch/restore (libwdi + pnputil) |
| `winuc/gui/` | Tray icon, settings dialog, setup wizard |
| `winuc/selftest.py` | Virtual two-controller integration check |

## License

[MIT](LICENSE). Dependency [bumble](https://github.com/google/bumble) is
Apache-2.0. `wdi-simple.exe` (bundled at build time) comes from
[libwdi](https://github.com/pbatard/libwdi) and is LGPL-3.0, shipped as a
separate invoked executable. Realtek firmware is not included in the repository;
it is downloaded from the Linux kernel firmware repo during setup.
