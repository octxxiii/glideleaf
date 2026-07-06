from winuc import hid_reports as hr


def test_report_map_wellformed():
    # 簡易 HID ディスクリプタパーサ: アイテム長を辿って過不足なく終端すること
    data = hr.REPORT_MAP
    i = 0
    collections = 0
    while i < len(data):
        prefix = data[i]
        size = prefix & 0x03
        size = 4 if size == 3 else size
        tag = prefix & 0xFC
        if tag == 0xA0:  # Collection
            collections += 1
        elif tag == 0xC0:  # End Collection
            collections -= 1
        i += 1 + size
    assert i == len(data)
    assert collections == 0


def test_report_map_contains_three_report_ids():
    ids = set()
    data = hr.REPORT_MAP
    i = 0
    while i < len(data):
        prefix = data[i]
        size = prefix & 0x03
        size = 4 if size == 3 else size
        if (prefix & 0xFC) == 0x84 and size == 1:  # Report ID
            ids.add(data[i + 1])
        i += 1 + size
    assert ids == {1, 2, 3}


def test_mouse_report_packing():
    assert hr.mouse_report(0x01, 10, -5, 1, -1) == bytes(
        [0x01, 10, 0, 0xFB, 0xFF, 1, 0xFF]
    )
    assert len(hr.mouse_report(0, 0, 0)) == hr.MOUSE_REPORT_SIZE


def test_mouse_report_clamps():
    report = hr.mouse_report(0xFF, 999999, -999999, 300, -300)
    assert report[0] == 0x1F  # 5ビットのみ
    import struct

    _, dx, dy, wheel, hwheel = struct.unpack("<Bhhbb", report)
    assert (dx, dy, wheel, hwheel) == (32767, -32767, 127, -127)


def test_keyboard_report():
    assert hr.keyboard_report(0x08, (0x04,)) == bytes([8, 0, 4, 0, 0, 0, 0, 0])
    assert hr.keyboard_report(0) == bytes(8)
    assert len(hr.keyboard_report(0, tuple(range(1, 10)))) == 8


def test_consumer_report():
    assert hr.consumer_report(0x00E9) == bytes([0xE9, 0x00])
    assert hr.consumer_report(0x029D) == bytes([0x9D, 0x02])
    assert hr.consumer_report(0) == bytes([0, 0])
