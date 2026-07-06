"""アプリ本体: 入力キャプチャ (フックスレッド) と BLE (asyncio) の橋渡し。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bumble.device import Device
from bumble.transport import open_transport

from . import keymap
from .ble_peripheral import HogpPeripheral
from .capture import BUTTON_NAMES, InputCapture, enable_dpi_awareness
from .config import Config
from .edge import EdgeStateMachine, State

logger = logging.getLogger(__name__)

# BLE 送信の最小間隔 (秒)。接続インターバル (~11-15ms) より細かく送っても無駄。
SEND_INTERVAL = 0.004


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
        self.queue: asyncio.Queue[tuple] = asyncio.Queue()
        self.keyboard_state = keymap.KeyboardState()
        self._buttons = 0
        self._consumer_down: int | None = None
        self._wheel_acc = 0.0
        self._hwheel_acc = 0.0
        # ボタン→スクロール変換 (index → action)
        self._button_actions = {
            BUTTON_NAMES[name]: action
            for name, action in config.button_actions.items()
            if name in BUTTON_NAMES
        }
        self._drag_buttons: set[int] = set()  # 押下中の drag_scroll ボタン
        self._wheel_repeat_task: asyncio.Task | None = None

    # ------------------------------------------------------------ plumbing

    def _emit_from_hook_thread(self, event: tuple) -> None:
        assert self.loop is not None
        self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

    def _on_ble_state_change(self) -> None:
        ready = self.peripheral.ready
        if self.capture is not None:
            self.capture.armed = ready
            if not ready and self.machine.state != State.LOCAL:
                logger.warning("BLE 切断のため Windows に制御を戻します")
                self.capture.force_release()
        logger.info("BLE 状態: %s", "転送可能" if ready else "未接続")

    # --------------------------------------------------------------- setup

    async def run(self, enable_capture: bool = True) -> None:
        self.loop = asyncio.get_running_loop()
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

            print()
            print("=" * 64)
            print(f"  iPad の 設定 > Bluetooth から")
            print(f"  「{self.config.device_name}」 に接続してください。")
            print(f"  接続後、マウスカーソルを画面の {self._edge_label()} に")
            print(f"  押し込むと iPad 側へ移動します。")
            print(f"  強制的に戻る: {self.config.release_hotkey}")
            print("=" * 64)
            print()

            if enable_capture:
                self.capture = InputCapture(
                    self.machine,
                    self._emit_from_hook_thread,
                    release_hotkey=self.config.release_hotkey,
                    forward_injected=self.config.forward_injected,
                    passthrough_buttons=tuple(self.config.passthrough_buttons),
                )
                self.capture.start()
                self.capture.wait_started()

            try:
                await self._pump_events()
            finally:
                if self.capture is not None:
                    self.capture.stop()

    def _edge_label(self) -> str:
        return {"right": "右端", "left": "左端", "top": "上端", "bottom": "下端"}[
            self.config.edge
        ]

    # --------------------------------------------------------- event pump

    async def _pump_events(self) -> None:
        """フックスレッドからのイベントを取り出し、マウス移動を合成して送る。"""
        while True:
            event = await self.queue.get()
            dx = dy = 0
            flush_needed = False

            while True:
                kind = event[0]
                if kind == "move":
                    if self._drag_buttons:
                        # ドラッグスクロール中: 移動をスクロールに変換
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
                    # 順序を保つ: ボタン/キーの前に溜まった移動を送る
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
        """ボタン→スクロール変換 (ボタン自体は iPad に送らない)。"""
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

        # メディアキー等は Consumer usage で送る
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
        if self._wheel_repeat_task is not None:
            self._wheel_repeat_task.cancel()
            self._wheel_repeat_task = None
        if state == "local":  # local へ復帰
            self._consumer_down = None
            await self.peripheral.release_all()
