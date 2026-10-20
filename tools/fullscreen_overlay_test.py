"""Verify the overlay is above a borderless fullscreen window (manual test)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from app.models import DisplayConfig
from app.overlay import HeartOverlay
from app.theme import apply_theme


class Fullscreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("background: #17324A; color: white;")
        layout = QVBoxLayout(self)
        label = QLabel("BORDERLESS FULLSCREEN TEST")
        label.setAlignment(Qt.AlignCenter)
        label.setFont(QFont("Segoe UI", 32))
        layout.addWidget(label)


def main() -> int:
    app = QApplication(sys.argv[:1])
    apply_theme(app)
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        print("no screen")
        return 1
    print("screen", screen.geometry(), "dpr", screen.devicePixelRatio())
    full = Fullscreen()
    full.showFullScreen()
    full.raise_()
    full.activateWindow()
    QTest.qWait(500)
    overlay = HeartOverlay(
        "FULLSCREEN",
        "Test Band",
        DisplayConfig(template="❤{bpm}", font_size=72, letter_spacing=4),
        bpm=88,
        connected=True,
        position=QPoint(300, 320),
        topmost_enhance=True,
        topmost_interval_ms=500,
    )
    overlay.show()
    print("overlay geom", overlay.geometry())

    def capture() -> None:
        path = Path("screenshots/fullscreen_overlay.png")
        pix = screen.grabWindow(0)
        pix.save(str(path))
        print("saved", path, pix.size())
        overlay.close()
        full.close()
        QTimer.singleShot(400, app.quit)

    QTimer.singleShot(1800, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
