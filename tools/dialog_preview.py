"""Render the dialogs for visual inspection (development helper)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.ble_service import DemoBleService
from app.dialogs import DisplaySettingsDialog
from app.dialogs_device import DeviceSelectionDialog
from app.dialogs_settings import SettingsDialog
from app.history_store import HistoryStore
from app.models import DisplayConfig
from app.storage import ConfigStore, setup_paths
from app.theme import app_icon, apply_theme


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(app_icon())
    apply_theme(app)
    paths = setup_paths(demo=True)
    store = ConfigStore(paths)
    service = DemoBleService()
    service.start()
    out = Path("screenshots/dialogs")
    out.mkdir(parents=True, exist_ok=True)

    device_dialog = DeviceSelectionDialog(None, service, store, set())
    device_dialog.show()
    QTimer.singleShot(2400, lambda: device_dialog.grab().save(str(out / "device_dialog.png")))

    def open_style() -> None:
        style = DisplaySettingsDialog(
            None,
            DisplayConfig(),
            "Mi Band 8",
            lambda cfg: None,
            sample_bpm=78,
            sample_connected=True,
        )
        style.show()
        QTimer.singleShot(700, lambda: style.grab().save(str(out / "style_dialog.png")))
        QTimer.singleShot(1200, style.close)

    QTimer.singleShot(2800, open_style)

    def open_settings() -> None:
        settings = SettingsDialog(
            None,
            store,
            paths,
            lambda: None,
            lambda: None,
        )
        settings.show()
        QTimer.singleShot(500, lambda: settings.grab().save(str(out / "settings_dialog.png")))
        QTimer.singleShot(900, settings.close)

    QTimer.singleShot(4300, open_settings)
    QTimer.singleShot(5800, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
