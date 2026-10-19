import sys
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from winuc.config import Config
from winuc import i18n


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Tk desktop")
@pytest.mark.parametrize("language", ["ko", "ja", "en"])
def test_dashboard_fits_1366_by_768_with_logs_open(desktop_root, monkeypatch, language):
    from winuc.gui.dashboard import Dashboard

    previous = i18n.get_language()
    i18n.set_language(language)
    monkeypatch.setattr(tk.Toplevel, "winfo_screenwidth", lambda _self: 1366)
    monkeypatch.setattr(tk.Toplevel, "winfo_screenheight", lambda _self: 768)
    app = SimpleNamespace(
        root=desktop_root,
        config=Config(language=language),
        service=SimpleNamespace(status="stopped", running=False, last_error=None),
        _open_settings=Mock(),
        _open_wizard=Mock(),
    )
    dashboard = Dashboard(app)
    try:
        desktop_root.update()
        assert dashboard.win.winfo_width() <= 1366
        assert dashboard.win.winfo_height() <= 688
        assert dashboard.win.winfo_children()[0].winfo_reqheight() <= dashboard.win.winfo_height()

        dashboard.toggle_logs()
        desktop_root.update()
        assert dashboard.win.winfo_height() <= 688
        assert dashboard.win.winfo_children()[0].winfo_reqheight() <= dashboard.win.winfo_height()
    finally:
        dashboard.close()
        i18n.set_language(previous)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Tk desktop")
@pytest.mark.parametrize("language", ["ko", "ja", "en"])
def test_settings_fits_1366_by_768(desktop_root, monkeypatch, language):
    from winuc.gui.settings import SettingsWindow

    previous = i18n.get_language()
    i18n.set_language(language)
    monkeypatch.setattr(tk.Toplevel, "winfo_screenwidth", lambda _self: 1366)
    monkeypatch.setattr(tk.Toplevel, "winfo_screenheight", lambda _self: 768)
    window = SettingsWindow(desktop_root, Config(language=language), Mock())
    try:
        desktop_root.update()
        assert window.win.winfo_height() <= 708
        footer = window.win.winfo_children()[-1]
        assert footer.winfo_y() + footer.winfo_height() <= window.win.winfo_height()
    finally:
        window.win.destroy()
        i18n.set_language(previous)
