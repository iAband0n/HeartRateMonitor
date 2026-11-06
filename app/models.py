"""Data models and defaults for HeartRateOverlay.

Everything persisted to disk is represented by a small dataclass.  The
``from_dict`` helpers are deliberately forgiving: users may edit config.json
by hand and an upgrade must never make the application fail to start.
"""

from __future__ import annotations

import dataclasses
import re
import time
from dataclasses import dataclass, field
from typing import Any

APP_NAME = "HeartRateOverlay"
APP_DISPLAY_NAME = "心率悬浮窗"
APP_VERSION = "1.1.0"
CONFIG_VERSION = 1

DEFAULT_TEMPLATE = "❤{bpm}"
DEFAULT_FONT = "Segoe UI"

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clamp(value: Any, low: int | float, high: int | float, fallback: int | float) -> int | float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def _bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def _color(value: Any, fallback: str) -> str:
    if isinstance(value, str) and COLOR_RE.match(value.strip()):
        return value.strip().upper()
    return fallback


def _text(value: Any, fallback: str, max_len: int = 200) -> str:
    if not isinstance(value, str):
        return fallback
    value = value.replace("\x00", "").strip("\r\n")
    return value[:max_len]


@dataclass
class DisplayConfig:
    """Visual configuration for one floating window (or the defaults)."""

    template: str = DEFAULT_TEMPLATE
    heart_text: str = "❤"
    font_family: str = DEFAULT_FONT
    font_size: int = 56
    bold: bool = True
    italic: bool = False
    letter_spacing: float = 2.0
    heart_color: str = "#FF3B5C"
    number_color: str = "#FFFFFF"
    text_color: str = "#FFFFFF"
    background_color: str = "#0B0F16"
    background_opacity: int = 0
    outline_color: str = "#000000"
    outline_width: int = 0
    shadow_enabled: bool = True
    shadow_color: str = "#000000"
    shadow_opacity: int = 120
    padding: int = 16
    radius: int = 16
    opacity: float = 1.0
    align: str = "center"
    show_when_disconnected: bool = True

    def normalized(self) -> "DisplayConfig":
        """Return a copy with all values inside safe, renderable bounds."""
        template = _text(self.template, DEFAULT_TEMPLATE, 120)
        if not template:
            template = DEFAULT_TEMPLATE
        align = self.align if self.align in {"left", "center", "right"} else "center"
        return DisplayConfig(
            template=template,
            heart_text=_text(self.heart_text, "❤", 16),
            font_family=_text(self.font_family, DEFAULT_FONT, 80) or DEFAULT_FONT,
            font_size=int(_clamp(self.font_size, 12, 220, 56)),
            bold=_bool(self.bold, True),
            italic=_bool(self.italic, False),
            letter_spacing=float(_clamp(self.letter_spacing, -4, 40, 2.0)),
            heart_color=_color(self.heart_color, "#FF3B5C"),
            number_color=_color(self.number_color, "#FFFFFF"),
            text_color=_color(self.text_color, "#FFFFFF"),
            background_color=_color(self.background_color, "#0B0F16"),
            background_opacity=int(_clamp(self.background_opacity, 0, 255, 0)),
            outline_color=_color(self.outline_color, "#000000"),
            outline_width=int(_clamp(self.outline_width, 0, 8, 0)),
            shadow_enabled=_bool(self.shadow_enabled, True),
            shadow_color=_color(self.shadow_color, "#000000"),
            shadow_opacity=int(_clamp(self.shadow_opacity, 0, 255, 120)),
            padding=int(_clamp(self.padding, 0, 80, 16)),
            radius=int(_clamp(self.radius, 0, 80, 16)),
            opacity=float(_clamp(self.opacity, 0.15, 1.0, 1.0)),
            align=align,
            show_when_disconnected=_bool(self.show_when_disconnected, True),
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self.normalized())

    @classmethod
    def from_dict(cls, data: Any) -> "DisplayConfig":
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in dataclasses.fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        try:
            return cls(**values).normalized()
        except Exception:
            return cls()


@dataclass
class DeviceProfile:
    """A remembered device.  ``key`` is the stable lookup id (BLE address)."""

    key: str
    address: str = ""
    name: str = ""
    favorite: bool = False
    auto_reconnect: bool = True
    last_connected: float = 0.0
    connect_count: int = 0
    display: DisplayConfig = field(default_factory=DisplayConfig)
    overlay_visible: bool = False
    overlay_locked: bool = False
    overlay_x: int | None = None
    overlay_y: int | None = None
    overlay_width: int | None = None
    overlay_height: int | None = None
    notes: str = ""

    @property
    def display_name(self) -> str:
        return (self.name or "未命名设备").strip()

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["display"] = self.display.to_dict()
        return data

    @classmethod
    def from_dict(cls, key: str, data: Any) -> "DeviceProfile":
        if not isinstance(data, dict):
            data = {}
        address = _text(data.get("address"), "", 80)
        name = _text(data.get("name"), "", 80)
        return cls(
            key=key or address,
            address=address,
            name=name,
            favorite=_bool(data.get("favorite"), False),
            auto_reconnect=_bool(data.get("auto_reconnect"), True),
            last_connected=float(_clamp(data.get("last_connected"), 0, 10**12, 0)),
            connect_count=int(_clamp(data.get("connect_count"), 0, 10**9, 0)),
            display=DisplayConfig.from_dict(data.get("display")),
            overlay_visible=_bool(data.get("overlay_visible"), False),
            overlay_locked=_bool(data.get("overlay_locked"), False),
            overlay_x=_optional_int(data.get("overlay_x")),
            overlay_y=_optional_int(data.get("overlay_y")),
            overlay_width=_optional_int(data.get("overlay_width")),
            overlay_height=_optional_int(data.get("overlay_height")),
            notes=_text(data.get("notes"), "", 300),
        )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


