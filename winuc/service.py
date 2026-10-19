"""Background service supervisor.

Owns the asyncio event loop and the BLE + input-capture app on a worker
thread so the Tk/pystray GUI stays on the main thread. Designed for a
long-running tray process: clean start/stop, no leaked threads or tasks,
and a small fixed set of state.
"""

from __future__ import annotations

from .i18n import t

import asyncio
import logging
import threading
from copy import deepcopy
from typing import Callable

from .app import UniversalControlApp
from .config import Config
from .paths import keystore_path

logger = logging.getLogger(__name__)

# Service status, surfaced to the GUI.
STATUS_STOPPED = "stopped"
STATUS_STARTING = "starting"
STATUS_ADVERTISING = "advertising"   # radio up, no iPad connected
STATUS_CONNECTED = "connected"       # iPad connected, not yet subscribed
STATUS_READY = "ready"               # iPad connected and receiving input
STATUS_ERROR = "error"


class Service:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._app: UniversalControlApp | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._status = STATUS_STOPPED
        self._last_error: str | None = None
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        # Called (from arbitrary threads) whenever status changes.
        self.on_status_change: Callable[[str], None] | None = None

    # --------------------------------------------------------------- state

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _set_status(self, status: str) -> None:
        if status == self._status:
            return
        self._status = status
        callback = self.on_status_change
        if callback is not None:
            try:
                callback(status)
            except Exception:
                logger.debug("status callback failed", exc_info=True)

    # ------------------------------------------------------------ control

    def start(self, config: Config) -> None:
        config.validate()
        with self._lock:
            if self.running:
                return
            self._last_error = None
            self._stop_requested.clear()
            self._set_status(STATUS_STARTING)
            self._thread = threading.Thread(
                target=self._run, args=(deepcopy(config),), name="winuc-service", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_requested.set()
        with self._lock:
            app, thread = self._app, self._thread
        if app is not None:
            app.request_stop()
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                self._last_error = t("서비스 종료를 기다리고 있습니다. 잠시 후 다시 시도해 주세요.")
                self._set_status(STATUS_ERROR)
                return
        with self._lock:
            self._thread = None
            self._app = None
            self._loop = None
        self._set_status(STATUS_STOPPED)

    def restart(self, config: Config) -> None:
        self.stop()
        if not self.running:
            self.start(config)

    # ------------------------------------------------------------- worker

    def _run(self, config: Config) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            app = UniversalControlApp(config, keystore_file=str(keystore_path()))
            app.on_status = self._set_status
            with self._lock:
                self._loop = loop
                self._app = app
            if self._stop_requested.is_set():
                self._set_status(STATUS_STOPPED)
                return
            async def run_app():
                task = asyncio.create_task(app.run(enable_capture=True))
                try:
                    while not task.done():
                        if self._stop_requested.is_set():
                            app.request_stop()
                        await asyncio.sleep(0.02)
                    await task
                finally:
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
            loop.run_until_complete(run_app())
        except Exception as exc:  # transport open failure, HCI error, etc.
            logger.error("service stopped with error: %s", exc, exc_info=True)
            self._last_error = str(exc)
            self._set_status(STATUS_ERROR)
        else:
            self._set_status(STATUS_STOPPED)
        finally:
            try:
                _cancel_pending(loop)
            finally:
                loop.close()


def _cancel_pending(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel any stragglers so the loop can close without leaking tasks."""
    pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
