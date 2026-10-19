import ast
from dataclasses import replace
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from winuc.config import Config
from winuc import i18n
from winuc.translations import CATALOGS


@pytest.fixture(autouse=True)
def restore_language():
    previous = i18n.get_language()
    yield
    i18n.set_language(previous)


@pytest.mark.parametrize("locale, expected", [
    ("en_US", "en"), ("ko-KR", "ko"), ("ja_JP", "ja"),
    ("zh_CN", "zh-Hans"), ("zh-SG", "zh-Hans"), ("zh_TW", "zh-Hant"),
    ("zh-HK", "zh-Hant"), ("zh-Hant-MO", "zh-Hant"),
    ("pt_PT", "pt-BR"), ("es-MX", "es"), ("fr-CA", "fr"),
    ("de_DE", "de"), ("unknown", "en"), (None, "en"),
])
def test_regional_locale_resolution(locale, expected):
    assert i18n.resolve_language(locale) == expected


def test_automatic_selection_and_english_fallback(monkeypatch):
    monkeypatch.setattr(i18n, "system_language", lambda: "ja")
    assert i18n.set_language("auto") == "ja"
    assert i18n.t("연결 시작") == "接続開始"
    monkeypatch.delitem(CATALOGS["ja"], "연결 시작")
    assert i18n.t("연결 시작") == "Start connection"
    assert i18n.set_language("unsupported") == "en"


def test_catalogs_preserve_placeholders_and_cover_all_messages():
    base = CATALOGS["en"]
    formatter = Formatter()
    def fields(text):
        return {field for _, field, _, _ in formatter.parse(text) if field is not None}
    for code, catalog in CATALOGS.items():
        assert catalog.keys() == base.keys(), code
        for key, value in catalog.items():
            assert value.strip(), (code, key)
            assert fields(value) == fields(base[key]), (code, key)
            assert "fuba" in catalog["fuba 감사"]
    root = Path(__file__).resolve().parents[1] / "winuc"
    for path in root.rglob("*.py"):
        if path.name in ("translations.py", "i18n.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t" and node.args and isinstance(node.args[0], ast.Constant):
                assert node.args[0].value in base, (path, node.lineno)


@pytest.mark.parametrize("language", list(CATALOGS))
def test_language_preference_survives_save_and_load(tmp_path, language):
    path = tmp_path / "config.json"
    Config(language=language).save(path)
    assert Config.load(path).language == language


def test_old_config_defaults_to_system_language(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"speed": 1.2}', encoding="utf-8")
    assert Config.load(path).language == "auto"
    with pytest.raises(ValueError):
        Config(language="invalid").validate()


def test_language_change_keeps_ble_connected(tmp_path):
    from winuc.gui.tray import TrayApp
    app = TrayApp.__new__(TrayApp)
    app.config_file = tmp_path / "config.json"
    app.config = Config(language="ko")
    app.root = SimpleNamespace(after_idle=Mock())
    app.service = SimpleNamespace(running=True, restart=Mock())
    app._refresh_icon = Mock()
    app._apply_config(replace(app.config, language="ja"))
    app.service.restart.assert_not_called()
    app.root.after_idle.assert_called_once_with(app._refresh_language)
    assert i18n.get_language() == "ja"
    assert Config.load(app.config_file).language == "ja"
    app._apply_config(replace(app.config, speed=1.5))
    app.service.restart.assert_called_once()


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows desktop UI")
def test_live_language_switch_rebuilds_dashboard_and_tray(tmp_path):
    import tkinter as tk
    from winuc.gui.dashboard import Dashboard
    from winuc.gui.tray import TrayApp
    root = tk.Tk()
    root.withdraw()
    app = TrayApp.__new__(TrayApp)
    app.root = root
    app.config = Config(language="ko")
    app.config_file = tmp_path / "config.json"
    app.service = SimpleNamespace(running=True, status="ready", last_error=None, restart=Mock())
    app.icon = SimpleNamespace(update_menu=Mock())
    app._wizard = None
    i18n.set_language("ko")
    app._dashboard = Dashboard(app)
    original = app._dashboard
    try:
        app._apply_config(replace(app.config, language="ja"))
        root.update()
        assert not original.win.winfo_exists()
        assert app._dashboard.title.get() == "入力共有の準備完了"
        assert "入力共有の準備完了" in app.icon.title
        assert "Glideleaf コントロールパネル" in [item.text for item in app.icon.menu]
        app.service.restart.assert_not_called()
    finally:
        app._dashboard.close()
        root.destroy()
