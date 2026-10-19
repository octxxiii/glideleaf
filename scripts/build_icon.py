"""Build executable and README icons from the generated Glideleaf mark."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from winuc.gui.icons import make_icon

root = Path(__file__).resolve().parents[1]
make_icon(None, 256).save(root / 'packaging' / 'winuc.ico', format='ICO',
                               sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                      (64, 64), (128, 128), (256, 256)])
make_icon(None, 256).save(root / 'docs' / 'images' / 'glideleaf-icon.png')
