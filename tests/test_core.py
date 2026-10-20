"""Core unit tests (no GUI required except Qt font metrics)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from app.ble_service import parse_heart_rate  # noqa: E402
from app.history_store import HistoryStore  # noqa: E402
from app.models import (  # noqa: E402
    AppConfig,
    DeviceProfile,
    DisplayConfig,
    make_device_key,
)
from app.render import build_layout  # noqa: E402


class HeartRateParserTests(unittest.TestCase):
    def test_uint8(self) -> None:
        bpm, contact, rr = parse_heart_rate(bytes([0x00, 72]))
        self.assertEqual((bpm, contact, rr), (72, 0, None))

    def test_uint16(self) -> None:
        bpm, contact, rr = parse_heart_rate(bytes([0x01, 0x2C, 0x01]))
        self.assertEqual(bpm, 300)

    def test_contact_and_rr(self) -> None:
        data = bytes([0x00 | (2 << 1) | 0x10, 80, 0x00, 0x04])
        bpm, contact, rr = parse_heart_rate(data)
        self.assertEqual(bpm, 80)
        self.assertEqual(contact, 2)
        self.assertEqual(rr, 1024)

    def test_empty(self) -> None:
        with self.assertRaises(ValueError):
            parse_heart_rate(b"")


class ConfigModelTests(unittest.TestCase):
    def test_display_normalized(self) -> None:
        cfg = DisplayConfig.from_dict(
            {
                "template": "",
                "font_size": 9999,
                "letter_spacing": -99,
                "heart_color": "not-a-color",
                "background_opacity": 999,
            }
        )
        self.assertTrue(cfg.template)
        self.assertEqual(cfg.font_size, 220)
        self.assertEqual(cfg.letter_spacing, -4)
        self.assertEqual(cfg.heart_color, "#FF3B5C")
        self.assertEqual(cfg.background_opacity, 255)

    def test_config_roundtrip(self) -> None:
        cfg = AppConfig()
        profile = DeviceProfile(
            key="AA:BB:CC:DD:EE:FF",
            address="AA:BB:CC:DD:EE:FF",
            name="Test Band",
            favorite=True,
            last_connected=123.0,
            overlay_x=120,
            overlay_y=80,
        )
        cfg.devices[profile.key] = profile
        clone = AppConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
        self.assertEqual(clone.devices[profile.key].name, "Test Band")
        self.assertTrue(clone.devices[profile.key].favorite)
        self.assertEqual(clone.devices[profile.key].overlay_x, 120)

    def test_key(self) -> None:
        self.assertEqual(make_device_key("aa:bb", "x"), "AA:BB")


class HistoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        base = ROOT / ".localdata" / "tests"
        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True)
        self.path = base / "history.sqlite3"
        self.store = HistoryStore(self.path)

    def tearDown(self) -> None:
        self.store.close()
        shutil.rmtree(self.path.parent, ignore_errors=True)

    def test_add_query_stats(self) -> None:
        now = time.time()
        for index in range(10):
            self.store.add_sample("dev", 70 + index, now - 10 + index)
        points = self.store.points("dev", now - 60, bucket=1)
        self.assertEqual(len(points), 10)
        stats = self.store.stats("dev", now - 60)
        self.assertEqual(stats["min"], 70)
        self.assertEqual(stats["max"], 79)
        self.assertEqual(stats["count"], 10)

    def test_throttle(self) -> None:
        now = time.time()
        self.assertTrue(self.store.add_sample("dev", 70, now))
        self.assertFalse(self.store.add_sample("dev", 71, now + 0.1))
        self.assertTrue(self.store.add_sample("dev", 72, now + 1.0))

    def test_bucket_and_csv(self) -> None:
        now = time.time()
        rows = [("dev", now - 100 + index, 70 + index % 10) for index in range(100)]
        self.store.add_many(rows)
        bucketed = self.store.points("dev", now - 200, bucket=10)
        self.assertLess(len(bucketed), 100)
        out = self.path.parent / "out.csv"
        count = self.store.export_csv("dev", now - 200, str(out))
        self.assertEqual(count, 100)
        self.assertTrue(out.read_text(encoding="utf-8-sig").startswith("时间"))


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_layout_heart_and_number(self) -> None:
        cfg = DisplayConfig(template="❤{bpm}", font_size=60, letter_spacing=3)
        layout = build_layout(cfg, 88, "Test", 90, True)
        self.assertGreater(layout.box_width, 80)
        self.assertGreater(layout.box_height, 60)
        self.assertEqual("".join(g.text for g in layout.glyphs).replace("88", ""), "❤")
        self.assertTrue(any(g.is_heart for g in layout.glyphs))
        self.assertTrue(any(g.color.name().upper() == "#FF3B5C" for g in layout.glyphs))

    def test_tokens_and_disconnected(self) -> None:
        cfg = DisplayConfig(template="{name} {heart} {bpm} {battery}", font_size=40)
        layout = build_layout(cfg, 0, "Band", 77, False)
        text = "".join(g.text for g in layout.glyphs)
        self.assertIn("Band", text)
        self.assertIn("--", text)
        self.assertIn("77%", text)

    def test_letter_spacing_changes_width(self) -> None:
        tight = build_layout(DisplayConfig(template="{bpm}", letter_spacing=0), 88, connected=True)
        loose = build_layout(DisplayConfig(template="{bpm}", letter_spacing=10), 88, connected=True)
        self.assertGreater(loose.box_width, tight.box_width)


if __name__ == "__main__":
    unittest.main(verbosity=2)
