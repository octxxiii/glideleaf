"""Application core: bridges the input-capture hook thread and the BLE (asyncio) side."""

from __future__ import annotations

from .i18n import t

import asyncio
import logging
import threading
from typing import Any, Callable

from bumble.device import Device
from bumble.transport import open_transport

from . import keymap
from .ble_peripheral import HogpPeripheral
from .capture import BUTTON_NAMES, InputCapture, enable_dpi_awareness
from .config import Config
from .edge import EdgeStateMachine, State

logger = logging.getLogger(__name__)

# Minimum interval between BLE sends. Sending faster than the connection
# interval (~11-15 ms) is wasted work.
SEND_INTERVAL = 0.004

# Upper bound on the hook-thread event queue. If the BLE link stalls we must
# not buffer input events without limit (long-running tray app: no leaks).
# When full, the oldest events are dropped -- stale motion is worthless anyway.
MAX_QUEUE = 2048


class UniversalControlApp:
    def __init__(self, config: Config, keystore_file: str | None = None) -> None:
        self.config = config
        self.peripheral = HogpPeripheral(config, keystore_file)
        self.machine = EdgeStateMachine(
            edge=config.edge,
            push_threshold_px=config.push_threshold_px,
            return_threshold_px=config.return_threshold_px,
            remote_size=tuple(config.ipad_screen),
            speed=config.speed,
        )
        self.capture: InputCapture | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue: asyncio.Queue[tuple] = asyncio.Queue(maxsize=MAX_QUEUE)
        self.keyboard_state = keymap.KeyboardState()
        self._buttons = 0
        self._consumer_down: int | None = None
        self._wheel_acc = 0.0
        self._hwheel_acc = 0.0
        # Button -> scroll conversion (button index -> action).
        self._button_actions = {
            BUTTON_NAMES[name]: action
            for name, action in config.button_actions.items()
            if name in BUTTON_NAMES
        }
        self._drag_buttons: set[int] = set()  # held drag_scroll buttons
        self._wheel_repeat_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._stop_requested = threading.Event()
        # Optional status callback: called (thread-safely) on connection changes
        # with one of "advertising" | "connected" | "ready".
        self.on_status: Callable[[str], None] | None = None

    # ------------------------------------------------------------ plumbing

    def _emit_from_hook_thread(self, event: tuple) -> None:
        loop = self.loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._enqueue, event)

    def _enqueue(self, event: tuple) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop the oldest event to make room; never grow without bound.
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    def _on_ble_state_change(self) -> None:
        ready = self.peripheral.ready
        if self.capture is not None:
            self.capture.armed = ready
            if not ready and self.machine.state != State.LOCAL:
                logger.warning("BLE link lost -- returning control to Windows")
                self.capture.force_release()
        logger.info("BLE state: %s", "ready" if ready else "not connected")
        if self.on_status is not None:
            if ready:
                status = "ready"
            elif self.peripheral.connected:
                status = "connected"
            else:
                status = "advertising"
            self.on_status(status)

    # --------------------------------------------------------------- setup

    async def run(self, enable_capture: bool = True) -> None:
        self.loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        if self._stop_requested.is_set():
            return
        enable_dpi_awareness()

        async with await open_transport(self.config.transport) as hci_transport:
            device = Device.from_config_with_hci(
                self.peripheral.make_device_configuration(),
                hci_transport.source,
                hci_transport.sink,
            )
            self.peripheral.attach(device)
            self.peripheral.on_state_change = self._on_ble_state_change
            await self.peripheral.start()
            if self.on_status is not None:
                self.on_status("advertising")

            pump = None
            stopping = None
            try:
                if enable_capture:
                    self.capture = InputCapture(
                        self.machine,
                        self._emit_from_hook_thread,
                        release_hotkey=self.config.release_hotkey,
                        forward_injected=self.config.forward_injected,
                        passthrough_buttons=tuple(self.config.passthrough_buttons),
                    )
                    self.capture.start()
                    if not await asyncio.to_thread(self.capture.wait_started):
                        raise RuntimeError(t("입력 캡처를 시작하지 못했습니다."))
                    self.capture.armed = self.peripheral.ready
                pump = asyncio.create_task(self._pump_events())
                stopping = asyncio.create_task(self._stop_event.wait())
                done, _ = await asyncio.wait((pump, stopping), return_when=asyncio.FIRST_COMPLETED)
                if pump in done:
                    await pump
                    raise RuntimeError(t("입력 전송이 중단되었습니다."))
            finally:
                tasks = [task for task in (pump, stopping) if task is not None]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if self._wheel_repeat_task is not None:
                    self._wheel_repeat_task.cancel()
                    self._wheel_repeat_task = None
                if self.capture is not None:
                    self.capture.stop()
                    self.capture = None
                await self.peripheral.release_all()

    def request_stop(self) -> None:
        """Ask the run() loop to shut down cleanly (callable from any thread)."""
        self._stop_requested.set()
        loop, event = self.loop, self._stop_event
        if loop is not None and event is not None and not loop.is_closed():
            loop.call_soon_threadsafe(event.set)

    # --------------------------------------------------------- event pump

    async def _pump_events(self) -> None:
        """Drain hook-thread events, coalescing mouse motion into batched sends."""
        while True:
            event = await self.queue.get()
            dx = dy = 0
            flush_needed = False

            while True:
                kind = event[0]
                if kind == "move":
                    if self._drag_buttons:
                        # Drag-scroll: convert motion into wheel notches.
                        sign = -1 if self.config.drag_scroll_invert else 1
                        px = max(1, self.config.drag_scroll_px)
                        self._wheel_acc += sign * -event[2] / px
                        self._hwheel_acc += sign * event[1] / px
                    else:
                        dx += event[1]
                        dy += event[2]
                    flush_needed = True
                elif kind == "wheel":
                    sign = -1 if self.config.natural_scroll else 1
                    self._wheel_acc += sign * event[1] / 120.0
                    self._hwheel_acc += sign * event[2] / 120.0
                    flush_needed = True
                else:
                    # Preserve ordering: flush pending motion before button/key.
                    if flush_needed:
                        await self._flush_motion(dx, dy)
                        dx = dy = 0
                        flush_needed = False
                    await self._handle_discrete(event)

                if self.queue.empty():
                    break
                event = self.queue.get_nowait()

            if flush_needed:
                await self._flush_motion(dx, dy)
                await asyncio.sleep(SEND_INTERVAL)

    async def _flush_motion(self, dx: int, dy: int) -> None:
        wheel = int(self._wheel_acc)
        hwheel = int(self._hwheel_acc)
        self._wheel_acc -= wheel
        self._hwheel_acc -= hwheel
        if dx or dy or wheel or hwheel:
            if self.peripheral.ready:
                await self.peripheral.send_mouse(self._buttons, dx, dy, wheel, hwheel)

    async def _handle_discrete(self, event: tuple[Any, ...]) -> None:
        kind = event[0]
        if kind == "button":
            _, index, down = event
            action = self._button_actions.get(index)
            if action is not None:
                await self._handle_button_action(index, action, down)
                return
            bit = 1 << index
            self._buttons = (self._buttons | bit) if down else (self._buttons & ~bit)
            if self.peripheral.ready:
                await self.peripheral.send_mouse(self._buttons, 0, 0)
        elif kind == "key":
            await self._handle_key(event)
        elif kind == "state":
            await self._handle_state(event[1])

    async def _handle_button_action(self, index: int, action: str, down: bool) -> None:
        """Button -> scroll conversion (the button itself is not sent to the iPad)."""
        if action == "drag_scroll":
            if down:
                self._drag_buttons.add(index)
            else:
                self._drag_buttons.discard(index)
            return
        if action in ("wheel_up", "wheel_down"):
            if self._wheel_repeat_task is not None:
                self._wheel_repeat_task.cancel()
                self._wheel_repeat_task = None
            if down:
                notches = 1 if action == "wheel_up" else -1
                self._wheel_repeat_task = asyncio.create_task(
                    self._wheel_repeat(notches)
                )

    async def _wheel_repeat(self, notches: int) -> None:
        try:
            while True:
                self._wheel_acc += notches
                await self._flush_motion(0, 0)
                await asyncio.sleep(0.09)
        except asyncio.CancelledError:
            pass

    async def _handle_key(self, event: tuple[Any, ...]) -> None:
        _, vk, scan, extended, down = event

        # Media / system keys go out as Consumer-page usages.
        consumer = keymap.VK_TO_CONSUMER.get(vk)
        if consumer is not None:
            if not self.peripheral.ready:
                return
            if down:
                self._consumer_down = consumer
                await self.peripheral.send_consumer(consumer)
            elif self._consumer_down == consumer:
                self._consumer_down = None
                await self.peripheral.send_consumer(0)
            return

        usage = keymap.scan_to_usage(
            scan, extended, vk=vk, jis_mac_style=self.config.jis_mac_style
        )
        if usage is None:
            return
        if self.config.swap_alt_win:
            usage = keymap.swap_alt_gui(usage)

        changed = (
            self.keyboard_state.press(usage) if down else self.keyboard_state.release(usage)
        )
        if changed and self.peripheral.ready:
            await self.peripheral.send_keyboard(*self.keyboard_state.snapshot())

    async def _handle_state(self, state: str) -> None:
        self.keyboard_state.clear()
        self._buttons = 0
        self._drag_buttons.clear()
        self._wheel_acc = self._hwheel_acc = 0.0
        self._consumer_down = None
        if self._wheel_repeat_task is not None:
            self._wheel_repeat_task.cancel()
            self._wheel_repeat_task = None
        if state == "local":  # returning to Windows
            self._consumer_down = None
            await self.peripheral.release_all()
