# Languages / 언어 지원

Glideleaf's desktop interface supports:

| Code | Language |
| --- | --- |
| `en` | English |
| `ko` | 한국어 |
| `ja` | 日本語 |
| `zh-Hans` | 简体中文 |
| `zh-Hant` | 繁體中文 |
| `es` | Español |
| `fr` | Français |
| `de` | Deutsch |
| `pt-BR` | Português (Brasil) |

The default is **Use system language**. Unsupported system languages fall back
to English. Traditional Chinese is selected for Taiwan, Hong Kong, Macau or
an explicit Hant locale. Portuguese locales currently use Brazilian Portuguese.

Open **Pointer & keyboard → Language**, choose a language and save. The control
panel and tray update immediately; an open adapter setup window updates after
any active operation finishes. Changing only the language keeps BLE connected.
The choice is saved in the existing per-user configuration (`language` field).
UI language does not change keyboard mappings or the iPad's keyboard layout.

## Translation contributions

`winuc/translations.py` contains UTF-8 catalogs for the control panel, settings,
tray, adapter setup, validation messages and acknowledgements. Korean source
messages are stable IDs. Each row has nine pipe-separated language columns in
the order declared at the top of that file. Preserve `{named}` placeholders,
literal `\n` line breaks and legal identifiers. Do not translate device IDs,
Bluetooth names entered by the user, key codes, license names or file paths.

Translations have automated completeness, placeholder and UI layout checks.
Native-speaker review is welcome; automated checks do not certify linguistic
quality. External driver/BLE errors and technical logs retain their original
language. CLI help, upstream documentation and the installer are not localized
by this change.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\verify_gui.py --language ja
```

## fubaさんへ / Thanks to fuba

WinUCを作り、公開してくださったfubaさんに感謝します。
あなたの取り組みがGlideleafの出発点になりました。

Thank you, fuba, for creating and sharing WinUC. Your work made Glideleaf possible.

WinUC를 만들고 공개해 주신 fuba님께 감사드립니다.
그 작업 덕분에 Glideleaf를 시작할 수 있었습니다.

The acknowledgements in the app include this thanks in all nine languages,
alongside the original copyright and license information.
