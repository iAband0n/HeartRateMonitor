"""Main application window and all UI wiring."""

from __future__ import annotations

import ctypes.wintypes as wintypes
import dataclasses
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QByteArray, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import win32_utils
from .ble_service import (
    DemoBleService,
    STATE_CONNECTED,
    STATE_CONNECTING,
    STATE_DISCONNECTED,
    STATE_ERROR,
    STATE_RECONNECTING,
)
from .charts import HeartChart, StatTile
from .dialogs import DisplaySettingsDialog
from .dialogs_device import DeviceSelectionDialog
from .dialogs_settings import SettingsDialog
from .history_store import HistoryStore
from .models import (
    APP_DISPLAY_NAME,
    APP_VERSION,
    AppConfig,
    DeviceProfile,
    DisplayConfig,
    format_ago,
    make_device_key,
    pretty_address,
)
from .overlay import HeartOverlay
from .storage import AppPaths, ConfigStore
from .theme import app_icon, draw_app_icon
from .widgets import DeviceCard, EmptyState, MultiDeviceCard

log = logging.getLogger(__name__)

HOTKEY_LOCK = 1
HOTKEY_VISIBILITY = 2


@dataclass
class DeviceSession:
    key: str
    profile: DeviceProfile
    bpm: int = 0
    battery: int | None = None
    state: str = STATE_DISCONNECTED
    message: str = ""
    last_update: float = 0.0
    samples: deque[tuple[float, int]] = field(default_factory=lambda: deque(maxlen=1800))
    rr: int | None = None

    @property
    def connected(self) -> bool:
        return self.state == STATE_CONNECTED


