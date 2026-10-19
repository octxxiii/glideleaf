"""Render desktop windows with fake BLE state, without changing drivers."""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from winuc.capture import enable_dpi_awareness
enable_dpi_awareness()

import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch
from PIL import ImageGrab

from winuc.config import Config
from winuc.i18n import set_language, t, LANGUAGES
from winuc.gui.dashboard import Dashboard
from winuc.gui.settings import SettingsWindow
from winuc.gui.setup_wizard import SetupWizard


def settle(root, delay=300):
    root.after(delay, root.quit)
    root.mainloop()


def capture(win, name):
    win.geometry("+30+30")
    win.deiconify()
    win.lift()
    win.attributes("-topmost", True)
    settle(win, 1000)
    x, y = win.winfo_rootx(), win.winfo_rooty()
    target = Path(__file__).resolve().parents[1] / "artifacts"
    target.mkdir(exist_ok=True)
    ImageGrab.grab(bbox=(x, y, x + win.winfo_width(), y + win.winfo_height())).save(target / name)
    win.attributes("-topmost", False)


def main(language="ko"):
    set_language(language)
    root = tk.Tk()
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    app = SimpleNamespace(root=root, config=Config(language=language), service=SimpleNamespace(status="advertising", running=True, last_error=None), _open_settings=lambda: None, _open_wizard=lambda: None, _toggle_running=lambda: None)
    panel = Dashboard(app)
    for state in ("stopped", "starting", "advertising", "connected", "ready", "error"):
        app.service.status = state
        app.service.last_error = "동글 연결을 확인해 주세요." if state == "error" else None
        panel.win.after_cancel(panel._timer)
        panel.refresh()
        settle(root)
        assert panel.title.get()
    app.service.status, app.service.last_error = "advertising", None
    panel.win.after_cancel(panel._timer)
    panel.refresh()
    capture(panel.win, f"dashboard-{language}.png")
    assert panel.log_toggle.winfo_ismapped(), (language, "footer hidden")
    assert panel.log_toggle.winfo_rooty() + panel.log_toggle.winfo_height() <= panel.win.winfo_rooty() + panel.win.winfo_height(), (language, "footer clipped")
    with patch("tkinter.messagebox.showinfo") as about:
        panel.show_about()
        assert t("fuba 감사") in about.call_args.args[1]
    panel.toggle_logs()
    settle(root)
    assert panel.logs.winfo_manager()
    panel.toggle_logs()
    assert not panel.logs.winfo_manager()
    panel.close()

    saved = []
    settings = SettingsWindow(root, app.config, saved.append)
    capture(settings.win, f"settings-{language}.png")
    settings.vars["speed"].set(0)
    with patch("winuc.gui.settings.messagebox.showerror") as error:
        settings._save()
        error.assert_called_once()
    assert not saved and app.config.speed == 1
    settings.vars["speed"].set(1.7)
    settings.vars["edge"].set(t("왼쪽"))
    settings.vars["language"].set(settings._language_labels["ja"])
    settings._btn_vars["x1"].set(t("위로 스크롤"))
    settings._save()
    assert saved[0].speed == 1.7 and saved[0].edge == "left"
    assert saved[0].language == "ja" and saved[0].button_actions == {"x1": "wheel_up"}
    assert app.config.speed == 1 and app.config.edge == "right"

    with patch("winuc.gui.setup_wizard.driver._pnp_query", return_value=[]):
        wizard = SetupWizard(root)
        settle(root)
        assert not wizard._busy
        assert wizard.status_var.get() == t("USB 블루투스 동글을 찾지 못했습니다.\n지원 동글을 연결하고 다시 검색하세요. Realtek RTL8761B 계열을 권장합니다.")
        with patch.object(wizard.win, "clipboard_clear"), patch.object(wizard.win, "clipboard_append") as clipboard:
            wizard._copy_diagnostics()
            assert '"usb_node_count": 0' in clipboard.call_args.args[0]
        capture(wizard.win, f"setup-{language}.png")
        wizard.refresh()
        wizard._close()
        settle(root)
    root.destroy()
    assert not errors, errors
    print(f"PASS {language}: six states, footer layout, credits, log toggle, validation, localized settings roundtrip, async wizard close")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", choices=LANGUAGES, default="ko")
    main(parser.parse_args().language)
