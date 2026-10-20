"""Device picker, overlay style editor and settings dialogs (part 2)."""

from __future__ import annotations

import dataclasses
import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .ble_service import DiscoveredDevice
from .models import (
    DeviceProfile,
    format_ago,
    make_device_key,
    pretty_address,
)
from .storage import ConfigStore
from .theme import app_icon

log = logging.getLogger(__name__)


def _rssi_text(rssi: int | None) -> str:
    if rssi is None:
        return "信号 —"
    return f"信号 {rssi} dBm"


class ScanRow(QFrame):
    toggled = Signal(str, bool)
    connect_requested = Signal(object)
    favorite_requested = Signal(str)

    def __init__(
        self,
        info: DiscoveredDevice,
        profile: DeviceProfile,
        connected: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.info = info
        self.profile = profile
        self.connected = connected
        self.setObjectName("SubtleCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 10, 9)
        layout.setSpacing(10)
        self.checkbox = QCheckBox()
        self.checkbox.toggled.connect(lambda checked: self.toggled.emit(self.info.key, checked))
        layout.addWidget(self.checkbox)
        avatar = QLabel("❤")
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(36, 36)
        avatar.setStyleSheet(
            "background: rgba(255,59,92,0.12); border: 1px solid rgba(255,59,92,0.2);"
            "border-radius: 18px; color: #FF5C77; font-size: 17px;"
        )
        layout.addWidget(avatar)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        self.name_label = QLabel(info.name or "未知设备")
        self.name_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.meta_label = QLabel(f"{pretty_address(info.address)}   ·   {_rssi_text(info.rssi)}")
        self.meta_label.setProperty("role", "dim")
        text_box.addWidget(self.name_label)
        text_box.addWidget(self.meta_label)
        layout.addLayout(text_box, 1)

        self.hr_badge = QLabel("❤ 心率广播" if info.has_heart_rate else "连接后检测")
        self.hr_badge.setProperty("role", "chipAccent" if info.has_heart_rate else "chip")
        layout.addWidget(self.hr_badge, 0, Qt.AlignVCenter)

        self.favorite_button = QToolButton()
        self.favorite_button.setObjectName("Star")
        self.favorite_button.setCursor(Qt.PointingHandCursor)
        self.favorite_button.setToolTip("收藏设备")
        self.favorite_button.clicked.connect(lambda: self.favorite_requested.emit(self.info.key))
        layout.addWidget(self.favorite_button)

        self.connect_button = QPushButton("已连接" if connected else "连接")
        self.connect_button.setObjectName("Chip")
        self.connect_button.setEnabled(not connected)
        self.connect_button.setCursor(Qt.PointingHandCursor)
        self.connect_button.clicked.connect(lambda: self.connect_requested.emit(self.info))
        layout.addWidget(self.connect_button)
        self.update_profile(profile)

    def update_info(self, info: DiscoveredDevice) -> None:
        self.info = info
        self.name_label.setText(info.name or "未知设备")
        self.meta_label.setText(f"{pretty_address(info.address)}   ·   {_rssi_text(info.rssi)}")
        self.hr_badge.setText("❤ 心率广播" if info.has_heart_rate else "连接后检测")
        self.hr_badge.setProperty("role", "chipAccent" if info.has_heart_rate else "chip")
        self.hr_badge.style().unpolish(self.hr_badge)
        self.hr_badge.style().polish(self.hr_badge)

    def update_profile(self, profile: DeviceProfile) -> None:
        self.profile = profile
        self.favorite_button.setText("★" if profile.favorite else "☆")
        self.favorite_button.setProperty("favorite", bool(profile.favorite))
        self.favorite_button.style().unpolish(self.favorite_button)
        self.favorite_button.style().polish(self.favorite_button)

    def set_connected(self, connected: bool) -> None:
        self.connected = connected
        self.connect_button.setText("已连接" if connected else "连接")
        self.connect_button.setEnabled(not connected)
        self.checkbox.setEnabled(not connected)
        if connected:
            self.checkbox.setChecked(False)

    def set_checked(self, checked: bool) -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(False)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked() and not self.connected

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self.connected:
            self.checkbox.toggle()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if not self.connected:
            self.connect_requested.emit(self.info)
        super().mouseDoubleClickEvent(event)


class FavoriteRow(QFrame):
    connect_requested = Signal(object)
    favorite_requested = Signal(str)

    def __init__(self, profile: DeviceProfile, connected: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.setObjectName("SubtleCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 8, 9, 8)
        layout.setSpacing(8)
        icon = QLabel("★" if profile.favorite else "◷")
        icon.setStyleSheet(
            "color: #FBBF24;" if profile.favorite else "color: #8D99AC;"
        )
        icon.setFixedWidth(16)
        layout.addWidget(icon)
        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        name = QLabel(profile.display_name)
        name.setStyleSheet("font-size: 12px; font-weight: 600;")
        meta = QLabel(f"{format_ago(profile.last_connected)} · {pretty_address(profile.address)}")
        meta.setProperty("role", "dim")
        text_box.addWidget(name)
        text_box.addWidget(meta)
        layout.addLayout(text_box, 1)
        button = QPushButton("已连接" if connected else "连接")
        button.setObjectName("Chip")
        button.setEnabled(not connected)
        button.clicked.connect(lambda: self.connect_requested.emit(profile))
        layout.addWidget(button)
        if profile.favorite:
            remove = QToolButton()
            remove.setText("✕")
            remove.setToolTip("取消收藏")
            remove.clicked.connect(lambda: self.favorite_requested.emit(profile.key))
            layout.addWidget(remove)


class DeviceSelectionDialog(QDialog):
    """Scans for BLE devices and returns the chosen device list."""

    def __init__(
        self,
        parent: QWidget,
        ble,
        config_store: ConfigStore,
        connected_keys: set[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.ble = ble
        self.config_store = config_store
        self.connected_keys = set(connected_keys or set())
        self.result_devices: list[DiscoveredDevice] = []
        self._rows: dict[str, ScanRow] = {}
        self._favorites: list[FavoriteRow] = []
        self._transient_profiles: dict[str, DeviceProfile] = {}
        self._infos: dict[str, DiscoveredDevice] = {}
        self._scanning = False
        self._finished_once = False
        self._query = ""

        self.setWindowTitle("选择蓝牙设备")
        self.setWindowIcon(app_icon())
        self.resize(900, 640)
        self.setMinimumSize(780, 540)
        self._build()
        self._connect_signals()
        self._refresh_favorites()
        self._update_counter()
        QTimer.singleShot(120, self.start_scan)

    # -- UI ----------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("选择设备")
        title.setStyleSheet("font-size: 23px; font-weight: 700;")
        subtitle = QLabel(
            "确保手环 / 手表已开启心率广播并靠近电脑 · 可勾选多个设备同时连接"
        )
        subtitle.setProperty("role", "muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        close_button = QToolButton()
        close_button.setText("✕")
        close_button.setObjectName("IconButton")
        close_button.clicked.connect(self.reject)
        header.addWidget(close_button, 0, Qt.AlignTop)
        root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索设备名称或地址…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search_edit, 1)
        self.scan_button = QPushButton("开始扫描")
        self.scan_button.setObjectName("Primary")
        self.scan_button.clicked.connect(self.start_scan)
        toolbar.addWidget(self.scan_button)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("Ghost")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_scan)
        toolbar.addWidget(self.stop_button)
        root.addLayout(toolbar)

        self.scan_status = QLabel("准备扫描附近设备…")
        self.scan_status.setProperty("role", "muted")
        root.addWidget(self.scan_status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        body = QHBoxLayout()
        body.setSpacing(14)

        left = QFrame()
        left.setObjectName("Card")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 12, 14, 12)
        left_layout.setSpacing(8)
        left_header = QHBoxLayout()
        left_header.addWidget(QLabel("附近的设备"))
        left_header.addStretch(1)
        self.found_label = QLabel("0 个")
        self.found_label.setProperty("role", "chip")
        left_header.addWidget(self.found_label)
        left_layout.addLayout(left_header)
        self.scan_scroll = QScrollArea()
        self.scan_scroll.setWidgetResizable(True)
        self.scan_container = QWidget()
        self.scan_layout = QVBoxLayout(self.scan_container)
        self.scan_layout.setContentsMargins(0, 0, 4, 0)
        self.scan_layout.setSpacing(7)
        self.empty_scan_label = QLabel(
            "正在搜索…\n\n请确认：\n• 手环已开启「心率广播」\n• 电脑蓝牙已打开\n• 设备距离电脑 1–2 米内"
        )
        self.empty_scan_label.setAlignment(Qt.AlignCenter)
        self.empty_scan_label.setProperty("role", "muted")
        self.empty_scan_label.setWordWrap(True)
        self.scan_layout.addWidget(self.empty_scan_label)
        self.scan_layout.addStretch(1)
        self.scan_scroll.setWidget(self.scan_container)
        left_layout.addWidget(self.scan_scroll, 1)
        self.scan_error = QLabel("")
        self.scan_error.setStyleSheet("color: #F87171; font-size: 11px;")
        self.scan_error.setWordWrap(True)
        left_layout.addWidget(self.scan_error)
        body.addWidget(left, 1)

        right = QFrame()
        right.setObjectName("Card")
        right.setFixedWidth(300)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_layout.setSpacing(8)
        fav_header = QHBoxLayout()
        fav_header.addWidget(QLabel("收藏 / 常用"))
        fav_header.addStretch(1)
        hint = QLabel("★")
        hint.setStyleSheet("color: #FBBF24;")
        fav_header.addWidget(hint)
        right_layout.addLayout(fav_header)
        self.fav_scroll = QScrollArea()
        self.fav_scroll.setWidgetResizable(True)
        self.fav_container = QWidget()
        self.fav_layout = QVBoxLayout(self.fav_container)
        self.fav_layout.setContentsMargins(0, 0, 4, 0)
        self.fav_layout.setSpacing(7)
        self.fav_empty = QLabel("收藏设备后会出现在这里，\n下次连接无需重新搜索。")
        self.fav_empty.setAlignment(Qt.AlignCenter)
        self.fav_empty.setProperty("role", "muted")
        self.fav_empty.setWordWrap(True)
        self.fav_layout.addWidget(self.fav_empty)
        self.fav_layout.addStretch(1)
        self.fav_scroll.setWidget(self.fav_container)
        right_layout.addWidget(self.fav_scroll, 1)
        right_layout.addWidget(
            QLabel("提示：可先在扫描结果中点 ☆ 收藏设备。"),
        )
        body.addWidget(right, 0)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        self.selection_hint = QLabel("勾选设备后可同时连接多个")
        self.selection_hint.setProperty("role", "muted")
        footer.addWidget(self.selection_hint)
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.connect_button = QPushButton("连接所选设备")
        self.connect_button.setObjectName("Primary")
        self.connect_button.setEnabled(False)
        self.connect_button.clicked.connect(self._connect_selected)
        footer.addWidget(self.connect_button)
        root.addLayout(footer)

    def _connect_signals(self) -> None:
        self.ble.scan_started.connect(self._on_scan_started)
        self.ble.scan_progress.connect(self._on_scan_progress)
        self.ble.scan_finished.connect(self._on_scan_finished)
        self.ble.scan_error.connect(self._on_scan_error)

    # -- scanning ----------------------------------------------------------
    def start_scan(self) -> None:
        if self._scanning:
            return
        self.scan_error.setText("")
        self.scan_status.setText("正在扫描…  请稍候")
        self.scan_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress.setVisible(True)
        self._scanning = True
        try:
            self.ble.scan(10.0)
        except Exception as exc:
            self._on_scan_error(str(exc))

    def _stop_scan(self) -> None:
        self.stop_button.setEnabled(False)
        self.scan_status.setText("正在停止扫描…")
        self.ble.stop_scan()

    def _on_scan_started(self) -> None:
        self._scanning = True
        self.progress.setVisible(True)

    def _on_scan_progress(self, info: DiscoveredDevice) -> None:
        self.empty_scan_label.setVisible(False)
        key = info.key
        profile = self._ensure_profile(info)
        row = self._rows.get(key)
        if row is None:
            row = ScanRow(info, profile, key in self.connected_keys, self.scan_container)
            row.toggled.connect(self._on_row_toggled)
            row.connect_requested.connect(self._connect_one)
            row.favorite_requested.connect(self._toggle_favorite)
            self._rows[key] = row
            self.scan_layout.insertWidget(self.scan_layout.count() - 1, row)
        else:
            row.update_info(info)
        row.set_connected(key in self.connected_keys)
        row.update_profile(profile)
        row.setVisible(self._matches(self._query, info.name, info.address))
        self.found_label.setText(f"{len(self._rows)} 个")
        self.scan_status.setText(f"正在扫描… 已发现 {len(self._rows)} 个设备")
        self._update_counter()

    def _on_scan_finished(self, devices: list[DiscoveredDevice]) -> None:
        self._scanning = False
        self.progress.setVisible(False)
        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.found_label.setText(f"{len(self._rows)} 个")
        if self._rows:
            self.scan_status.setText(
                f"扫描完成，发现 {len(self._rows)} 个设备 · 勾选后点击右下角连接"
            )
        else:
            self.scan_status.setText("未发现设备")
            self.empty_scan_label.setText(
                "没有发现蓝牙设备。\n\n请检查：\n• 手环是否开启「心率广播」\n"
                "• 电脑蓝牙是否打开\n• 设备是否已与手机连接（部分设备需先断开手机）\n"
                "然后点击「开始扫描」重试。"
            )
            self.empty_scan_label.setVisible(True)
        self._finished_once = True
        self._update_counter()

    def _on_scan_error(self, message: str) -> None:
        self._scanning = False
        self.progress.setVisible(False)
        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.scan_status.setText("扫描失败")
        self.scan_error.setText(f"{message}\n请确认系统蓝牙已开启；台式机可尝试插入蓝牙适配器。")
        if not self._rows:
            self.empty_scan_label.setVisible(True)

    # -- devices / favorites ----------------------------------------------
    def _ensure_profile(self, info: DiscoveredDevice) -> DeviceProfile:
        config = self.config_store.config
        key = info.key
        self._infos[key] = info
        profile = config.devices.get(key)
        if profile is None:
            key = make_device_key(info.address, info.name)
            profile = config.devices.get(key)
        if profile is None:
            # Do not persist every nearby BLE device.  A profile is only saved
            # when the user favorites or connects it.
            profile = self._transient_profiles.get(key)
            if profile is None:
                profile = DeviceProfile(
                    key=key,
                    address=info.address,
                    name=info.name,
                    display=dataclasses.replace(config.default_display),
                )
                self._transient_profiles[key] = profile
            elif info.name:
                profile.name = info.name
        else:
            changed = False
            if info.name and profile.name != info.name:
                profile.name = info.name
                changed = True
            if info.address and profile.address != info.address:
                profile.address = info.address
                changed = True
            if changed:
                self.config_store.save()
        return profile

    def _on_row_toggled(self, key: str, checked: bool) -> None:
        self._update_counter()

    def _connect_one(self, info: DiscoveredDevice) -> None:
        if info.key in self.connected_keys:
            return
        self.result_devices = [info]
        self.accept()

    def _connect_selected(self) -> None:
        selected = [row.info for row in self._rows.values() if row.is_checked()]
        if not selected:
            self.selection_hint.setText("请先勾选至少一个设备")
            self.selection_hint.setStyleSheet("color: #FBBF24;")
            return
        self.result_devices = selected
        self.accept()

    def _update_counter(self) -> None:
        count = sum(1 for row in self._rows.values() if row.is_checked())
        self.connect_button.setText(f"连接所选设备 ({count})" if count else "连接所选设备")
        self.connect_button.setEnabled(count > 0)
        if count:
            self.selection_hint.setText(f"已选择 {count} 个设备，将同时建立连接")
            self.selection_hint.setStyleSheet("")
        else:
            self.selection_hint.setText("勾选设备后可同时连接多个")
            self.selection_hint.setStyleSheet("")

    def _toggle_favorite(self, key: str) -> None:
        profile = self.config_store.config.devices.get(key)
        if profile is None:
            profile = self._transient_profiles.get(key)
            if profile is None:
                return
            profile.favorite = True
            self.config_store.config.devices[key] = profile
            self._transient_profiles.pop(key, None)
        else:
            profile.favorite = not profile.favorite
            if not profile.favorite and profile.last_connected <= 0:
                self.config_store.config.devices.pop(key, None)
                self._transient_profiles[key] = profile
        self.config_store.save()
        row = self._rows.get(key)
        if row is not None:
            row.update_profile(profile)
        self._refresh_favorites()
        self._update_counter()

    def _refresh_favorites(self) -> None:
        while self.fav_layout.count():
            item = self.fav_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._favorites.clear()
        profiles = sorted(
            self.config_store.config.devices.values(),
            key=lambda p: (p.favorite, p.last_connected),
            reverse=True,
        )
        shown = 0
        for profile in profiles:
            if not profile.favorite and profile.last_connected <= 0:
                continue
            row = FavoriteRow(profile, profile.key in self.connected_keys, self.fav_container)
            row.connect_requested.connect(self._connect_profile)
            row.favorite_requested.connect(self._toggle_favorite_profile)
            self.fav_layout.addWidget(row)
            self._favorites.append(row)
            shown += 1
            if shown >= 12:
                break
        if not shown:
            empty = QLabel("收藏设备后会出现在这里，\n下次连接无需重新搜索。")
            empty.setAlignment(Qt.AlignCenter)
            empty.setProperty("role", "muted")
            empty.setWordWrap(True)
            self.fav_layout.addWidget(empty)
            self.fav_empty = empty
        else:
            self.fav_empty = None
        self.fav_layout.addStretch(1)

    def _toggle_favorite_profile(self, key: str) -> None:
        profile = self.config_store.config.devices.get(key)
        if profile is None:
            return
        profile.favorite = not profile.favorite
        self.config_store.save()
        self._refresh_favorites()
        row = self._rows.get(key)
        if row is not None:
            row.update_profile(profile)

    def _connect_profile(self, profile: DeviceProfile) -> None:
        if profile.key in self.connected_keys:
            return
        info = DiscoveredDevice(
            address=profile.address,
            name=profile.display_name,
            has_heart_rate=True,
        )
        self.result_devices = [info]
        self.accept()

    # -- search / close ----------------------------------------------------
    def _matches(self, query: str, *values: str) -> bool:
        if not query:
            return True
        text = " ".join(v or "" for v in values).lower()
        return query.lower() in text

    def _on_search(self, text: str) -> None:
        self._query = text.strip()
        for row in self._rows.values():
            row.setVisible(self._matches(self._query, row.info.name, row.info.address))
        for row in self._favorites:
            row.setVisible(self._matches(self._query, row.profile.name, row.profile.address))

    def closeEvent(self, event) -> None:
        try:
            self.ble.stop_scan()
        except Exception:
            pass
        super().closeEvent(event)

    def reject(self) -> None:
        try:
            self.ble.stop_scan()
        except Exception:
            pass
        super().reject()