@dataclass
class AppConfig:
    version: int = CONFIG_VERSION
    devices: dict[str, DeviceProfile] = field(default_factory=dict)
    default_display: DisplayConfig = field(default_factory=DisplayConfig)
    auto_reconnect_favorites: bool = False
    close_to_tray: bool = True
    topmost_enhance: bool = True
    topmost_interval_ms: int = 1200
    hotkeys_enabled: bool = True
    history_retention_days: int = 30
    window_geometry: str = ""
    selected_key: str = ""
    multi_view: bool = True
    disconnected_expanded: bool = True
    first_run: bool = True
    last_scan: float = 0.0
    last_version: str = APP_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": CONFIG_VERSION,
            "devices": {key: profile.to_dict() for key, profile in self.devices.items()},
            "default_display": self.default_display.to_dict(),
            "auto_reconnect_favorites": bool(self.auto_reconnect_favorites),
            "close_to_tray": bool(self.close_to_tray),
            "topmost_enhance": bool(self.topmost_enhance),
            "topmost_interval_ms": int(_clamp(self.topmost_interval_ms, 300, 5000, 1200)),
            "hotkeys_enabled": bool(self.hotkeys_enabled),
            "history_retention_days": int(_clamp(self.history_retention_days, 1, 3650, 30)),
            "window_geometry": _text(self.window_geometry, "", 80),
            "selected_key": _text(self.selected_key, "", 80),
            "multi_view": bool(self.multi_view),
            "disconnected_expanded": bool(self.disconnected_expanded),
            "first_run": bool(self.first_run),
            "last_scan": float(self.last_scan or 0),
            "last_version": APP_VERSION,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "AppConfig":
        if not isinstance(data, dict):
            return cls()
        devices: dict[str, DeviceProfile] = {}
        raw_devices = data.get("devices")
        if isinstance(raw_devices, dict):
            for key, value in raw_devices.items():
                if not isinstance(key, str) or not key:
                    continue
                profile = DeviceProfile.from_dict(key, value)
                if profile.address or profile.name:
                    devices[key] = profile
        return cls(
            devices=devices,
            default_display=DisplayConfig.from_dict(data.get("default_display")),
            auto_reconnect_favorites=_bool(data.get("auto_reconnect_favorites"), False),
            close_to_tray=_bool(data.get("close_to_tray"), True),
            topmost_enhance=_bool(data.get("topmost_enhance"), True),
            topmost_interval_ms=int(_clamp(data.get("topmost_interval_ms"), 300, 5000, 1200)),
            hotkeys_enabled=_bool(data.get("hotkeys_enabled"), True),
            history_retention_days=int(_clamp(data.get("history_retention_days"), 1, 3650, 30)),
            window_geometry=_text(data.get("window_geometry"), "", 80),
            selected_key=_text(data.get("selected_key"), "", 80),
            multi_view=_bool(data.get("multi_view"), True),
            disconnected_expanded=_bool(data.get("disconnected_expanded"), True),
            first_run=_bool(data.get("first_run"), True),
            last_scan=float(_clamp(data.get("last_scan"), 0, 10**12, 0)),
            last_version=_text(data.get("last_version"), "", 30),
        )


def make_device_key(address: str, name: str = "") -> str:
    """Stable key for a BLE device.

    On Windows ``BleakScanner`` gives us a MAC-like address which is stable
    for public-address wearables.  Some devices expose a random address; in
    that case the caller can still use the same key while the app is running
    and the saved profile keeps the last known name.
    """
    address = (address or "").strip()
    if address:
        return address.upper()
    name = (name or "").strip()
    return f"name:{name}" if name else f"unknown:{int(time.time())}"


def pretty_address(address: str) -> str:
    if not address:
        return "—"
    return address.upper()


def format_ago(timestamp: float) -> str:
    if not timestamp:
        return "从未连接"
    delta = max(0, time.time() - timestamp)
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return f"{int(delta // 60)} 分钟前"
    if delta < 86400:
        return f"{int(delta // 3600)} 小时前"
    if delta < 86400 * 30:
        return f"{int(delta // 86400)} 天前"
    return time.strftime("%Y-%m-%d", time.localtime(timestamp))
