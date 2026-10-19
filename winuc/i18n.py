"""UI translations, OS locale detection, and a predictable English fallback.

Catalogs are Python data so frozen builds need no external resource paths.
Korean source messages are stable translation IDs; placeholders are named.
"""
from __future__ import annotations

import ctypes
import locale
import sys

LANGUAGES = {
    "auto": "System default / 자동",
    "en": "English", "ko": "한국어", "ja": "日本語",
    "zh-Hans": "简体中文", "zh-Hant": "繁體中文",
    "es": "Español", "fr": "Français", "de": "Deutsch",
    "pt-BR": "Português (Brasil)",
}


def resolve_language(code: str | None) -> str:
    code = (code or "").replace("_", "-").lower()
    if code.startswith("zh"):
        return "zh-Hant" if any(part in code.split("-") for part in ("hant", "tw", "hk", "mo")) else "zh-Hans"
    if code.startswith("pt"):
        return "pt-BR"
    return next((key for key in LANGUAGES if key.lower() == code.split("-")[0] and key != "auto"), "en")


def system_language() -> str:
    if sys.platform == "win32":
        try:
            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                return resolve_language(buffer.value)
        except (AttributeError, OSError):
            pass
    try:
        return resolve_language(locale.getlocale()[0])
    except (ValueError, TypeError):
        return "en"


_language = system_language()


def set_language(code: str) -> str:
    global _language
    _language = system_language() if code == "auto" else resolve_language(code)
    return _language


def get_language() -> str:
    return _language


def t(message: str, **values) -> str:
    from .translations import CATALOGS
    translated = CATALOGS.get(_language, {}).get(message, CATALOGS["en"].get(message, message))
    return translated.format(**values) if values else translated
