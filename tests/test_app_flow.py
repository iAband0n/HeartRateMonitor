"""End-to-end UI flow in demo mode (no BLE hardware required)."""

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import win32_utils
from app.ble_service import DemoBleService
from app.history_store import HistoryStore
from app.main_window import MainWindow
from app.storage import AppPaths, ConfigStore
from app.theme import apply_theme


class AppFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def test_connect_open_lock_hide(self) -> None:
        base = ROOT / ".localdata" / "flow"
        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True)
        os.environ["HEART_RATE_OVERLAY_DATA_DIR"] = str(base)
        paths = AppPaths(demo=True)
        paths.data_dir = base
        paths.config_file = base / "config.json"
        paths.history_file = base / "history.sqlite3"
        paths.log_file = base / "app.log"
        store = ConfigStore(paths)
        history = HistoryStore(paths.history_file)
        service = DemoBleService()
        service.start()
        window = MainWindow(service, store, history, paths, demo=True)
        window.show()
        QTest.qWait(2600)
        self.assertEqual(len(window._sessions), 2)
        self.assertTrue(all(session.connected for session in window._sessions.values()))
        self.assertTrue(window._multi_view)
        self.assertEqual(window.right_stack.currentIndex(), 2)
        self.assertEqual(len(window._multi_cards), 2)
        first_key = next(iter(window._sessions))
        first_card = window._multi_cards[first_key]
        self.assertNotEqual(first_card.stat_values["最低"].text(), "—")
        self.assertGreater(len(first_card.history_chart._points), 0)
        self.assertIsNotNone(window.multi_range_combo)
        window._set_multi_view(False)
        QTest.qWait(100)
        self.assertEqual(window.right_stack.currentIndex(), 1)
        window.resize(1100, 660)
        QTest.qWait(100)
        detail_page = window.detail_scroll_area.widget()
        self.assertGreater(
            detail_page.height(), window.detail_scroll_area.viewport().height()
        )
        curve_bottom = window.live_chart.mapTo(
            detail_page, window.live_chart.rect().bottomLeft()
        ).y()
        stats_top = window.stat_min.mapTo(detail_page, window.stat_min.rect().topLeft()).y()
        self.assertLess(curve_bottom, stats_top)
        window._set_multi_view(True)
        QTest.qWait(100)
        self.assertEqual(window.right_stack.currentIndex(), 2)
        window._toggle_overlay(first_key)
        QTest.qWait(300)
        overlay = window._overlays[first_key]
        self.assertTrue(overlay.isVisible())
        self.assertFalse(overlay.locked)
        window._toggle_lock(first_key)
        QTest.qWait(250)
        self.assertTrue(overlay.locked)
        hwnd = win32_utils.hwnd_of(overlay)
        self.assertTrue(win32_utils.is_click_through(hwnd))
        window._toggle_overlay(first_key)
        QTest.qWait(150)
        self.assertFalse(overlay.isVisible())
        window._toggle_overlay(first_key)
        QTest.qWait(150)
        self.assertTrue(overlay.isVisible())

        disconnected_key = next(iter(window._sessions))
        window._disconnect_key(disconnected_key)
        QTest.qWait(400)
        self.assertIsNotNone(window.disconnected_toggle)
        self.assertEqual(window.config.disconnected_expanded, True)
        self.assertTrue(window.disconnected_panel.isVisible())
        window.disconnected_toggle.click()
        QTest.qWait(100)
        self.assertFalse(window.disconnected_panel.isVisible())
        self.assertFalse(window.config.disconnected_expanded)

        window.quit_application()
        QTest.qWait(300)
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
