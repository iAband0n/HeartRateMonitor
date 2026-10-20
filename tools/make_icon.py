"""Generate the application .png from the vector icon painter."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QGuiApplication

from app.theme import draw_app_icon

app = QGuiApplication(sys.argv[:1])
pix = draw_app_icon(512)
out = Path("assets/heart.png")
pix.save(str(out), "PNG")
print(out, pix.size())
