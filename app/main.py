"""Application entry point.

Run from source:      python -m app.main
Demo / screenshots:  python -m app.main --demo --screenshot screenshots
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QIODevice, QTimer, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from . import win32_utils
from .ble_service import create_ble_service
from .history_store import HistoryStore
from .logging_setup import install_exception_hooks, setup_logging
from .main_window import MainWindow
from .models import APP_DISPLAY_NAME, APP_VERSION
from .storage import ConfigStore, setup_paths
from .theme import app_icon, apply_theme

log = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_DISPLAY_NAME)
    parser.add_argument("--demo", action="store_true", help="使用模拟设备（无需蓝牙硬件）")
    parser.add_argument("--smoke-test", action="store_true", help="启动后自动退出，用于验证打包")
    parser.add_argument("--screenshot", metavar="DIR", help="演示模式截图到指定目录后退出")
    parser.add_argument(
        "--scan-test",
        nargs="?",
        const=8,
        type=float,
        metavar="SECONDS",
        help="仅扫描 BLE 设备并退出，用于验证蓝牙后端",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    return parser.parse_args(argv)


def _run_scan_test(seconds: float) -> int:
    """Headless-ish BLE scan used to verify frozen builds on real hardware."""
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_DISPLAY_NAME)
    ble = create_ble_service(demo=False)
    ble.scan_started.connect(lambda: log.info("SCAN TEST started"))
    ble.scan_progress.connect(
        lambda info: log.info(
            "SCAN TEST device %s %s rssi=%s hr=%s",
            info.address,
            info.name,
            info.rssi,
            info.has_heart_rate,
        )
    )
    ble.scan_error.connect(lambda message: log.error("SCAN TEST error: %s", message))
    ble.scan_finished.connect(
        lambda devices: log.info("SCAN TEST finished: %d device(s)", len(devices))
    )
    ble.start()
    ble.scan(max(3.0, seconds))
    QTimer.singleShot(int((max(3.0, seconds) + 3.0) * 1000), app.quit)
    code = app.exec()
    ble.shutdown()
    log.info("SCAN TEST exit %s", code)
    return code


def _instance_name() -> str:
    user = getpass.getuser() or "user"
    digest = hashlib.md5(user.encode("utf-8", "ignore")).hexdigest()[:10]
    return f"HeartRateOverlay-{digest}"


def _notify_existing_instance(name: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(name, QIODevice.WriteOnly)
    if not socket.waitForConnected(250):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(250)
    socket.disconnectFromServer()
    return True


def _start_instance_server(app: QApplication, window: MainWindow) -> QLocalServer | None:
    name = _instance_name()
    server = QLocalServer(app)
    QLocalServer.removeServer(name)
    if not server.listen(name):
        log.warning("Could not start single-instance server: %s", server.errorString())
        return None

    def on_new_connection() -> None:
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            if socket is None:
                continue
            socket.waitForReadyRead(150)
            data = bytes(socket.readAll())
            socket.disconnectFromServer()
            if data in {b"show", b""}:
                window._show_from_tray()

    server.newConnection.connect(on_new_connection)
    return server


def _capture_screenshots(window: MainWindow, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    window.showNormal()
    window.raise_()
    window.activateWindow()
    if window._selected_key and window._selected_key not in window._overlays:
        window._open_overlay(window._selected_key)

    def capture() -> None:
        try:
            main_path = directory / "main_window.png"
            window.grab().save(str(main_path), "PNG")
            log.info("Saved screenshot %s", main_path)
            for index, (key, overlay) in enumerate(window._overlays.items()):
                overlay_path = directory / f"overlay_{index + 1}.png"
                overlay.grab().save(str(overlay_path), "PNG")
                log.info("Saved screenshot %s", overlay_path)
        finally:
            window.quit_application()

    QTimer.singleShot(1800, capture)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    demo = bool(args.demo or args.screenshot)
    paths = setup_paths(demo=demo)
    setup_logging(paths.log_file, console=not getattr(sys, "frozen", False))
    install_exception_hooks()
    log.info("Starting %s %s (demo=%s, frozen=%s)", APP_DISPLAY_NAME, APP_VERSION, demo, getattr(sys, "frozen", False))

    win32_utils.set_app_user_model_id("W.HeartRateOverlay.1")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    if args.scan_test is not None:
        return _run_scan_test(float(args.scan_test))
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("W's Thing")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)

    if not demo and not args.smoke_test:
        if _notify_existing_instance(_instance_name()):
            log.info("Another instance is already running; asked it to show.")
            return 0

    config_store = ConfigStore(paths)
    history = HistoryStore(paths.history_file)
    ble = create_ble_service(demo=demo)
    ble.start()
    window = MainWindow(ble, config_store, history, paths, demo=demo)
    window.show()

    server = None
    if not demo and not args.smoke_test:
        server = _start_instance_server(app, window)
        app._instance_server = server  # type: ignore[attr-defined]

    if args.screenshot:
        _capture_screenshots(window, Path(args.screenshot))
    elif args.smoke_test:
        QTimer.singleShot(3500, window.quit_application)
        QTimer.singleShot(3800, lambda: app.exit(0))

    code = app.exec()
    if server is not None:
        server.close()
    log.info("Exit code %s", code)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
