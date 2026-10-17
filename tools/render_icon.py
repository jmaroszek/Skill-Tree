"""Render assets/skill_tree_logo.svg into the app icons: electron/build/icon.png
and assets/skill_tree.ico. Needs PySide6 and Pillow, which the app does not.

Run from the repository root: `python tools/render_icon.py`.
"""
from pathlib import Path
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image
app = QGuiApplication([])
root = Path.cwd()
renderer = QSvgRenderer(str(root / 'assets/skill_tree_logo.svg'))
assert renderer.isValid()
image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
image.fill(0)
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
renderer.render(painter)
painter.end()
png = root / 'electron/build/icon.png'
assert image.save(str(png))
with Image.open(png) as im:
    im.save(root / 'assets/skill_tree.ico', sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    print('PNG:', im.size, 'background:', im.getpixel((512, 80)))
with Image.open(root / 'assets/skill_tree.ico') as im:
    print('ICO sizes:', sorted(im.ico.sizes()))
