"""System-tray application: the main entry point for the GUI build.

pystray owns the tray icon on its own thread; Tkinter must run on the main
thread. We keep a hidden Tk root on the main thread and marshal all UI work
(settings window, wizard, dialogs) onto it with `root.after`.
"""

from __future__ import annotations

from ..i18n import t
from ..i18n import set_language
from dataclasses import replace

import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable

import pystray

from .. import autostart
from .. import driver
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
from .dashboard import Dashboard

logger = logging.getLogger(__name__)

_STATUS_TEXT = {
    STATUS_STOPPED: "연결 꺼짐",
    STATUS_STARTING: "연결 준비 중",
    STATUS_ADVERTISING: "iPad 연결 대기",
    STATUS_CONNECTED: "iPad 연결됨",
    STATUS_READY: "입력 공유 준비 완료",
    STATUS_ERROR: "연결 오류",
}


class TrayApp:
    def __init__(self) -> None:
        self.config_file = config_path()
        self.config = Config.load(self.config_file)
        set_language(self.config.language)
        if not self.config_file.exists():
            self.config.save(self.config_file)
        self.service = Service()
        self.service.on_status_change = self._on_status_change

        from ..capture import enable_dpi_awareness
        enable_dpi_awareness()

        # Hidden Tk root on the main thread. All UI runs here.
        self.root = tk.Tk()
        self.root.withdraw()
        # Marshalling queue: tray-thread callbacks -> main-thread execution.
        self._ui_queue: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._settings_win: SettingsWindow | None = None
        self._dashboard = None
        self._wizard = None

        self.icon = pystray.Icon(
            "glideleaf",
            icon=make_icon(STATUS_STOPPED),
            title="Glideleaf",
            menu=self._build_menu(),
        )
        self._pump_ui_queue()

    # --------------------------------------------------------------- menu

    def _build_menu(self) -> pystray.Menu:
        def running(_item):
            return self.service.running

        def status_label(_item):
            return t(_STATUS_TEXT.get(self.service.status, self.service.status))

        return pystray.Menu(
            pystray.MenuItem(t("Glideleaf 연결 패널"), self._open_dashboard, default=True),
            pystray.MenuItem(status_label, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                t("입력 공유 사용"),
                self._toggle_running,
                checked=lambda _i: self.service.running,
            ),
            pystray.MenuItem(t("설정…"), self._open_settings),
            pystray.MenuItem(t("동글 설정 / 복원…"), self._open_wizard),
            pystray.MenuItem(
                t("로그인 시 자동 실행"),
                self._toggle_autostart,
                checked=lambda _i: autostart.is_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("종료"), self._quit),
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

    def _has_adapter_choice(self) -> bool:
        # Preserve explicit legacy/manual transports, but never auto-open the
        # default USB index before a new GUI user has applied an adapter.
        return bool(self.config.adapter_id) or self.config.transport != Config().transport

    def _toggle_running(self, _icon=None, _item=None) -> None:
        if self.service.running:
            self.service.stop()
        else:
            self._start_service()
        self._on_main(self._refresh_icon)

    def _start_service(self) -> None:
        # Run on a worker: PnP discovery can take seconds. Driver setup is a
        # normal prerequisite, not a BLE service crash. Keep the app's own
        # validation as a final guard against unplugging after this check.
        config = self.config
        if not self._has_adapter_choice():
            self._open_wizard()
            return
        if config.adapter_id:
            try:
                driver.require_selected_adapter(config.adapter_id, config.transport)
            except RuntimeError as exc:
                self._open_wizard()
                message = str(exc)
                self._on_main(lambda: messagebox.showinfo(
                    t("동글 설정 / 복원…"), message, parent=self.root))
                return
        if config != self.config:
            # The user applied another choice while discovery was running.
            return
        self.service.start(config)

    def _open_dashboard(self, _icon=None, _item=None) -> None:
        def show():
            if self._dashboard is not None and self._dashboard.win.winfo_exists():
                self._dashboard.win.deiconify()
                self._dashboard.win.lift()
            else:
                self._dashboard = Dashboard(self)
        self._on_main(show)

    def _open_settings(self, _icon=None, _item=None) -> None:
        def show():
            if self._settings_win is not None and self._settings_win.win.winfo_exists():
                self._settings_win.win.lift()
                return
            self._settings_win = SettingsWindow(self.root, self.config, self._apply_config)
        self._on_main(show)

    def _open_wizard(self, _icon=None, _item=None) -> None:
        def show():
            if self._wizard is not None and self._wizard.win.winfo_exists():
                self._wizard.win.lift()
            else:
                self._wizard = self._make_wizard()
        self._on_main(show)

    def _make_wizard(self) -> SetupWizard:
        return SetupWizard(self.root, on_apply=self._apply_dongle,
                           active_adapter_id=self.config.adapter_id,
                           prepare_driver=self._prepare_adapter_driver)

    def _apply_dongle(self, selected: driver.Dongle) -> None:
        # Called by the wizard worker, never change Tk widgets here.
        current = driver.resolve_selected_adapter(selected.identity)
        previous = self.config
        config = replace(previous, transport=current.transport, adapter_id=current.identity)
        if config == previous:
            return
        was_running = self.service.running
        if was_running:
            self.service.stop()
            if self.service.running:
                raise RuntimeError(t("서비스 종료를 기다리고 있습니다. 잠시 후 다시 시도해 주세요."))
        try:
            config.save(self.config_file)
        except Exception:
            if was_running:
                self.service.start(previous)
            raise
        self.config = config
        if was_running and current.is_winusb:
            self.service.start(config)
        self._on_main(self._refresh_icon)
        self._on_main(self._sync_settings_adapter)

    def _sync_settings_adapter(self) -> None:
        settings = getattr(self, "_settings_win", None)
        if settings is not None and settings.win.winfo_exists():
            settings.config = self.config
            settings.vars["transport"].set(self.config.transport)
        wizard = getattr(self, "_wizard", None)
        if wizard is not None and wizard.win.winfo_exists():
            wizard.set_active_adapter(self.config.adapter_id)

    def _prepare_adapter_driver(self, selected: driver.Dongle) -> None:
        driver.resolve_selected_adapter(selected.identity)
        if self.service.running:
            self.service.stop()
            if self.service.running:
                raise RuntimeError(t("서비스 종료를 기다리고 있습니다. 잠시 후 다시 시도해 주세요."))
        self._on_main(self._refresh_icon)

    def _apply_config(self, config: Config) -> None:
        config.save(self.config_file)
        previous = self.config
        self.config = config
        language_changed = previous.language != config.language
        set_language(config.language)
        if self.service.running and replace(previous, language=config.language) != config:
            # Restart the link so new settings take effect immediately.
            if self._has_adapter_choice():
                self.service.restart(config)
            else:
                self.service.stop()
        if language_changed:
            self.root.after_idle(self._refresh_language)
        self._sync_settings_adapter()
        self._refresh_icon()

    def _refresh_language(self) -> None:
        self.icon.menu = self._build_menu()
        self.icon.update_menu()
        if self._dashboard is not None and self._dashboard.win.winfo_exists():
            self._dashboard.close()
            self._dashboard = Dashboard(self)
        self._refresh_wizard_language()

    def _refresh_wizard_language(self) -> None:
        wizard = self._wizard
        if wizard is None or not wizard.win.winfo_exists():
            return
        if wizard._busy:
            self.root.after(100, self._refresh_wizard_language)
            return
        wizard._close()
        self._wizard = self._make_wizard()

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
            err = self.service.last_error or t("알 수 없는 오류")
            self._on_main(lambda: messagebox.showerror(
                "Glideleaf", t("BLE 서비스가 중단되었습니다:\n\n{error}", error=err), parent=self.root))

    def _refresh_icon(self) -> None:
        status = self.service.status
        self.icon.icon = make_icon(status)
        self.icon.title = f"Glideleaf — {t(_STATUS_TEXT.get(status, status))}"
        self.icon.update_menu()

    # --------------------------------------------------------------- loop

    def run(self, autostart_service: bool = True, first_run: bool = False) -> None:
        # pystray runs its own thread; Tk mainloop stays on the main thread.
        self.icon.run_detached()
        self._open_dashboard()
        if first_run:
            self._open_wizard()
        elif autostart_service:
            threading.Thread(target=self._start_service, daemon=True).start()
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
