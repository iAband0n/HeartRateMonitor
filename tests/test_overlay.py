"""Overlay window integration test: topmost, drag, resize, controls, click-through."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import win32_utils
from app.models import DisplayConfig
from app.overlay import HeartOverlay
from app.theme import apply_theme


class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self) -> None:
        self.overlay = HeartOverlay(
            "TEST:KEY",
            "Test Band",
            DisplayConfig(template="❤{bpm}", font_size=48),
            bpm=88,
            connected=True,
            position=QPoint(180, 180),
            topmost_enhance=True,
            topmost_interval_ms=500,
        )
        self.positions: list[tuple[str, int, int]] = []
        self.locks: list[tuple[str, bool]] = []
        self.sizes: list[tuple[str, int, int]] = []
        self.overlay.position_changed.connect(lambda *args: self.positions.append(args))
        self.overlay.lock_changed.connect(lambda *args: self.locks.append(args))
        self.overlay.size_changed.connect(lambda *args: self.sizes.append(args))
        self.overlay.show()
        QTest.qWait(300)

    def tearDown(self) -> None:
        self.overlay.close()
        self.overlay.deleteLater()
        QTest.qWait(100)

    def _mouse(self, event_type, local: QPointF, global_pos: QPointF, button, buttons) -> QMouseEvent:
        return QMouseEvent(
            event_type,
            local,
            global_pos,
            button,
            buttons,
            Qt.NoModifier,
        )

    def test_topmost_and_click_through(self) -> None:
        hwnd = win32_utils.hwnd_of(self.overlay)
        self.assertTrue(hwnd)
        self.assertTrue(win32_utils.get_ex_style(hwnd) & win32_utils.WS_EX_TOPMOST)
        self.assertFalse(win32_utils.is_click_through(hwnd))
        self.assertTrue(self.overlay.controls.isVisible())
        self.overlay.set_locked(True)
        QTest.qWait(100)
        self.assertTrue(win32_utils.is_click_through(hwnd))
        self.assertTrue(win32_utils.get_ex_style(hwnd) & win32_utils.WS_EX_TOPMOST)
        self.assertEqual(self.locks[-1], ("TEST:KEY", True))
        self.assertFalse(self.overlay.controls.isVisible())
        self.overlay.set_locked(False)
        QTest.qWait(100)
        self.assertFalse(win32_utils.is_click_through(hwnd))
        self.assertEqual(self.locks[-1], ("TEST:KEY", False))
        self.assertTrue(self.overlay.controls.isVisible())

    def test_drag_moves_window(self) -> None:
        start = self.overlay.pos()
        local = QPointF(self.overlay.width() / 2, 20)
        press_global = QPointF(start.x() + local.x(), start.y() + local.y())
        press = self._mouse(
            QEvent.MouseButtonPress, local, press_global, Qt.LeftButton, Qt.LeftButton
        )
        self.overlay.mousePressEvent(press)
        move_global = QPointF(press_global.x() + 55, press_global.y() + 35)
        move = self._mouse(
            QEvent.MouseMove,
            QPointF(local.x() + 55, local.y() + 35),
            move_global,
            Qt.NoButton,
            Qt.LeftButton,
        )
        self.overlay.mouseMoveEvent(move)
        release = self._mouse(
            QEvent.MouseButtonRelease,
            QPointF(local.x() + 55, local.y() + 35),
            move_global,
            Qt.LeftButton,
            Qt.NoButton,
        )
        self.overlay.mouseReleaseEvent(release)
        self.assertEqual(self.overlay.pos(), start + QPoint(55, 35))
        QTest.qWait(700)
        self.assertTrue(self.positions)
        self.assertEqual(self.positions[-1], ("TEST:KEY", start.x() + 55, start.y() + 35))

    def test_corner_resize(self) -> None:
        start_size = self.overlay.size()
        point = self.overlay._handle_points()["br"]
        local = QPointF(point.x(), point.y())
        press_global = QPointF(self.overlay.x() + local.x(), self.overlay.y() + local.y())
        press = self._mouse(
            QEvent.MouseButtonPress, local, press_global, Qt.LeftButton, Qt.LeftButton
        )
        self.overlay.mousePressEvent(press)
        move_global = QPointF(press_global.x() + 60, press_global.y() + 40)
        move = self._mouse(
            QEvent.MouseMove,
            QPointF(local.x() + 60, local.y() + 40),
            move_global,
            Qt.NoButton,
            Qt.LeftButton,
        )
        self.overlay.mouseMoveEvent(move)
        release = self._mouse(
            QEvent.MouseButtonRelease,
            QPointF(local.x() + 60, local.y() + 40),
            move_global,
            Qt.LeftButton,
            Qt.NoButton,
        )
        self.overlay.mouseReleaseEvent(release)
        self.assertGreater(self.overlay.width(), start_size.width())
        self.assertGreater(self.overlay.height(), start_size.height())
        self.assertIsNotNone(self.overlay.custom_size)
        self.assertTrue(self.sizes)
        self.assertEqual(self.sizes[-1][0], "TEST:KEY")
        self.overlay.reset_size()
        self.assertIsNone(self.overlay.custom_size)
        self.assertEqual(self.sizes[-1], ("TEST:KEY", 0, 0))

    def test_controls_hide(self) -> None:
        self.assertTrue(self.overlay.controls.isVisible())
        self.overlay.hide_button.click()
        QTest.qWait(50)
        self.assertFalse(self.overlay.isVisible())

    def test_size_tracks_bpm_digits(self) -> None:
        narrow = self.overlay.width()
        self.overlay.set_data(188, True)
        QTest.qWait(50)
        self.assertGreaterEqual(self.overlay.width(), narrow)
        self.assertGreater(self.overlay.height(), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
