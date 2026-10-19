# Hardware validation status

Glideleaf has not yet qualified a physical iPad/USB-adapter combination in this
fork. The Realtek RTL8761B family is an **upstream reference**, not a new
compatibility certification by Glideleaf.

The automated virtual-controller integration test covers pairing, service
discovery, notification subscription and expected HID report contents. Desktop
screenshots use simulated state. Neither establishes hardware compatibility.

Before recommending a device combination, record the exact commit, Windows
version, iPad model/iPadOS, chipset, VID/PID and firmware source, then verify:

- WinUSB switch and restoration on the intended adapter; unrelated adapters remain intact.
- Pick a non-first adapter, apply it, restart the app, and verify the same physical
  device remains selected even if enumeration order changes. Unplug it and verify
  the app refuses to open another radio. Same-VID/PID selections are currently
  blocked until only one remains connected.
- Initial pairing and reconnection after app restart.
- Continuous mouse movement, clicks, scrolling and keyboard/media input.
- Entry at each configured edge, push-back return, and Ctrl+Alt+Q recovery.
- Release of held keys/buttons on disconnect, service stop and input errors.
- Sleep/resume on Windows and iPad, USB unplug/replug and iPad rotation.
- JIS and other keyboard layouts only for the hardware actually used.
- Installation, launch and removal on a Windows machine without Python.

Attach redacted logs and actual interaction observations. Keep unknown or
failed cases visible. Do not turn a virtual-test PASS into a device PASS.
