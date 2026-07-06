"""BLE HOGP (HID over GATT) peripheral.

Makes Windows act as a BLE mouse + keyboard. The iPad only needs to
pair with this device from Settings > Bluetooth.

- HID Service (0x1812): Report Map / Reports require encryption.
  The iPad sees the insufficient-encryption error and automatically starts pairing (Just Works + bonding).
- Battery Service (0x180F) and Device Information Service (0x180A, with PnP ID) are
  mandatory per the HOGP spec.
- Bonding keys are persisted to JsonKeyStore, so subsequent connections reconnect automatically.
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
    """Windows battery level (100 if unavailable, e.g. on desktops)."""
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
    """HOGP combo device (keyboard + consumer + mouse)."""

    def __init__(self, config: Config, keystore_file: str | None = None) -> None:
        self.config = config
        self._keystore_file = keystore_file
        self.device: Device | None = None
        self._subscribed = False
        self._connected = False
        # Reconnection session with a bonded host (send notifications without re-writing the CCCD)
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
                # Keyboard LED output report
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
        # The advertising PDU is limited to 31 bytes. The name is placed in the scan response.
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
        # Deterministically derive the IRK from the address (so we reconnect with the same key every time)
        device_config.irk = (bytes(address) * 3)[:16]
        device_config.advertising_data = self._advertising_data()
        device_config.scan_response_data = self._scan_response_data()
        return device_config

    def attach(self, device: Device) -> None:
        """Attach GATT services and pairing configuration to an already-created bumble Device."""
        self.device = device
        device.add_services(self._build_services())
        # identity_address_type=RANDOM is important: if unspecified, bumble distributes the
        # dongle's public address as the identity, but advertising is done with the
        # configured static random address, so on reconnect the iPad judges it to be
        # "a different device" and stops reconnecting automatically.
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
            "Advertising started: name=%r address=%s",
            self.config.device_name,
            self.config.address,
        )

    # ---------------------------------------------------------------- events

    def _on_connection(self, connection) -> None:
        logger.info("Connected: %s", connection.peer_address)
        self._connected = True
        connection.on(connection.EVENT_DISCONNECTION, self._on_disconnection)
        connection.on(
            connection.EVENT_CONNECTION_ENCRYPTION_CHANGE,
            lambda *_args: self._on_encryption_change(connection),
        )
        asyncio.ensure_future(self._ensure_encryption(connection))
        self._notify_state()

    async def _ensure_encryption(self, connection) -> None:
        """On reconnect: if a bonded peer does not start encryption, prompt it ourselves.

        As is standard for HID peripherals, sending an SMP Security Request makes a
        bonded central immediately re-encrypt using the stored LTK.
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
                logger.info("Bonded host reconnecting — requesting encryption")
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
            # Per the HOGP spec, a bonded host reconnects assuming the peripheral
            # remembers the subscription state (CCCD) (it does not re-write the CCCD).
            # A host that was actually in use is always subscribed, so restore the subscription state.
            logger.info("Reconnection complete — subscription state restored (input forwarding enabled)")
            self._subscribed = True
            self._resumed = True
            self._notify_state()

        asyncio.ensure_future(resume_if_bonded())

    def _on_disconnection(self, reason) -> None:
        logger.info("Disconnected (reason=%s)", reason)
        self._connected = False
        self._subscribed = False
        self._resumed = False
        self._notify_state()

    def _on_subscription(self, _connection, notify_enabled, _indicate_enabled) -> None:
        if notify_enabled:
            logger.info("Host subscribed to input reports — input forwarding is now enabled")
            self._subscribed = True
            self._resumed = False  # A real CCCD was written, so forced notifications are not needed
        self._notify_state()

    def _notify_state(self) -> None:
        if self.on_state_change is not None:
            self.on_state_change()

    @property
    def connected(self) -> bool:
        """True once a central (iPad) is connected, before it subscribes."""
        return self._connected

    @property
    def ready(self) -> bool:
        """True when the iPad is connected and ready to accept input reports."""
        return self._connected and self._subscribed

    # ----------------------------------------------------------------- input

    async def send_mouse(
        self, buttons: int, dx: int, dy: int, wheel: int = 0, hwheel: int = 0
    ) -> None:
        assert self.device is not None
        # Split motion that exceeds int16 and send it in chunks
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
        """Prevent stuck keys on transition: release all keys and all buttons."""
        if self.device is None or not self.ready:
            return
        try:
            await self.send_keyboard(0, ())
            await self.send_consumer(0)
            await self.send_mouse(0, 0, 0)
        except Exception:  # Fine to ignore, e.g. right after a disconnect
            logger.debug("release_all failed", exc_info=True)
