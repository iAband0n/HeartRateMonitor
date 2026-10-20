"""Config, history and log locations + atomic JSON persistence."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

from .models import APP_NAME, AppConfig

log = logging.getLogger(__name__)


def app_data_dir() -> Path:
    # Explicit override is useful for portable installs and automated tests.
    override = os.environ.get("HEART_RATE_OVERLAY_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    base = os.environ.get("APPDATA")
    if base:
        root = Path(base)
    else:  # pragma: no cover - Windows always has APPDATA
        root = Path.home() / "AppData" / "Roaming"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """Locate bundled resources both in source runs and PyInstaller builds."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative


class AppPaths:
    def __init__(self, demo: bool = False) -> None:
        self.demo = demo
        self.data_dir = app_data_dir()
        prefix = "demo_" if demo else ""
        self.config_file = self.data_dir / f"{prefix}config.json"
        self.history_file = self.data_dir / f"{prefix}history.sqlite3"
        self.log_file = self.data_dir / ("demo_app.log" if demo else "app.log")
        self.lock_file = self.data_dir / "instance.lock"


class ConfigStore:
    """Loads/saves config.json atomically and keeps a backup on corruption."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.config = self.load()
        self._last_saved: float = 0.0

    def load(self) -> AppConfig:
        path = self.paths.config_file
        if not path.exists():
            return AppConfig()
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
            config = AppConfig.from_dict(data)
            log.info("Loaded config with %d device(s) from %s", len(config.devices), path)
            return config
        except Exception:
            log.exception("Could not read config %s; using defaults", path)
            try:
                backup = path.with_suffix(path.suffix + f".broken-{int(time.time())}")
                shutil.copy2(path, backup)
            except Exception:
                pass
            return AppConfig()

    def save(self) -> bool:
        path = self.paths.config_file
        tmp = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = self.config.to_dict()
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
            self._last_saved = time.time()
            return True
        except Exception:
            log.exception("Could not save config to %s", path)
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return False


def setup_paths(demo: bool = False) -> AppPaths:
    return AppPaths(demo=demo)
