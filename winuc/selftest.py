"""Self-test that validates the BLE layer without a physical dongle.

Connects two of bumble's virtual controllers over a LocalLink, running the
WinUC HOGP peripheral on one and a central acting as the iPad on the other.
Runs the full flow: pairing (Just Works) -> service discovery -> report subscription -> notification receipt.
"""

from __future__ import annotations

import asyncio
import logging

from bumble.controller import Controller
from bumble.device import Device, Peer
from bumble.gatt import (
    GATT_HUMAN_INTERFACE_DEVICE_SERVICE,
    GATT_REPORT_CHARACTERISTIC,
    GATT_REPORT_MAP_CHARACTERISTIC,
    GATT_REPORT_REFERENCE_DESCRIPTOR,
    Characteristic,
)
from bumble.hci import Address
from bumble.host import Host
from bumble.link import LocalLink
from bumble.pairing import PairingConfig
from bumble.transport.common import AsyncPipeSink

from . import hid_reports as hr
from .ble_peripheral import HogpPeripheral
from .config import Config

logger = logging.getLogger(__name__)

CENTRAL_ADDRESS = "F0:F1:F2:AA:BB:01"


async def run_selftest(config: Config | None = None, keystore_file: str | None = None) -> dict:
    """On success, returns the contents of the received reports. Raises on failure."""
    config = config or Config()
    link = LocalLink()

    # --- Peripheral (WinUC) ---
    peripheral_controller = Controller("WinUC", link=link)
    peripheral = HogpPeripheral(config, keystore_file)
    device_config = peripheral.make_device_configuration()
    peripheral_device = Device(
        config=device_config,
        host=Host(peripheral_controller, AsyncPipeSink(peripheral_controller)),
    )
    peripheral.attach(peripheral_device)
    await peripheral.start()

    # --- Central (acting as iPad) ---
    central_controller = Controller("iPad", link=link)
    central_device = Device(
        name="FakeiPad",
        address=Address(CENTRAL_ADDRESS, Address.RANDOM_DEVICE_ADDRESS),
        host=Host(central_controller, AsyncPipeSink(central_controller)),
    )
    central_device.pairing_config_factory = lambda _connection: PairingConfig(
        sc=True, mitm=False, bonding=False
    )
    await central_device.power_on()

    connection = await central_device.connect(
        Address(config.address, Address.RANDOM_DEVICE_ADDRESS)
    )
    logger.info("selftest: connection established")
    await connection.pair()
    logger.info("selftest: pairing complete (encrypted=%s)", connection.is_encrypted)

    peer = Peer(connection)
    await peer.discover_services()
    hid_services = peer.get_services_by_uuid(GATT_HUMAN_INTERFACE_DEVICE_SERVICE)
    assert hid_services, "HID service not found"
    await peer.discover_characteristics()

    report_map = await peer.read_value(
        peer.get_characteristics_by_uuid(GATT_REPORT_MAP_CHARACTERISTIC)[0]
    )
    assert bytes(report_map) == hr.REPORT_MAP, "Report Map does not match"
    logger.info("selftest: Report Map read OK (%d bytes)", len(report_map))

    # Identify input reports by their Report Reference (ID, type=input) and subscribe
    received: dict[int, list[bytes]] = {1: [], 2: [], 3: []}
    subscribed = 0
    for characteristic in peer.get_characteristics_by_uuid(GATT_REPORT_CHARACTERISTIC):
        if not (characteristic.properties & Characteristic.Properties.NOTIFY):
            continue
        await peer.discover_descriptors(characteristic)
        ref_descriptor = characteristic.get_descriptor(GATT_REPORT_REFERENCE_DESCRIPTOR)
        assert ref_descriptor is not None
        ref = bytes(await peer.read_value(ref_descriptor))
        report_id = ref[0]

        def on_notification(value, report_id=report_id):
            received[report_id].append(bytes(value))

        await peer.subscribe(characteristic, on_notification)
        subscribed += 1
    assert subscribed == 3, f"expected 3 input reports (got {subscribed})"

    # Wait a bit for the subscription events to reach the peripheral side
    await asyncio.sleep(0.1)
    assert peripheral.ready, "peripheral did not become ready"

    # --- Send input ---
    await peripheral.send_mouse(buttons=1, dx=10, dy=-5, wheel=1)
    await peripheral.send_keyboard(0x08, (0x04,))  # Cmd+A
    await peripheral.send_keyboard(0, ())
    await peripheral.send_consumer(0x00E9)  # Volume Up
    await peripheral.send_consumer(0)
    await asyncio.sleep(0.2)

    assert received[3], "no mouse report received"
    assert received[3][0] == hr.mouse_report(1, 10, -5, 1, 0)
    assert received[1][0] == hr.keyboard_report(0x08, (0x04,))
    assert received[1][1] == hr.keyboard_report(0, ())
    assert received[2][0] == hr.consumer_report(0x00E9)

    logger.info("selftest: all notifications verified ✓")
    return {k: [v.hex() for v in vs] for k, vs in received.items()}