class MainWindow(QMainWindow):
    def __init__(
        self,
        ble,
        config_store: ConfigStore,
        history: HistoryStore,
        paths: AppPaths,
        demo: bool = False,
    ) -> None:
        super().__init__()
        self.ble = ble
        self.config_store = config_store
        self.config: AppConfig = config_store.config
        self.history = history
        self.paths = paths
        self.demo = demo
        self._sessions: dict[str, DeviceSession] = {}
        self._cards: dict[str, DeviceCard] = {}
        self._overlays: dict[str, HeartOverlay] = {}
        self._multi_cards: dict[str, MultiDeviceCard] = {}
        self.disconnected_toggle: QPushButton | None = None
        self.disconnected_panel: QWidget | None = None
        self._multi_view = bool(self.config.multi_view)
        self._selected_key = ""
        self._history_range = 300
        self._force_quit = False
        self._quitting = False
        self._close_hint_shown = False
        self._hotkeys_registered: list[int] = []
        self._last_tray_update = 0.0
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._reset_status)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(450)
        self._save_timer.timeout.connect(self._save_config)

        self.setWindowTitle(f"{APP_DISPLAY_NAME} · HeartRate Overlay")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1020, 660)
        self.resize(1220, 780)
        self._sync_sessions_from_profiles()
        self._restore_geometry()
        self._build_ui()
        self._build_tray()
        self._connect_ble_signals()
        self._refresh_device_list()
        self._choose_initial_selection()
        self._refresh_selected_view()
        self._load_recent_history()

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(1000)
        self._ui_timer.timeout.connect(self._tick)
        self._ui_timer.start()

        if self.config.history_retention_days > 0:
            self.history.prune(self.config.history_retention_days)

        QTimer.singleShot(350, self._restore_overlays)
        QTimer.singleShot(900, self._restore_auto_connect)
        QTimer.singleShot(500, self._register_hotkeys)
        QTimer.singleShot(1200, self._first_run_hint)

        if self.demo:
            self._setup_demo()

        self.show_status("就绪 · 点击右上角「选择设备」开始", "idle")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(10)
        body.addWidget(self._build_left_panel())
        body.addWidget(self._build_right_panel())
        body.setSizes([400, 800])
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        outer.addWidget(body, 1)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        status.setStyleSheet(
            "QStatusBar { background: #0F141D; border-top: 1px solid #1D2532; "
            "color: #8D99AC; font-size: 11px; } "
            "QStatusBar::item { border: none; }"
        )
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #8D99AC; padding-left: 10px;")
        status.addWidget(self.status_label, 1)
        self.data_hint = QLabel(f"v{APP_VERSION}  ·  本地运行  ·  不上传健康数据")
        self.data_hint.setStyleSheet("color: #5E6A7D; padding-right: 12px;")
        status.addPermanentWidget(self.data_hint)
        self.setStatusBar(status)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(84)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 12, 20, 12)
        layout.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(46, 46))
        logo.setFixedSize(46, 46)
        layout.addWidget(logo)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel(APP_DISPLAY_NAME)
        title.setStyleSheet("font-size: 20px; font-weight: 700; letter-spacing: 0.5px;")
        subtitle = QLabel("HeartRate Overlay · 低功耗蓝牙心率 · 多设备同显")
        subtitle.setProperty("role", "muted")
        subtitle.setStyleSheet("font-size: 11px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)

        if self.demo:
            demo_badge = QLabel("演示模式")
            demo_badge.setProperty("role", "chipAccent")
            layout.addWidget(demo_badge, 0, Qt.AlignVCenter)

        layout.addStretch(1)

        self.header_status = QLabel("● 蓝牙待命")
        self.header_status.setStyleSheet("color: #8D99AC; font-size: 11px;")
        layout.addWidget(self.header_status)

        self.overlays_button = QPushButton("全部悬浮窗")
        self.overlays_button.setObjectName("Ghost")
        self.overlays_button.setCursor(Qt.PointingHandCursor)
        overlay_menu = QMenu(self.overlays_button)
        overlay_menu.addAction("显示全部悬浮窗", self._show_all_overlays)
        overlay_menu.addAction("隐藏全部悬浮窗", self._hide_all_overlays)
        overlay_menu.addSeparator()
        overlay_menu.addAction("锁定全部悬浮窗", lambda: self._set_all_locks(True))
        overlay_menu.addAction("解锁全部悬浮窗", lambda: self._set_all_locks(False))
        self.overlays_button.setMenu(overlay_menu)
        layout.addWidget(self.overlays_button)

        self.select_button = QPushButton("＋  选择设备")
        self.select_button.setObjectName("Primary")
        self.select_button.setCursor(Qt.PointingHandCursor)
        self.select_button.clicked.connect(self.open_device_dialog)
        layout.addWidget(self.select_button)

        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setText("⚙")
        self.settings_button.setToolTip("设置")
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.setFixedSize(38, 38)
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)
        return header

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(350)
        panel.setMaximumWidth(470)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 8, 14)
        layout.setSpacing(10)

        heading = QHBoxLayout()
        title = QLabel("我的设备")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        heading.addWidget(title)
        self.device_count = QLabel("0 台")
        self.device_count.setProperty("role", "chip")
        heading.addWidget(self.device_count)
        heading.addStretch(1)
        add_button = QPushButton("＋")
        add_button.setObjectName("Chip")
        add_button.setToolTip("选择设备")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.setFixedWidth(34)
        add_button.clicked.connect(self.open_device_dialog)
        heading.addWidget(add_button)
        layout.addLayout(heading)

        self.left_stack = QStackedWidget()
        empty = EmptyState(
            "还没有设备",
            "点击「选择设备」搜索附近的手环 / 手表\n支持同时连接多个设备",
            "选择设备",
            icon=draw_app_icon(128),
        )
        empty.action_requested.connect(self.open_device_dialog)
        self.left_stack.addWidget(empty)

        self.device_scroll = QScrollArea()
        self.device_scroll.setWidgetResizable(True)
        self.device_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.device_container = QWidget()
        self.device_layout = QVBoxLayout(self.device_container)
        self.device_layout.setContentsMargins(0, 2, 8, 2)
        self.device_layout.setSpacing(9)
        self.device_layout.addStretch(1)
        self.device_scroll.setWidget(self.device_container)
        self.left_stack.addWidget(self.device_scroll)
        layout.addWidget(self.left_stack, 1)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 16, 20, 14)
        layout.setSpacing(0)

        self.view_bar = QWidget()
        view_layout = QHBoxLayout(self.view_bar)
        view_layout.setContentsMargins(0, 0, 0, 8)
        view_layout.setSpacing(6)
        view_label = QLabel("显示方式")
        view_label.setProperty("role", "muted")
        view_layout.addWidget(view_label)
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.single_view_button = QPushButton("单个设备")
        self.multi_view_button = QPushButton("多设备同显")
        for index, button in enumerate((self.single_view_button, self.multi_view_button)):
            button.setObjectName("RangeButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self.view_group.addButton(button, index)
            view_layout.addWidget(button)
        self.single_view_button.setChecked(not self._multi_view)
        self.multi_view_button.setChecked(self._multi_view)
        self.view_group.idClicked.connect(self._on_view_mode_clicked)
        view_layout.addStretch(1)
        self.view_hint = QLabel("")
        self.view_hint.setProperty("role", "dim")
        view_layout.addWidget(self.view_hint)
        self.view_bar.setVisible(False)
        layout.addWidget(self.view_bar)

        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(
            EmptyState(
                "心率将在这里显示",
                "连接设备后，这里会显示实时心率、最近 3 分钟曲线和完整历史记录。\n"
                "把鼠标放到曲线上可以查看具体数值。",
                icon=draw_app_icon(128),
            )
        )
        self.right_stack.addWidget(self._build_detail_page())
        self.right_stack.addWidget(self._build_multi_page())
        layout.addWidget(self.right_stack, 1)
        return panel

    def _build_multi_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("全部设备实时心率")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        header.addWidget(title)
        self.multi_count = QLabel("0 台")
        self.multi_count.setProperty("role", "chip")
        header.addWidget(self.multi_count)
        header.addStretch(1)
        range_caption = QLabel("历史")
        range_caption.setProperty("role", "muted")
        header.addWidget(range_caption)
        self.multi_range_combo = QComboBox()
        self.multi_range_combo.setFixedWidth(98)
        for label, seconds in (
            ("5 分钟", 300),
            ("30 分钟", 1800),
            ("1 小时", 3600),
            ("6 小时", 21600),
            ("24 小时", 86400),
        ):
            self.multi_range_combo.addItem(label, seconds)
        index = self.multi_range_combo.findData(self._history_range)
        self.multi_range_combo.setCurrentIndex(index if index >= 0 else 0)
        self.multi_range_combo.currentIndexChanged.connect(self._on_multi_range_changed)
        header.addWidget(self.multi_range_combo)
        hint = QLabel("每秒刷新")
        hint.setProperty("role", "dim")
        header.addWidget(hint)
        layout.addLayout(header)
        self.multi_scroll = QScrollArea()
        self.multi_scroll.setWidgetResizable(True)
        self.multi_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.multi_container = QWidget()
        self.multi_grid = QGridLayout(self.multi_container)
        self.multi_grid.setContentsMargins(0, 0, 6, 0)
        self.multi_grid.setHorizontalSpacing(10)
        self.multi_grid.setVerticalSpacing(10)
        self.multi_scroll.setWidget(self.multi_container)
        layout.addWidget(self.multi_scroll, 1)
        return page

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        live_card = QFrame()
        live_card.setObjectName("Card")
        live = QVBoxLayout(live_card)
        live.setContentsMargins(18, 14, 18, 14)
        live.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.detail_avatar = QLabel("❤")
        self.detail_avatar.setAlignment(Qt.AlignCenter)
        self.detail_avatar.setFixedSize(42, 42)
        self.detail_avatar.setStyleSheet(
            "background: rgba(255,59,92,0.14); border: 1px solid rgba(255,59,92,0.25);"
            "border-radius: 21px; color: #FF5C77; font-size: 20px;"
        )
        header.addWidget(self.detail_avatar)
        name_box = QVBoxLayout()
        name_box.setSpacing(1)
        self.detail_name = QLabel("—")
        self.detail_name.setStyleSheet("font-size: 17px; font-weight: 700;")
        self.detail_meta = QLabel("—")
        self.detail_meta.setProperty("role", "muted")
        name_box.addWidget(self.detail_name)
        name_box.addWidget(self.detail_meta)
        header.addLayout(name_box, 1)
        self.detail_status = QLabel("● 未连接")
        self.detail_status.setStyleSheet("color: #8D99AC; font-size: 11px;")
        header.addWidget(self.detail_status)
        self.detail_battery = QLabel("")
        self.detail_battery.setProperty("role", "chip")
        header.addWidget(self.detail_battery)
        self.detail_style_button = QPushButton("样式")
        self.detail_style_button.setObjectName("Chip")
        self.detail_style_button.clicked.connect(self._style_selected)
        header.addWidget(self.detail_style_button)
        self.detail_overlay_button = QPushButton("悬浮窗")
        self.detail_overlay_button.setObjectName("Chip")
        self.detail_overlay_button.clicked.connect(self._toggle_selected_overlay)
        header.addWidget(self.detail_overlay_button)
        live.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(14)
        bpm_box = QVBoxLayout()
        bpm_box.setSpacing(0)
        bpm_row = QHBoxLayout()
        bpm_row.setSpacing(4)
        self.big_bpm = QLabel("—")
        self.big_bpm.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 76px; font-weight: 800; color: #EEF2F8;"
        )
        bpm_unit = QLabel("BPM")
        bpm_unit.setProperty("role", "unit")
        bpm_unit.setStyleSheet("font-size: 12px; padding-bottom: 13px;")
        bpm_row.addWidget(self.big_bpm)
        bpm_row.addWidget(bpm_unit, 0, Qt.AlignBottom)
        bpm_box.addLayout(bpm_row)
        self.last_update_label = QLabel("等待心率数据…")
        self.last_update_label.setProperty("role", "muted")
        bpm_box.addWidget(self.last_update_label)
        bpm_box.addStretch(1)
        body.addLayout(bpm_box, 0)

        chart_box = QVBoxLayout()
        chart_box.setSpacing(2)
        chart_title = QLabel("实时心率 · 最近 3 分钟")
        chart_title.setProperty("role", "muted")
        chart_box.addWidget(chart_title)
        self.live_chart = HeartChart()
        self.live_chart.set_empty_text("连接后开始接收心率…")
        chart_box.addWidget(self.live_chart, 1)
        body.addLayout(chart_box, 1)
        live.addLayout(body, 1)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.stat_min = StatTile("最低")
        self.stat_avg = StatTile("平均")
        self.stat_max = StatTile("最高")
        self.stat_count = StatTile("采样", unit="个")
        for tile in (self.stat_min, self.stat_avg, self.stat_max, self.stat_count):
            stats.addWidget(tile)
        live.addLayout(stats)
        layout.addWidget(live_card, 5)

        history_card = QFrame()
        history_card.setObjectName("Card")
        hist = QVBoxLayout(history_card)
        hist.setContentsMargins(18, 14, 18, 12)
        hist.setSpacing(8)
        hist_header = QHBoxLayout()
        hist_header.setSpacing(8)
        hist_title = QLabel("心率历史")
        hist_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        hist_header.addWidget(hist_title)
        hist_header.addSpacing(6)
        self.range_group = QButtonGroup(self)
        self.range_group.setExclusive(True)
        ranges = [("5 分钟", 300), ("30 分钟", 1800), ("1 小时", 3600), ("6 小时", 21600), ("24 小时", 86400)]
        for index, (label, seconds) in enumerate(ranges):
            button = QPushButton(label)
            button.setObjectName("RangeButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(seconds == 300)
            self.range_group.addButton(button, seconds)
            hist_header.addWidget(button)
        self.range_group.idClicked.connect(self._set_history_range)
        hist_header.addStretch(1)
        export = QPushButton("导出 CSV")
        export.setObjectName("Chip")
        export.clicked.connect(self._export_history)
        hist_header.addWidget(export)
        clear = QPushButton("清空")
        clear.setObjectName("Chip")
        clear.clicked.connect(self._clear_selected_history)
        hist_header.addWidget(clear)
        hist.addLayout(hist_header)
        self.history_chart = HeartChart()
        self.history_chart.set_empty_text("暂无历史数据，连接设备后会按秒记录")
        self.history_chart.setMinimumHeight(190)
        hist.addWidget(self.history_chart, 1)
        self.history_info = QLabel("—")
        self.history_info.setProperty("role", "dim")
        hist.addWidget(self.history_info)
        layout.addWidget(history_card, 4)
        return page

    # ------------------------------------------------------------------
    # Session/profile helpers
    # ------------------------------------------------------------------
    def _sync_sessions_from_profiles(self) -> None:
        for key, profile in self.config.devices.items():
            if key not in self._sessions:
                self._sessions[key] = DeviceSession(key=key, profile=profile)
            else:
                self._sessions[key].profile = profile

    def _ensure_profile(self, address: str, name: str, key: str | None = None) -> DeviceProfile:
        key = key or make_device_key(address, name)
        profile = self.config.devices.get(key)
        if profile is None:
            profile = DeviceProfile(
                key=key,
                address=address,
                name=name,
                display=dataclasses.replace(self.config.default_display),
            )
            self.config.devices[key] = profile
            self._schedule_save()
        else:
            changed = False
            if name and profile.name != name:
                profile.name = name
                changed = True
            if address and profile.address != address:
                profile.address = address
                changed = True
            if changed:
                self._schedule_save()
        self._sessions.setdefault(key, DeviceSession(key=key, profile=profile))
        self._sessions[key].profile = profile
        return profile

    def _session_for(self, key: str) -> DeviceSession | None:
        return self._sessions.get(key)

    def _session_dict(self, session: DeviceSession) -> dict[str, Any]:
        overlay = self._overlays.get(session.key)
        visible = bool(overlay and overlay.isVisible())
        return {
            "connected": session.connected,
            "state": session.state,
            "bpm": session.bpm,
            "battery": session.battery,
            "message": session.message,
            "overlay_visible": visible,
            "overlay_locked": bool(overlay and overlay.locked),
        }

    def _profile_for(self, key: str) -> DeviceProfile | None:
        session = self._sessions.get(key)
        return session.profile if session else self.config.devices.get(key)

    # ------------------------------------------------------------------
    # BLE signal handlers
    # ------------------------------------------------------------------
    def _connect_ble_signals(self) -> None:
        self.ble.heart_rate.connect(self._on_heart_rate)
        self.ble.connection_state.connect(self._on_connection_state)
        self.ble.battery.connect(self._on_battery)
        self.ble.log.connect(self._on_ble_log)
        self.ble.scan_error.connect(lambda message: self.show_status(message, "error"))
        self.ble.scan_started.connect(lambda: self.show_status("正在扫描蓝牙设备…", "idle"))

    def _on_heart_rate(self, key: str, bpm: int, ts: float, extra: Any) -> None:
        session = self._sessions.get(key)
        if session is None:
            return
        session.bpm = int(bpm)
        session.last_update = ts
        session.state = STATE_CONNECTED
        session.message = "已连接 · 正在接收心率"
        session.samples.append((ts, int(bpm)))
        self.history.add_sample(key, int(bpm), ts)
        if isinstance(extra, dict):
            session.rr = extra.get("rr")
        self._update_card(key)
        overlay = self._overlays.get(key)
        if overlay is not None:
            overlay.set_data(session.bpm, True, session.battery)
        if key == self._selected_key:
            self._update_current_bpm()
            self.last_update_label.setText(
                "最后更新 " + time.strftime("%H:%M:%S", time.localtime(ts))
            )
        self._update_header_state()
        now = time.monotonic()
        if now - self._last_tray_update > 5:
            self._last_tray_update = now
            self._update_tray_tooltip()

    def _on_connection_state(self, key: str, state: str, message: str) -> None:
        session = self._sessions.get(key)
        if session is None:
            profile = self.config.devices.get(key)
            if profile is None:
                return
            session = DeviceSession(key=key, profile=profile)
            self._sessions[key] = session
        session.state = state
        session.message = message
        overlay = self._overlays.get(key)
        if state == STATE_CONNECTED:
            session.profile.last_connected = time.time()
            session.profile.connect_count += 1
            if session.profile.overlay_visible and overlay is None:
                self._open_overlay(key)
            if overlay is not None:
                overlay.set_connected(True)
                overlay.set_data(session.bpm, True, session.battery)
            self._schedule_save()
            self.show_status(f"{session.profile.display_name} · {message}", "ok")
        else:
            if state in {STATE_DISCONNECTED, STATE_ERROR}:
                session.bpm = 0
                if overlay is not None:
                    overlay.set_connected(False)
                if state == STATE_ERROR:
                    self.show_status(f"{session.profile.display_name} · {message}", "error")
                    self._notify_tray(f"{session.profile.display_name}: {message}", warning=True)
                else:
                    self.show_status(f"{session.profile.display_name} · {message}", "idle")
            elif state in {STATE_CONNECTING, STATE_RECONNECTING}:
                self.show_status(f"{session.profile.display_name} · {message}", "warn")
        self._refresh_device_list()
        if key == self._selected_key:
            self._refresh_selected_view()
        self._update_header_state()
        self._update_tray_tooltip()

    def _on_battery(self, key: str, level: int) -> None:
        session = self._sessions.get(key)
        if session is None:
            return
        session.battery = int(level)
        self._update_card(key)
        overlay = self._overlays.get(key)
        if overlay is not None:
            overlay.set_data(session.bpm, session.connected, session.battery)
        if key == self._selected_key:
            self.detail_battery.setText(f"⚡ {level}%")
        self._schedule_save()

    def _on_ble_log(self, message: str) -> None:
        log.info("BLE: %s", message)
        if "失败" in message or "断开" in message:
            self.show_status(message, "warn")

    # ------------------------------------------------------------------
    # Device list / selection
    # ------------------------------------------------------------------
    def _refresh_device_list(self) -> None:
        self._sync_sessions_from_profiles()
        while self.device_layout.count():
            item = self.device_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards.clear()

        sessions = list(self._sessions.values())
        sessions.sort(
            key=lambda s: (
                1 if s.profile.favorite else 0,
                s.profile.last_connected,
                s.profile.name.lower(),
            ),
            reverse=True,
        )
        online = [
            s
            for s in sessions
            if s.state in {STATE_CONNECTED, STATE_CONNECTING, STATE_RECONNECTING}
        ]
        offline = [s for s in sessions if s.state not in {STATE_CONNECTED, STATE_CONNECTING, STATE_RECONNECTING}]

        def add_card(session, target_layout, parent_widget) -> None:
            card = DeviceCard(session.profile, parent_widget)
            card.select_requested.connect(self._select_device)
            card.connect_requested.connect(self._connect_key)
            card.disconnect_requested.connect(self._disconnect_key)
            card.overlay_requested.connect(self._toggle_overlay)
            card.lock_requested.connect(self._toggle_lock)
            card.style_requested.connect(self.open_style_for)
            card.favorite_requested.connect(self._toggle_favorite)
            card.forget_requested.connect(self._forget_device)
            card.auto_reconnect_requested.connect(self._set_auto_reconnect)
            card.set_selected(session.key == self._selected_key)
            card.update_from(session.profile, self._session_dict(session))
            target_layout.addWidget(card)
            self._cards[session.key] = card

        for session in online:
            add_card(session, self.device_layout, self.device_container)
        self.disconnected_toggle = None
        self.disconnected_panel = None
        if offline:
            expanded = bool(self.config.disconnected_expanded)
            toggle = QPushButton(("▾" if expanded else "▸") + f"  已断开 ({len(offline)})")
            toggle.setObjectName("SectionButton")
            toggle.setCheckable(True)
            toggle.setChecked(expanded)
            toggle.setCursor(Qt.PointingHandCursor)
            toggle.setToolTip("展开或收起已断开的设备")
            toggle.toggled.connect(self._toggle_disconnected_group)
            self.disconnected_toggle = toggle
            self.device_layout.addWidget(toggle)
            panel = QWidget(self.device_container)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(9)
            for session in offline:
                add_card(session, panel_layout, panel)
            panel.setVisible(expanded)
            self.disconnected_panel = panel
            self.device_layout.addWidget(panel)
        self.device_layout.addStretch(1)
        count = len(sessions)
        self.device_count.setText(f"{count} 台")
        self.left_stack.setCurrentIndex(0 if count == 0 else 1)
        if count == 0:
            self._multi_cards.clear()
            while self.multi_grid.count():
                item = self.multi_grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self.right_stack.setCurrentIndex(0)
            self.view_bar.setVisible(False)
        else:
            self._rebuild_multi_cards()
            self.view_bar.setVisible(True)
        self._update_header_state()
        self._update_tray_tooltip()

    def _toggle_disconnected_group(self, checked: bool) -> None:
        self.config.disconnected_expanded = bool(checked)
        self._schedule_save()
        if self.disconnected_toggle is not None:
            count = (
                self.disconnected_panel.layout().count()
                if self.disconnected_panel is not None
                else 0
            )
            self.disconnected_toggle.setText(
                ("▾" if checked else "▸") + f"  已断开 ({count})"
            )
        if self.disconnected_panel is not None:
            self.disconnected_panel.setVisible(bool(checked))

    def _update_card(self, key: str) -> None:
        card = self._cards.get(key)
        session = self._sessions.get(key)
        if card is not None and session is not None:
            card.update_from(session.profile, self._session_dict(session))
            if key == self._selected_key:
                card.set_selected(True)

    def _choose_initial_selection(self) -> None:
        selected = self.config.selected_key
        if selected in self._sessions:
            self._selected_key = selected
        elif self._sessions:
            self._selected_key = next(iter(self._sessions))
        else:
            self._selected_key = ""
        self.config.selected_key = self._selected_key
        for key, card in self._cards.items():
            card.set_selected(key == self._selected_key)

    def _select_device(self, key: str) -> None:
        if key not in self._sessions:
            return
        self._selected_key = key
        self.config.selected_key = key
        self._schedule_save()
        for card_key, card in self._cards.items():
            card.set_selected(card_key == key)
        for card_key, card in self._multi_cards.items():
            card.set_selected(card_key == key)
        self._refresh_selected_view()

    def _on_view_mode_clicked(self, index: int) -> None:
        self._set_multi_view(index == 1)

    def _set_multi_view(self, enabled: bool) -> None:
        self._multi_view = bool(enabled)
        self.config.multi_view = self._multi_view
        self.single_view_button.setChecked(not self._multi_view)
        self.multi_view_button.setChecked(self._multi_view)
        self._schedule_save()
        self._refresh_selected_view()

    def _show_single_device(self, key: str) -> None:
        self._select_device(key)
        self._set_multi_view(False)

    def _refresh_selected_view(self) -> None:
        session = self._sessions.get(self._selected_key)
        if session is None:
            self.right_stack.setCurrentIndex(0)
            self.view_bar.setVisible(False)
            return
        self.view_bar.setVisible(True)
        self.single_view_button.setChecked(not self._multi_view)
        self.multi_view_button.setChecked(self._multi_view)
        self.view_hint.setText(
            f"全部 {len(self._sessions)} 台设备同时显示"
            if self._multi_view
            else f"当前：{session.profile.display_name}"
        )
        if self._multi_view:
            self.right_stack.setCurrentIndex(2)
            if not self._multi_cards:
                self._rebuild_multi_cards()
            self._refresh_multi_data()
            return
        self.right_stack.setCurrentIndex(1)
        profile = session.profile
        self.detail_name.setText(profile.display_name)
        self.detail_avatar.setText("❤")
        meta = pretty_address(profile.address)
        if profile.last_connected:
            meta += f"  ·  上次连接 {format_ago(profile.last_connected)}"
        self.detail_meta.setText(meta)
        self.detail_battery.setText(f"⚡ {session.battery}%" if session.battery is not None else "")
        state_map = {
            STATE_CONNECTED: ("● 已连接", "#4ADE80"),
            STATE_CONNECTING: ("● 连接中…", "#FBBF24"),
            STATE_RECONNECTING: ("● 重连中…", "#FBBF24"),
            STATE_ERROR: ("● 连接失败", "#F87171"),
            STATE_DISCONNECTED: ("● 未连接", "#8D99AC"),
        }
        text, state_color = state_map.get(session.state, ("● 未连接", "#8D99AC"))
        self.detail_status.setText(text)
        self.detail_status.setStyleSheet(f"color: {state_color}; font-size: 11px;")
        overlay = self._overlays.get(profile.key)
        self.detail_overlay_button.setText(
            "隐藏悬浮窗" if overlay and overlay.isVisible() else "显示悬浮窗"
        )
        self._update_current_bpm()
        self._refresh_live_chart()
        self._refresh_stats()
        self._refresh_history_chart()

    def _rebuild_multi_cards(self) -> None:
        while self.multi_grid.count():
            item = self.multi_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._multi_cards.clear()
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: (
                1 if s.connected else 0,
                1 if s.profile.favorite else 0,
                s.profile.last_connected,
                s.profile.name.lower(),
            ),
            reverse=True,
        )
        for index, session in enumerate(sessions):
            card = MultiDeviceCard(session.profile, self.multi_container)
            card.select_requested.connect(self._select_device)
            card.detail_requested.connect(self._show_single_device)
            card.overlay_requested.connect(self._toggle_overlay)
            card.lock_requested.connect(self._toggle_lock)
            card.style_requested.connect(self.open_style_for)
            card.set_selected(session.key == self._selected_key)
            self.multi_grid.addWidget(card, index // 2, index % 2)
            self._multi_cards[session.key] = card
        self.multi_count.setText(f"{len(sessions)} 台")
        self.multi_grid.setColumnStretch(0, 1)
        self.multi_grid.setColumnStretch(1, 1 if len(sessions) > 1 else 0)
        rows = max(1, (len(sessions) + 1) // 2)
        for row in range(rows):
            self.multi_grid.setRowStretch(row, 1)
        self.multi_grid.setRowStretch(rows, 0)
        self._refresh_multi_data()

    def _refresh_multi_data(self) -> None:
        now = time.time()
        bucket = self._history_bucket()
        range_label = self._range_label()
        for key, card in self._multi_cards.items():
            session = self._sessions.get(key)
            if session is None:
                continue
            data = self._session_dict(session)
            data["last_update"] = session.last_update
            points = [(ts, bpm) for ts, bpm in session.samples if ts >= now - 180]
            values = [bpm for ts, bpm in session.samples if ts >= now - 300]
            stats = {
                "min": min(values) if values else 0,
                "avg": int(round(sum(values) / len(values))) if values else 0,
                "max": max(values) if values else 0,
                "count": len(values),
            }
            history_points = self.history.points(
                key,
                now - self._history_range,
                bucket=bucket,
                max_points=600,
            )
            card.update_from(
                session.profile,
                data,
                points,
                stats,
                history_points,
                range_label,
                self._history_range,
                bucket,
            )


    def _update_current_bpm(self) -> None:
        session = self._sessions.get(self._selected_key)
        if session is None:
            return
        if session.connected and session.bpm > 0:
            self.big_bpm.setText(str(session.bpm))
            self.big_bpm.setStyleSheet(
                "font-family: 'Segoe UI'; font-size: 76px; font-weight: 800; color: #EEF2F8;"
            )
        else:
            self.big_bpm.setText("—")
            self.big_bpm.setStyleSheet(
                "font-family: 'Segoe UI'; font-size: 76px; font-weight: 800; color: #4F5A6C;"
            )
        if session.last_update:
            self.last_update_label.setText(
                "最后更新 " + time.strftime("%H:%M:%S", time.localtime(session.last_update))
            )
        else:
            self.last_update_label.setText(
                "等待心率数据…" if session.connected else "设备未连接"
            )

    def _update_header_state(self) -> None:
        connected = sum(1 for s in self._sessions.values() if s.connected)
        connecting = sum(
            1 for s in self._sessions.values() if s.state in {STATE_CONNECTING, STATE_RECONNECTING}
        )
        if connected:
            self.header_status.setText(f"● 已连接 {connected} 台")
            self.header_status.setStyleSheet("color: #4ADE80; font-size: 11px;")
        elif connecting:
            self.header_status.setText("● 正在连接…")
            self.header_status.setStyleSheet("color: #FBBF24; font-size: 11px;")
        elif self._sessions:
            self.header_status.setText("● 蓝牙待命")
            self.header_status.setStyleSheet("color: #8D99AC; font-size: 11px;")
        else:
            self.header_status.setText("● 蓝牙待命")
            self.header_status.setStyleSheet("color: #8D99AC; font-size: 11px;")

    # ------------------------------------------------------------------
    # Charts / periodic refresh
    # ------------------------------------------------------------------
    def _load_recent_history(self) -> None:
        now = time.time()
        for key, session in self._sessions.items():
            try:
                points = self.history.points(key, now - 900, bucket=1, max_points=900)
            except Exception:
                points = []
            if points:
                session.samples.clear()
                session.samples.extend(points[-900:])
                last_ts, last_bpm = points[-1]
                if now - last_ts < 300:
                    session.bpm = last_bpm
                    session.last_update = last_ts

    def _tick(self) -> None:
        session = self._sessions.get(self._selected_key)
        if session is None:
            return
        if self._multi_view:
            self._refresh_multi_data()
        else:
            self._refresh_live_chart()
            self._refresh_stats()
            self._refresh_history_chart()
            self._update_current_bpm()
        now = time.monotonic()
        if now - self._last_tray_update > 5:
            self._last_tray_update = now
            self._update_tray_tooltip()

    def _refresh_live_chart(self) -> None:
        session = self._sessions.get(self._selected_key)
        if session is None:
            return
        now = time.time()
        points = [(ts, bpm) for ts, bpm in session.samples if ts >= now - 180]
        self.live_chart.set_points(points, range_sec=180, bucket=1.0)

    def _refresh_stats(self) -> None:
        session = self._sessions.get(self._selected_key)
        if session is None:
            return
        now = time.time()
        values = [bpm for ts, bpm in session.samples if ts >= now - 300]
        if values:
            self.stat_min.set_value(min(values))
            self.stat_avg.set_value(int(round(sum(values) / len(values))))
            self.stat_max.set_value(max(values))
            self.stat_count.set_value(len(values))
        else:
            for tile in (self.stat_min, self.stat_avg, self.stat_max, self.stat_count):
                tile.set_value(0)

    def _set_history_range(self, seconds: int) -> None:
        self._history_range = int(seconds)
        button = self.range_group.button(self._history_range)
        if button is not None:
            button.setChecked(True)
        if hasattr(self, "multi_range_combo"):
            index = self.multi_range_combo.findData(self._history_range)
            if index >= 0 and index != self.multi_range_combo.currentIndex():
                self.multi_range_combo.blockSignals(True)
                self.multi_range_combo.setCurrentIndex(index)
                self.multi_range_combo.blockSignals(False)
        if self._multi_view:
            self._refresh_multi_data()
        else:
            self._refresh_history_chart()

    def _on_multi_range_changed(self, index: int) -> None:
        seconds = self.multi_range_combo.itemData(index)
        if seconds:
            self._set_history_range(int(seconds))

    def _history_bucket(self) -> float:
        if self._history_range <= 600:
            return 1.0
        if self._history_range <= 1800:
            return 2.0
        if self._history_range <= 3600:
            return 5.0
        if self._history_range <= 21600:
            return 30.0
        return 120.0

    def _refresh_history_chart(self) -> None:
        session = self._sessions.get(self._selected_key)
        if session is None:
            return
        now = time.time()
        since = now - self._history_range
        bucket = self._history_bucket()
        points = self.history.points(session.key, since, bucket=bucket, max_points=900)
        self.history_chart.set_points(points, range_sec=self._history_range, bucket=bucket)
        if points:
            self.history_info.setText(
                f"最近 {self._range_label()} · {len(points)} 个绘图点 · "
                f"数据保存在本机 · 右键悬浮窗可调整样式"
            )
        else:
            self.history_info.setText("当前时间段暂无历史数据")

    def _range_label(self) -> str:
        mapping = {300: "5 分钟", 1800: "30 分钟", 3600: "1 小时", 21600: "6 小时", 86400: "24 小时"}
        return mapping.get(self._history_range, f"{self._history_range // 60} 分钟")

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------
    def open_device_dialog(self) -> None:
        dialog = DeviceSelectionDialog(
            self,
            self.ble,
            self.config_store,
            connected_keys={key for key, s in self._sessions.items() if s.connected},
        )
        result = dialog.exec()
        self._refresh_device_list()
        if result == QDialog.Accepted and dialog.result_devices:
            for info in dialog.result_devices:
                self._connect_info(info)
        else:
            self._save_config()

    def _connect_info(self, info) -> None:
        profile = self._ensure_profile(info.address, info.name, getattr(info, "key", None))
        session = self._sessions.get(profile.key)
        if session is None:
            session = DeviceSession(key=profile.key, profile=profile)
            self._sessions[profile.key] = session
        if session.state in {STATE_CONNECTING, STATE_CONNECTED}:
            return
        session.state = STATE_CONNECTING
        session.message = "正在连接…"
        self._select_device(profile.key)
        self._refresh_device_list()
        self._update_header_state()
        self.show_status(f"正在连接 {profile.display_name}…", "warn")
        self.ble.connect_device(
            profile.key, profile.address, profile.display_name, profile.auto_reconnect
        )

    def _connect_key(self, key: str) -> None:
        profile = self._profile_for(key)
        session = self._sessions.get(key)
        if profile is None or session is None:
            return
        if session.connected or session.state == STATE_CONNECTING:
            return
        info = type(
            "DeviceInfo",
            (),
            {
                "address": profile.address,
                "name": profile.display_name,
                "key": profile.key,
            },
        )()
        self._connect_info(info)

    def _disconnect_key(self, key: str) -> None:
        session = self._sessions.get(key)
        if session is None:
            return
        self.ble.disconnect_device(key)
        session.state = STATE_DISCONNECTED
        session.message = "已断开连接"
        session.bpm = 0
        overlay = self._overlays.get(key)
        if overlay is not None:
            overlay.set_connected(False)
        self._refresh_device_list()
        if key == self._selected_key:
            self._refresh_selected_view()
        self.show_status(f"{session.profile.display_name} 已断开", "idle")

    def _restore_auto_connect(self) -> None:
        if not self.config.auto_reconnect_favorites:
            return
        chosen = [
            p
            for p in self.config.devices.values()
            if p.favorite and p.auto_reconnect and p.address
        ]
        for index, profile in enumerate(chosen[:6]):
            QTimer.singleShot(index * 900, lambda p=profile: self._connect_key(p.key))

    def _toggle_favorite(self, key: str) -> None:
        profile = self._profile_for(key)
        if profile is None:
            return
        profile.favorite = not profile.favorite
        self._schedule_save()
        self._refresh_device_list()
        self.show_status(
            ("已收藏 " if profile.favorite else "已取消收藏 ") + profile.display_name, "ok"
        )

    def _set_auto_reconnect(self, key: str, enabled: bool) -> None:
        profile = self._profile_for(key)
        if profile is None:
            return
        profile.auto_reconnect = bool(enabled)
        self._schedule_save()
        self.show_status(
            ("已开启自动重连 · " if enabled else "已关闭自动重连 · ") + profile.display_name,
            "idle",
        )

    def _forget_device(self, key: str) -> None:
        profile = self._profile_for(key)
        if profile is None:
            return
        answer = QMessageBox.question(
            self,
            "忘记此设备",
            f"确定要将「{profile.display_name}」从设备列表移除吗？\n\n"
            "设备地址与样式设置会被移除，历史心率数据仍会保留。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.ble.disconnect_device(key)
        overlay = self._overlays.pop(key, None)
        if overlay is not None:
            overlay.hide()
            overlay.deleteLater()
        self.config.devices.pop(key, None)
        self._sessions.pop(key, None)
        if self._selected_key == key:
            self._selected_key = next(iter(self._sessions), "")
            self.config.selected_key = self._selected_key
        self._schedule_save()
        self._refresh_device_list()
        self._refresh_selected_view()
        self.show_status(f"已移除 {profile.display_name}", "idle")

    # ------------------------------------------------------------------
    # Overlays
    # ------------------------------------------------------------------
    def _open_overlay(self, key: str) -> HeartOverlay | None:
        session = self._sessions.get(key)
        if session is None:
            return None
        overlay = self._overlays.get(key)
        if overlay is None:
            profile = session.profile
            position = None
            if profile.overlay_x is not None and profile.overlay_y is not None:
                position = QPoint(int(profile.overlay_x), int(profile.overlay_y))
            size = None
            if profile.overlay_width and profile.overlay_height:
                size = QSize(int(profile.overlay_width), int(profile.overlay_height))
            overlay = HeartOverlay(
                device_key=key,
                device_name=profile.display_name,
                display=profile.display,
                bpm=session.bpm,
                battery=session.battery,
                connected=session.connected,
                locked=profile.overlay_locked,
                topmost_enhance=self.config.topmost_enhance,
                topmost_interval_ms=self.config.topmost_interval_ms,
                position=position,
                size=size,
            )
            overlay.lock_changed.connect(self._on_overlay_lock_changed)
            overlay.closed.connect(self._on_overlay_closed)
            overlay.style_requested.connect(self.open_style_for)
            overlay.position_changed.connect(self._on_overlay_position)
            overlay.size_changed.connect(self._on_overlay_size_changed)
            overlay.bring_to_front.connect(self._select_device)
            self._overlays[key] = overlay
            if position is None:
                area = QGuiApplication.primaryScreen().availableGeometry()
                offset = (len(self._overlays) - 1) * 38
                overlay.adjustSize()
                overlay.move(
                    area.right() - overlay.width() - 70,
                    area.top() + 96 + offset,
                )
                session.profile.overlay_x = overlay.x()
                session.profile.overlay_y = overlay.y()
                self._schedule_save()
        overlay.set_device_name(session.profile.display_name)
        overlay.set_data(session.bpm, session.connected, session.battery)
        overlay.set_locked(session.profile.overlay_locked, emit=False)
        overlay.show()
        overlay.set_locked(session.profile.overlay_locked, emit=False)
        session.profile.overlay_visible = True
        session.profile.overlay_locked = overlay.locked
        self._schedule_save()
        self._update_card(key)
        if self._selected_key == key:
            self._refresh_selected_view()
        return overlay

    def _hide_overlay(self, key: str) -> None:
        overlay = self._overlays.get(key)
        if overlay is not None:
            overlay.hide()
        session = self._sessions.get(key)
        if session is not None:
            session.profile.overlay_visible = False
            self._schedule_save()
            self._update_card(key)
        if self._selected_key == key:
            self._refresh_selected_view()

    def _toggle_overlay(self, key: str) -> None:
        overlay = self._overlays.get(key)
        if overlay is not None and overlay.isVisible():
            self._hide_overlay(key)
            self.show_status("悬浮窗已隐藏", "idle")
        else:
            self._open_overlay(key)
            self.show_status("悬浮窗已显示 · 拖动到合适位置后点击「锁定」", "ok")

    def _toggle_selected_overlay(self) -> None:
        if self._selected_key:
            self._toggle_overlay(self._selected_key)

    def _style_selected(self) -> None:
        if self._selected_key:
            self.open_style_for(self._selected_key)

    def _toggle_lock(self, key: str) -> None:
        overlay = self._overlays.get(key)
        if overlay is None or not overlay.isVisible():
            overlay = self._open_overlay(key)
        if overlay is None:
            return
        overlay.set_locked(not overlay.locked)
        self._refresh_selected_view() if key == self._selected_key else None

    def _on_overlay_lock_changed(self, key: str, locked: bool) -> None:
        session = self._sessions.get(key)
        if session is None:
            return
        session.profile.overlay_locked = bool(locked)
        self._schedule_save()
        self._update_card(key)
        self.show_status(
            "悬浮窗已锁定 · 鼠标点击会穿透" if locked else "悬浮窗已解锁 · 可以拖动",
            "ok" if locked else "idle",
        )

    def _on_overlay_closed(self, key: str) -> None:
        if self._quitting:
            return
        overlay = self._overlays.get(key)
        if overlay is not None and overlay.isVisible():
            overlay.hide()
        session = self._sessions.get(key)
        if session is not None:
            session.profile.overlay_visible = False
            self._schedule_save()
            self._update_card(key)
        if key == self._selected_key:
            self._refresh_selected_view()

    def _on_overlay_position(self, key: str, x: int, y: int) -> None:
        session = self._sessions.get(key)
        if session is None:
            return
        session.profile.overlay_x = int(x)
        session.profile.overlay_y = int(y)
        self._schedule_save()

    def _on_overlay_size_changed(self, key: str, width: int, height: int) -> None:
        session = self._sessions.get(key)
        if session is None:
            return
        if width > 0 and height > 0:
            session.profile.overlay_width = int(width)
            session.profile.overlay_height = int(height)
        else:
            session.profile.overlay_width = None
            session.profile.overlay_height = None
        self._schedule_save()

    def _restore_overlays(self) -> None:
        for key, profile in list(self.config.devices.items()):
            if profile.overlay_visible:
                self._open_overlay(key)

    def _show_all_overlays(self) -> None:
        if not self._sessions:
            self.show_status("还没有设备，请先选择设备", "warn")
            return
        for key in self._sessions:
            self._open_overlay(key)
        self.show_status(f"已显示 {len(self._overlays)} 个悬浮窗", "ok")

    def _hide_all_overlays(self) -> None:
        for key in list(self._overlays):
            self._hide_overlay(key)
        self.show_status("已隐藏全部悬浮窗", "idle")

    def _set_all_locks(self, locked: bool) -> None:
        if not self._overlays:
            self.show_status("当前没有可见的悬浮窗", "warn")
            return
        for key, overlay in self._overlays.items():
            if overlay.isVisible():
                overlay.set_locked(locked)
        self.show_status("已锁定全部悬浮窗" if locked else "已解锁全部悬浮窗", "ok")

    def open_style_for(self, key: str) -> None:
        session = self._sessions.get(key)
        if session is None:
            return

        def apply(cfg: DisplayConfig) -> None:
            session.profile.display = cfg
            overlay = self._overlays.get(key)
            if overlay is not None:
                overlay.set_display(cfg)
            self._schedule_save()

        dialog = DisplaySettingsDialog(
            self,
            session.profile.display,
            session.profile.display_name,
            apply,
            sample_bpm=session.bpm or 78,
            sample_connected=session.connected,
        )
        result = dialog.exec()
        if result == QDialog.Accepted:
            session.profile.display = dialog.result_config()
            self._schedule_save()
            self.show_status("悬浮窗样式已保存", "ok")
        else:
            self._schedule_save()

    def _edit_default_style(self) -> None:
        def apply(cfg: DisplayConfig) -> None:
            self.config.default_display = cfg
            self._schedule_save()

        dialog = DisplaySettingsDialog(
            self,
            self.config.default_display,
            "新设备默认样式",
            apply,
            sample_bpm=78,
            sample_connected=True,
        )
        if dialog.exec() == QDialog.Accepted:
            self.config.default_display = dialog.result_config()
            self._schedule_save()
            self.show_status("已保存新设备的默认悬浮窗样式", "ok")

    # ------------------------------------------------------------------
    # Settings / history actions
    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self,
            self.config_store,
            self.paths,
            self._clear_all_history,
            self._edit_default_style,
        )
        if dialog.exec() == QDialog.Accepted:
            for overlay in self._overlays.values():
                overlay.set_topmost_enhance(
                    self.config.topmost_enhance, self.config.topmost_interval_ms
                )
            self._register_hotkeys()
            self.history.prune(self.config.history_retention_days)
            self._save_config()
            self.show_status("设置已保存", "ok")

    def _clear_selected_history(self) -> None:
        session = self._sessions.get(self._selected_key)
        if session is None:
            return
        answer = QMessageBox.question(
            self,
            "清空历史",
            f"确定要清空「{session.profile.display_name}」的心率历史吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.history.clear(session.key)
        session.samples.clear()
        self._refresh_selected_view()
        self.show_status("已清空该设备的心率历史", "idle")

    def _clear_all_history(self) -> None:
        self.history.clear(None)
        for session in self._sessions.values():
            session.samples.clear()
        self._refresh_selected_view()
        self.show_status("已清空全部心率历史", "idle")

    def _export_history(self) -> None:
        session = self._sessions.get(self._selected_key)
        if session is None:
            return
        default_name = (
            f"{session.profile.display_name}_心率历史_"
            f"{time.strftime('%Y%m%d_%H%M')}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "导出心率历史", default_name, "CSV 文件 (*.csv)"
        )
        if not path:
            return
        since = time.time() - self._history_range if self._history_range > 0 else 0
        count = self.history.export_csv(session.key, since, path)
        if count >= 0:
            self.show_status(f"已导出 {count} 条记录", "ok")
        else:
            self.show_status("导出失败，请检查文件是否被占用", "error")

    # ------------------------------------------------------------------
    # Status bar / tray / notifications
    # ------------------------------------------------------------------
    def show_status(self, message: str, level: str = "idle") -> None:
        if not message:
            return
        color_map = {"ok": "#4ADE80", "warn": "#FBBF24", "error": "#F87171", "idle": "#8D99AC"}
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            f"color: {color_map.get(level, '#8D99AC')}; padding-left: 10px;"
        )
        if level in {"error", "warn"}:
            log.warning(message)
        self._status_timer.start(7000)

    def _reset_status(self) -> None:
        if self._sessions:
            connected = sum(1 for s in self._sessions.values() if s.connected)
            self.status_label.setText(
                f"就绪 · {connected} 台设备已连接" if connected else "就绪 · 蓝牙待命"
            )
        else:
            self.status_label.setText("就绪 · 点击右上角「选择设备」开始")
        self.status_label.setStyleSheet("color: #8D99AC; padding-left: 10px;")

    def _notify_tray(self, message: str, warning: bool = False) -> None:
        if self.tray is not None and self.tray.isVisible():
            icon = QSystemTrayIcon.Warning if warning else QSystemTrayIcon.Information
            self.tray.showMessage(APP_DISPLAY_NAME, message, icon, 4000)

    def _build_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_DISPLAY_NAME)
        menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self._show_from_tray)
        select_action = QAction("选择设备…", self)
        select_action.triggered.connect(self.open_device_dialog)
        show_all = QAction("显示全部悬浮窗", self)
        show_all.triggered.connect(self._show_all_overlays)
        hide_all = QAction("隐藏全部悬浮窗", self)
        hide_all.triggered.connect(self._hide_all_overlays)
        lock_all = QAction("锁定全部悬浮窗", self)
        lock_all.triggered.connect(lambda: self._set_all_locks(True))
        unlock_all = QAction("解锁全部悬浮窗", self)
        unlock_all.triggered.connect(lambda: self._set_all_locks(False))
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(show_action)
        menu.addAction(select_action)
        menu.addSeparator()
        menu.addAction(show_all)
        menu.addAction(hide_all)
        menu.addSeparator()
        menu.addAction(lock_all)
        menu.addAction(unlock_all)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _update_tray_tooltip(self) -> None:
        if self.tray is None:
            return
        lines = [APP_DISPLAY_NAME]
        connected = [s for s in self._sessions.values() if s.connected]
        if connected:
            for session in connected[:3]:
                lines.append(f"{session.profile.display_name}: {session.bpm or '--'} BPM")
        else:
            lines.append("未连接设备")
        self.tray.setToolTip("\n".join(lines))

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------
    def _register_hotkeys(self) -> None:
        if not win32_utils.IS_WINDOWS:
            return
        self._unregister_hotkeys()
        if not self.config.hotkeys_enabled:
            return
        hwnd = win32_utils.hwnd_of(self)
        log.info("Registering hotkeys on hwnd=%s visible=%s", hwnd, self.isVisible())
        if win32_utils.register_hotkey(
            hwnd, HOTKEY_LOCK, win32_utils.MOD_CONTROL | win32_utils.MOD_ALT, 0x4C
        ):
            self._hotkeys_registered.append(HOTKEY_LOCK)
        if win32_utils.register_hotkey(
            hwnd, HOTKEY_VISIBILITY, win32_utils.MOD_CONTROL | win32_utils.MOD_ALT, 0x48
        ):
            self._hotkeys_registered.append(HOTKEY_VISIBILITY)

    def _unregister_hotkeys(self) -> None:
        if not win32_utils.IS_WINDOWS:
            return
        hwnd = win32_utils.hwnd_of(self)
        for hotkey_id in self._hotkeys_registered:
            win32_utils.unregister_hotkey(hwnd, hotkey_id)
        self._hotkeys_registered.clear()

    def nativeEvent(self, event_type, message):
        if win32_utils.IS_WINDOWS:
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == win32_utils.WM_HOTKEY:
                    if msg.wParam == HOTKEY_LOCK:
                        self._hotkey_toggle_lock()
                        return True, 0
                    if msg.wParam == HOTKEY_VISIBILITY:
                        self._hotkey_toggle_visibility()
                        return True, 0
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def _hotkey_toggle_lock(self) -> None:
        overlay = self._overlays.get(self._selected_key)
        if overlay is not None and overlay.isVisible():
            overlay.set_locked(not overlay.locked)
            return
        visible = [o for o in self._overlays.values() if o.isVisible()]
        if visible:
            target = not visible[0].locked
            for item in visible:
                item.set_locked(target)
            self.show_status("已锁定悬浮窗" if target else "已解锁悬浮窗", "ok")
        else:
            self.show_status("没有可锁定的悬浮窗（Ctrl+Alt+L）", "warn")

    def _hotkey_toggle_visibility(self) -> None:
        if any(o.isVisible() for o in self._overlays.values()):
            self._hide_all_overlays()
        else:
            self._show_all_overlays()

    # ------------------------------------------------------------------
    # Persistence / shutdown
    # ------------------------------------------------------------------
    def _restore_geometry(self) -> None:
        geometry = self.config.window_geometry
        if geometry:
            try:
                raw = QByteArray.fromBase64(geometry.encode("ascii"))
                if not self.restoreGeometry(raw):
                    self._center_window()
            except Exception:
                self._center_window()
        else:
            self._center_window()

    def _center_window(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = min(1220, max(1020, area.width() - 120))
        height = min(800, max(660, area.height() - 120))
        self.resize(width, height)
        self.move(area.center().x() - width // 2, area.center().y() - height // 2)

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _save_config(self) -> None:
        try:
            if self.isVisible() and not self.isMinimized():
                self.config.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            for key, overlay in self._overlays.items():
                session = self._sessions.get(key)
                if session is not None:
                    session.profile.overlay_visible = overlay.isVisible()
                    session.profile.overlay_locked = overlay.locked
                    session.profile.overlay_x = overlay.x()
                    session.profile.overlay_y = overlay.y()
                    custom = overlay.custom_size
                    session.profile.overlay_width = custom.width() if custom else None
                    session.profile.overlay_height = custom.height() if custom else None
            self.config_store.save()
        except Exception:
            log.exception("Could not save settings")

    def closeEvent(self, event) -> None:
        if self._force_quit or self._quitting:
            self._quit_now()
            event.accept()
            return
        self.save_all_state()
        if self.config.close_to_tray and self.tray is not None:
            self.hide()
            event.ignore()
            if not self._close_hint_shown:
                self._close_hint_shown = True
                self.tray.showMessage(
                    APP_DISPLAY_NAME,
                    "程序仍在后台运行，悬浮窗会保持置顶。右键托盘图标可退出。",
                    QSystemTrayIcon.Information,
                    4500,
                )
            return
        self.quit_application()
        event.ignore()

    def save_all_state(self) -> None:
        try:
            if self.isVisible() and not self.isMinimized():
                self.config.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.config.selected_key = self._selected_key
            for key, overlay in self._overlays.items():
                session = self._sessions.get(key)
                if session is not None:
                    session.profile.overlay_visible = overlay.isVisible()
                    session.profile.overlay_locked = overlay.locked
                    session.profile.overlay_x = overlay.x()
                    session.profile.overlay_y = overlay.y()
                    custom = overlay.custom_size
                    session.profile.overlay_width = custom.width() if custom else None
                    session.profile.overlay_height = custom.height() if custom else None
            self.config_store.save()
        except Exception:
            log.exception("Could not save application state")

    def quit_application(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._force_quit = True
        self._save_timer.stop()
        self._status_timer.stop()
        self._ui_timer.stop()
        self.save_all_state()
        self._unregister_hotkeys()
        try:
            self.ble.shutdown()
        except Exception:
            log.exception("BLE shutdown failed")
        for overlay in list(self._overlays.values()):
            try:
                overlay.close()
            except Exception:
                pass
        try:
            self.history.close()
        except Exception:
            pass
        if self.tray is not None:
            self.tray.hide()
        QApplication.instance().quit()

    def _quit_now(self) -> None:
        self.quit_application()

    def _first_run_hint(self) -> None:
        if not self._sessions:
            self.show_status("第一步：点击右上角「选择设备」搜索手环 / 手表", "idle")
        elif self.config.first_run:
            self.show_status("点击设备卡片上的「显示悬浮窗」即可显示心率", "idle")
        self.config.first_run = False
        self._schedule_save()

    def _setup_demo(self) -> None:
        if not self._sessions:
            for info in DemoBleService.DEMO_DEVICES[:2]:
                profile = self._ensure_profile(info.address, info.name)
                profile.favorite = True
                profile.display = dataclasses.replace(
                    self.config.default_display,
                    template="❤ {bpm}" if "Mi Band" in info.name else "♥{bpm}",
                    font_size=58 if "Mi Band" in info.name else 52,
                )
            self._selected_key = next(iter(self._sessions), "")
            self.config.selected_key = self._selected_key
            self.history.seed_demo([(key, s.profile.name) for key, s in self._sessions.items()])
            self._load_recent_history()
            self._refresh_device_list()
            self._choose_initial_selection()
            self._refresh_selected_view()
            for index, key in enumerate(list(self._sessions)[:2]):
                QTimer.singleShot(700 + index * 500, lambda k=key: self._connect_key(k))
