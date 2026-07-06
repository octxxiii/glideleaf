"""仮想コントローラ (LocalLink) 上での BLE 統合テスト。

実機ドングル・iPad なしで、ペアリング → サービス発見 → 購読 → 通知受信
の全経路を検証する。
"""

import pytest

from winuc.config import Config
from winuc.selftest import run_selftest


@pytest.mark.asyncio
async def test_hogp_end_to_end(tmp_path):
    received = await run_selftest(
        Config(), keystore_file=str(tmp_path / "keys.json")
    )
    # mouse: buttons=1, dx=10, dy=-5, wheel=1
    assert received[3][0] == "010a00fbff0100"
    # keyboard: Cmd+A → release
    assert received[1][0] == "0800040000000000"
    assert received[1][1] == "0000000000000000"
    # consumer: VolUp → release
    assert received[2][0] == "e900"
    assert received[2][1] == "0000"
