from PIL import Image
from pathlib import Path

from winuc.gui.icons import make_icon


def test_generated_icon_and_tray_states():
    for size in (16, 32, 64, 256):
        mark = make_icon(None, size)
        assert mark.size == (size, size)
        assert mark.mode == "RGBA"
        assert mark.getpixel((0, 0))[3] <= 5
        assert make_icon("ready", size).tobytes() != make_icon("error", size).tobytes()

    with Image.open(Path(__file__).resolve().parents[1] / "packaging" / "winuc.ico") as exe_icon:
        assert {(16, 16), (32, 32), (256, 256)} <= exe_icon.info["sizes"]
