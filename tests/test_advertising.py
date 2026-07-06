"""実機コントローラで拒否されないよう、アドバタイジングの 31 バイト制限を守る。"""

from winuc.ble_peripheral import HogpPeripheral
from winuc.config import Config


def test_advertising_data_fits_legacy_limit():
    peripheral = HogpPeripheral(Config())
    assert len(peripheral._advertising_data()) <= 31
    assert len(peripheral._scan_response_data()) <= 31


def test_long_device_name_is_truncated():
    config = Config(device_name="と" * 40)  # マルチバイトの超長名
    peripheral = HogpPeripheral(config)
    assert len(peripheral._scan_response_data()) <= 31
