# Contributing to Glideleaf

Glideleaf shares Windows mouse and keyboard input with iPad over BLE HID.
Small, reproducible improvements and native-speaker translation reviews are welcome.

1. Create a branch from `main` and install `requirements-dev.txt` in a virtual environment.
2. Describe the user-visible problem and make the smallest useful change.
3. Run `python -m pytest -q` and `python -m glideleaf --selftest` on Windows.
4. For UI changes, run `python scripts/verify_gui.py --language en` and the affected language.
5. Report what you actually tested. Separate simulated BLE, UI rendering and physical-device results.

For translations, preserve the named placeholders in `winuc/translations.py`.
See [LANGUAGES.md](LANGUAGES.md). Do not change HID mappings to change UI language.

Hardware reports should include Windows/iPadOS versions, adapter chipset and
VID/PID, driver state, steps and redacted logs. Never post pairing keys.
Read [hardware validation](docs/HARDWARE_VALIDATION.md) before claiming compatibility.

Preserve fuba's original copyright and MIT license. Contributions to project
code are provided under MIT unless separately identified; dependencies keep
their existing licenses. See [third-party notices](THIRD_PARTY_NOTICES.md).
