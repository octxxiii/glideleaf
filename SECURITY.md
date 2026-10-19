# Security reporting

Glideleaf captures keyboard/mouse events and manages an explicitly selected
USB Bluetooth adapter. Pairing keys are sensitive local data.

Please use [GitHub private vulnerability reporting](https://github.com/octxxiii/glideleaf/security/advisories/new)
for vulnerabilities rather than posting reproduction details or secrets in a
public issue. No response time or support guarantee is currently offered.

Do not submit pairing-key files, passwords or unredacted personal logs. Include
the affected commit, Windows/iPadOS versions, adapter VID/PID and minimal steps.

This is an alpha project. Secure desktop/UAC can interrupt capture, and
Ctrl+Alt+Del belongs to Windows. Keep the emergency return shortcut available.
Driver restoration must target the selected device's hardware ID. Do not
bundle unverified driver tools or firmware without reviewing provenance and
redistribution terms.
