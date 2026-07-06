"""BLE HOGP (HID over GATT) ペリフェラル。

Windows を BLE マウス+キーボードとして振る舞わせる。iPad は
Settings > Bluetooth からこのデバイスにペアリングするだけでよい。

- HID Service (0x1812): Report Map / Reports は暗号化必須にする。
  iPad は暗号化不足エラーを見て自動的にペアリング (Just Works + bonding) を開始する。
- Battery Service (0x180F), Device Information Service (0x180A, PnP ID 付き) は
  HOGP 仕様上必須。
- ボンディング鍵は JsonKeyStore に永続化され、次回以降は自動再接続する。
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import struct
import sys
from typing import Callable

from bumble import data_types
from bumble import hci
from bumble.core import AdvertisingData
from bumble.device import Device, DeviceConfiguration
from bumble.gatt import (
    GATT_BATTERY_LEVEL_CHARACTERISTIC,
    GATT_BATTERY_SERVICE,
    GATT_DEVICE_INFORMATION_SERVICE,
    GATT_HID_CONTROL_POINT_CHARACTERISTIC,
    GATT_HID_INFORMATION_CHARACTERISTIC,
    GATT_HUMAN_INTERFACE_DEVICE_SERVICE,
    GATT_MANUFACTURER_NAME_STRING_CHARACTERISTIC,
    GATT_MODEL_NUMBER_STRING_CHARACTERISTIC,
    GATT_PNP_ID_CHARACTERISTIC,
    GATT_PROTOCOL_MODE_CHARACTERISTIC,
    GATT_REPORT_CHARACTERISTIC,
    GATT_REPORT_MAP_CHARACTERISTIC,
    GATT_REPORT_REFERENCE_DESCRIPTOR,
    Characteristic,
    CharacteristicValue,
    Descriptor,
    Service,
)
from bumble.pairing import PairingConfig

from .config import Config
from . import hid_reports as hr

logger = logging.getLogger(__name__)

HID_REPORT_PROTOCOL = 0x01
HID_INPUT_REPORT = 0x01
HID_OUTPUT_REPORT = 0x02


def _battery_percent() -> int:
    """Windows のバッテリー残量 (デスクトップ等、取得不能なら 100)。"""
    if sys.platform != "win32":
        return 100

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    status = SYSTEM_POWER_STATUS()
    try:
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            if status.BatteryLifePercent <= 100:
                return status.BatteryLifePercent
    except OSError:
        pass
    return 100


class HogpPeripheral:
    """HOGP コンボデバイス (キーボード + コンシューマ + マウス)。"""

    def __init__(self, config: Config, keystore_file: str | None = None) -> None:
        self.config = config
        self._keystore_file = keystore_file
        self.device: Device | None = None
        self._subscribed = False
        self._connected = False
        # ボンド済みホストとの再接続セッション (CCCD の再書き込みなしで通知を送る)
        self._resumed = False
        self.on_state_change: Callable[[], None] | None = None

        self._kbd_input = self._input_report(hr.REPORT_ID_KEYBOARD, hr.KEYBOARD_REPORT_SIZE)
        self._consumer_input = self._input_report(hr.REPORT_ID_CONSUMER, hr.CONSUMER_REPORT_SIZE)
        self._mouse_input = self._input_report(hr.REPORT_ID_MOUSE, hr.MOUSE_REPORT_SIZE)

        for characteristic in (self._kbd_input, self._consumer_input, self._mouse_input):
            characteristic.on(
                Characteristic.EVENT_SUBSCRIPTION, self._on_subscription
            )

    # ------------------------------------------------------------------ GATT

    @staticmethod
    def _input_report(report_id: int, size: int) -> Characteristic:
        return Characteristic(
            GATT_REPORT_CHARACTERISTIC,
            Characteristic.Properties.READ | Characteristic.Properties.NOTIFY,
            Characteristic.READABLE
            | Characteristic.Permissions.READ_REQUIRES_ENCRYPTION,
            bytes(size),
            [
                Descriptor(
                    GATT_REPORT_REFERENCE_DESCRIPTOR,
                    Descriptor.READABLE,
                    bytes([report_id, HID_INPUT_REPORT]),
                )
            ],
        )

    def _build_services(self) -> list[Service]:
        config = self.config

        def on_control_point(_connection, value: bytes) -> None:
            logger.debug("HID Control Point write: %s", value.hex())

        def on_led_output(_connection, value: bytes) -> None:
            logger.debug("Keyboard LED output: %s", value.hex())

        def on_read_battery(_connection) -> bytes:
            return bytes([_battery_percent()])

        hid_service = Service(
            GATT_HUMAN_INTERFACE_DEVICE_SERVICE,
            [
                Characteristic(
                    GATT_PROTOCOL_MODE_CHARACTERISTIC,
                    Characteristic.Properties.READ
                    | Characteristic.Properties.WRITE_WITHOUT_RESPONSE,
                    Characteristic.READABLE | Characteristic.WRITEABLE,
                    bytes([HID_REPORT_PROTOCOL]),
                ),
                Characteristic(
                    GATT_HID_INFORMATION_CHARACTERISTIC,
                    Characteristic.Properties.READ,
                    Characteristic.READABLE,
                    hr.HID_INFORMATION,
                ),
                Characteristic(
                    GATT_HID_CONTROL_POINT_CHARACTERISTIC,
                    Characteristic.Properties.WRITE_WITHOUT_RESPONSE,
                    Characteristic.WRITEABLE,
                    CharacteristicValue(write=on_control_point),
                ),
                Characteristic(
                    GATT_REPORT_MAP_CHARACTERISTIC,
                    Characteristic.Properties.READ,
                    Characteristic.READABLE
                    | Characteristic.Permissions.READ_REQUIRES_ENCRYPTION,
                    hr.REPORT_MAP,
                ),
                self._kbd_input,
                self._consumer_input,
                self._mouse_input,
                # キーボード LED 出力レポート
                Characteristic(
                    GATT_REPORT_CHARACTERISTIC,
                    Characteristic.Properties.READ
                    | Characteristic.Properties.WRITE
                    | Characteristic.Properties.WRITE_WITHOUT_RESPONSE,
                    Characteristic.READABLE
                    | Characteristic.WRITEABLE
                    | Characteristic.Permissions.WRITE_REQUIRES_ENCRYPTION,
                    CharacteristicValue(write=on_led_output),
                    [
                        Descriptor(
                            GATT_REPORT_REFERENCE_DESCRIPTOR,
                            Descriptor.READABLE,
                            bytes([hr.REPORT_ID_KEYBOARD, HID_OUTPUT_REPORT]),
                        )
                    ],
                ),
            ],
        )

        dis = Service(
            GATT_DEVICE_INFORMATION_SERVICE,
            [
                Characteristic(
                    GATT_MANUFACTURER_NAME_STRING_CHARACTERISTIC,
                    Characteristic.Properties.READ,
                    Characteristic.READABLE,
                    config.manufacturer_name.encode("utf-8"),
                ),
                Characteristic(
                    GATT_MODEL_NUMBER_STRING_CHARACTERISTIC,
                    Characteristic.Properties.READ,
                    Characteristic.READABLE,
                    b"WinUC-1",
                ),
                Characteristic(
                    GATT_PNP_ID_CHARACTERISTIC,
                    Characteristic.Properties.READ,
                    Characteristic.READABLE,
                    struct.pack(
                        "<BHHH",
                        config.pnp.vendor_id_source,
                        config.pnp.vendor_id,
                        config.pnp.product_id,
                        config.pnp.product_version,
                    ),
                ),
            ],
        )

        battery = Service(
            GATT_BATTERY_SERVICE,
            [
                Characteristic(
                    GATT_BATTERY_LEVEL_CHARACTERISTIC,
                    Characteristic.Properties.READ | Characteristic.Properties.NOTIFY,
                    Characteristic.READABLE,
                    CharacteristicValue(read=on_read_battery),
                )
            ],
        )

        return [dis, hid_service, battery]

    def _advertising_data(self) -> bytes:
        # アドバタイジング PDU は 31 バイトまで。名前はスキャンレスポンス側に置く。
        return bytes(
            AdvertisingData(
                [
                    data_types.Flags(
                        AdvertisingData.Flags.LE_GENERAL_DISCOVERABLE_MODE
                        | AdvertisingData.Flags.BR_EDR_NOT_SUPPORTED
                    ),
                    data_types.CompleteListOf16BitServiceUUIDs(
                        [GATT_HUMAN_INTERFACE_DEVICE_SERVICE]
                    ),
                    data_types.Appearance(
                        data_types.Appearance.Category.HUMAN_INTERFACE_DEVICE,
                        data_types.Appearance.HumanInterfaceDeviceSubcategory.KEYBOARD,
                    ),
                ]
            )
        )

    def _scan_response_data(self) -> bytes:
        name = self.config.device_name.encode("utf-8")[:29].decode("utf-8", "ignore")
        return bytes(AdvertisingData([data_types.CompleteLocalName(name)]))

    # ----------------------------------------------------------------- setup

    def make_device_configuration(self) -> DeviceConfiguration:
        address = hci.Address(
            self.config.address, hci.Address.RANDOM_DEVICE_ADDRESS
        )
        device_config = DeviceConfiguration(
            name=self.config.device_name,
            address=address,
            advertising_interval_min=30.0,
            advertising_interval_max=50.0,
            keystore="JsonKeyStore"
            if self._keystore_file is None
            else f"JsonKeyStore:{self._keystore_file}",
            classic_enabled=False,
        )
        # アドレスから決定的に IRK を導出 (毎回同じ鍵で再接続できるように)
        device_config.irk = (bytes(address) * 3)[:16]
        device_config.advertising_data = self._advertising_data()
        device_config.scan_response_data = self._scan_response_data()
        return device_config

    def attach(self, device: Device) -> None:
        """作成済みの bumble Device に GATT サービス・ペアリング設定を取り付ける。"""
        self.device = device
        device.add_services(self._build_services())
        # identity_address_type=RANDOM が重要: 未指定だと bumble はドングルの
        # 公開アドレスをアイデンティティとして配布するが、アドバタイズは
        # 設定の静的ランダムアドレスで行うため、iPad が再接続時に
        # 「別のデバイス」と判断して自動再接続しなくなる。
        device.pairing_config_factory = lambda _connection: PairingConfig(
            sc=True,
            mitm=False,
            bonding=True,
            identity_address_type=PairingConfig.AddressType.RANDOM,
        )
        device.on(device.EVENT_CONNECTION, self._on_connection)

    async def start(self) -> None:
        assert self.device is not None
        await self.device.power_on()
        await self.device.start_advertising(auto_restart=True)
        logger.info(
            "アドバタイズ開始: name=%r address=%s",
            self.config.device_name,
            self.config.address,
        )

    # ---------------------------------------------------------------- events

    def _on_connection(self, connection) -> None:
        logger.info("接続: %s", connection.peer_address)
        self._connected = True
        connection.on(connection.EVENT_DISCONNECTION, self._on_disconnection)
        connection.on(
            connection.EVENT_CONNECTION_ENCRYPTION_CHANGE,
            lambda *_args: self._on_encryption_change(connection),
        )
        asyncio.ensure_future(self._ensure_encryption(connection))
        self._notify_state()

    async def _ensure_encryption(self, connection) -> None:
        """再接続時: ボンド済みの相手が暗号化を始めない場合、こちらから促す。

        HID ペリフェラルの定石で、SMP Security Request を送ると
        ボンド済みのセントラルは保存済み LTK で即座に再暗号化する。
        """
        await asyncio.sleep(1.0)
        try:
            if (
                self.device is None
                or connection.is_encrypted
                or self.device.keystore is None
            ):
                return
            keys = await self.device.keystore.get(str(connection.peer_address))
            if keys is not None:
                logger.info("ボンド済みホストの再接続 — 暗号化を要求します")
                self.device.request_pairing(connection)
        except Exception:
            logger.debug("_ensure_encryption failed", exc_info=True)

    def _on_encryption_change(self, connection) -> None:
        if not connection.is_encrypted or self._subscribed:
            return

        async def resume_if_bonded() -> None:
            if self.device is None or self.device.keystore is None:
                return
            keys = await self.device.keystore.get(str(connection.peer_address))
            if keys is None:
                return
            # ボンド済みホストは HOGP 仕様上、購読状態 (CCCD) をペリフェラルが
            # 記憶している前提で再接続してくる (CCCD を書き直さない)。
            # 実際に使っていたホストなら必ず購読済みなので、購読状態を復元する。
            logger.info("再接続完了 — 購読状態を復元しました (入力転送可能)")
            self._subscribed = True
            self._resumed = True
            self._notify_state()

        asyncio.ensure_future(resume_if_bonded())

    def _on_disconnection(self, reason) -> None:
        logger.info("切断 (reason=%s)", reason)
        self._connected = False
        self._subscribed = False
        self._resumed = False
        self._notify_state()

    def _on_subscription(self, _connection, notify_enabled, _indicate_enabled) -> None:
        if notify_enabled:
            logger.info("ホストが入力レポートを購読 — 入力転送が可能になりました")
            self._subscribed = True
            self._resumed = False  # 実際の CCCD が書かれたので force 通知は不要
        self._notify_state()

    def _notify_state(self) -> None:
        if self.on_state_change is not None:
            self.on_state_change()

    @property
    def ready(self) -> bool:
        """iPad が接続済みで、入力を受け付けられる状態か。"""
        return self._connected and self._subscribed

    # ----------------------------------------------------------------- input

    async def send_mouse(
        self, buttons: int, dx: int, dy: int, wheel: int = 0, hwheel: int = 0
    ) -> None:
        assert self.device is not None
        # int16 を超える移動は分割して送る
        while True:
            step_x = max(-32767, min(32767, dx))
            step_y = max(-32767, min(32767, dy))
            value = hr.mouse_report(buttons, step_x, step_y, wheel, hwheel)
            self._mouse_input.value = value
            await self.device.notify_subscribers(self._mouse_input, force=self._resumed)
            dx -= step_x
            dy -= step_y
            wheel = hwheel = 0
            if dx == 0 and dy == 0:
                return

    async def send_keyboard(self, modifiers: int, keys: tuple[int, ...]) -> None:
        assert self.device is not None
        value = hr.keyboard_report(modifiers, keys)
        self._kbd_input.value = value
        await self.device.notify_subscribers(self._kbd_input, force=self._resumed)

    async def send_consumer(self, usage: int) -> None:
        assert self.device is not None
        value = hr.consumer_report(usage)
        self._consumer_input.value = value
        await self.device.notify_subscribers(self._consumer_input, force=self._resumed)

    async def release_all(self) -> None:
        """遷移時の押しっぱなし防止: 全キー・全ボタンを解放。"""
        if self.device is None or not self.ready:
            return
        try:
            await self.send_keyboard(0, ())
            await self.send_consumer(0)
            await self.send_mouse(0, 0, 0)
        except Exception:  # 切断直後などは無視してよい
            logger.debug("release_all failed", exc_info=True)
