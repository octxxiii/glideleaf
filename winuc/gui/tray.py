"""System-tray application: the main entry point for the GUI build.

pystray owns the tray icon on its own thread; Tkinter must run on the main
thread. We keep a hidden Tk root on the main thread and marshal all UI work
(settings window, wizard, dialogs) onto it with `root.after`.
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from tkinter import messagebox
from typing import Callable

import pystray

from .. import autostart
from ..config import Config
from ..paths import config_path
from ..service import (
    STATUS_ADVERTISING,
    STATUS_CONNECTED,
    STATUS_ERROR,
    STATUS_READY,
    STATUS_STARTING,
    STATUS_STOPPED,
    Service,
)
from .icons import make_icon
from .settings import SettingsWindow
from .setup_wizard import SetupWizard

logger = logging.getLogger(__name__)

_STATUS_TEXT = {
    STATUS_STOPPED: "Stopped",
    STATUS_STARTING: "Starting …",
    STATUS_ADVERTISING: "Waiting for iPad …",
    STATUS_CONNECTED: "iPad connected",
    STATUS_READY: "Active — controlling iPad",
    STATUS_ERROR: "Error",
}


class TrayApp:
    def __init__(self) -> None:
        self.config_file = config_path()
        self.config = Config.load(self.config_file)
        if not self.config_file.exists():
            self.config.save(self.config_file)
        self.service = Service()
        self.service.on_status_change = self._on_status_change

        # Hidden Tk root on the main thread. All UI runs here.
        self.root = tk.Tk()
        self.root.withdraw()
        # Marshalling queue: tray-thread callbacks -> main-thread execution.
        self._ui_queue: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._settings_win: SettingsWindow | None = None

        self.icon = pystray.Icon(
            "winuc",
            icon=make_icon(STATUS_STOPPED),
            title="WinUC — Stopped",
            menu=self._build_menu(),
        )
        self._pump_ui_queue()

    # --------------------------------------------------------------- menu

    def _build_menu(self) -> pystray.Menu:
        def running(_item):
            return self.service.running

        def status_label(_item):
            return _STATUS_TEXT.get(self.service.status, self.service.status)

        return pystray.Menu(
            pystray.MenuItem(status_label, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Enabled",
                self._toggle_running,
                checked=lambda _i: self.service.running,
            ),
            pystray.MenuItem("Settings…", self._open_settings),
            pystray.MenuItem("Setup / Dongle…", self._open_wizard),
            pystray.MenuItem(
                "Start at sign-in",
                self._toggle_autostart,
                checked=lambda _i: autostart.is_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    # ------------------------------------------------- main-thread marshal

    def _on_main(self, fn: Callable[[], None]) -> None:
        self._ui_queue.put(fn)

    def _pump_ui_queue(self) -> None:
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    logger.exception("UI callback failed")
        except queue.Empty:
            pass
        self.root.after(100, self._pump_ui_queue)

    # ------------------------------------------------------------ actions

    def _toggle_running(self, _icon=None, _item=None) -> None:
        if self.service.running:
            self.service.stop()
        else:
            self.service.start(self.config)
        self._refresh_icon()

    def _open_settings(self, _icon=None, _item=None) -> None:
        def show():
            if self._settings_win is not None and self._settings_win.win.winfo_exists():
                self._settings_win.win.lift()
                return
            self._settings_win = SettingsWindow(self.root, self.config, self._apply_config)
        self._on_main(show)

    def _open_wizard(self, _icon=None, _item=None) -> None:
        self._on_main(lambda: SetupWizard(self.root))

    def _apply_config(self, config: Config) -> None:
        self.config = config
        config.save(self.config_file)
        if self.service.running:
            # Restart the link so new settings take effect immediately.
            self.service.restart(config)
        self._refresh_icon()

    def _toggle_autostart(self, _icon=None, _item=None) -> None:
        autostart.set_enabled(not autostart.is_enabled())

    def _quit(self, _icon=None, _item=None) -> None:
        self.service.stop()
        self.icon.stop()
        self._on_main(self.root.quit)

    # ------------------------------------------------------------- status

    def _on_status_change(self, status: str) -> None:
        # Called from the service thread; marshal icon update safely.
        self._on_main(self._refresh_icon)
        if status == STATUS_ERROR:
            err = self.service.last_error or "Unknown error"
            self._on_main(lambda: messagebox.showerror(
                "WinUC", f"The BLE service stopped:\n\n{err}", parent=self.root))

    def _refresh_icon(self) -> None:
        status = self.service.status
        self.icon.icon = make_icon(status)
        self.icon.title = f"WinUC — {_STATUS_TEXT.get(status, status)}"
        self.icon.update_menu()

    # --------------------------------------------------------------- loop

    def run(self, autostart_service: bool = True, first_run: bool = False) -> None:
        # pystray runs its own thread; Tk mainloop stays on the main thread.
        self.icon.run_detached()
        if first_run:
            self._on_main(lambda: SetupWizard(self.root))
        elif autostart_service:
            self.service.start(self.config)
            self._refresh_icon()
        try:
            self.root.mainloop()
        finally:
            self.service.stop()
            try:
                self.icon.stop()
            except Exception:
                pass


def main(first_run: bool = False) -> int:
    TrayApp().run(autostart_service=not first_run, first_run=first_run)
    return 0
