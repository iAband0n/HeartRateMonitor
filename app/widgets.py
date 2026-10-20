"""Reusable widgets for the main window: device cards and empty states."""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .charts import HeartChart
from .models import DeviceProfile, format_ago, pretty_address
from .theme import heart_pixmap


class ElidedLabel(QLabel):
    """QLabel that ellides long text instead of forcing its card wider."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self.setToolTip(text)
        self._refresh_elide()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._refresh_elide()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_elide()

    def _refresh_elide(self) -> None:
        metrics = QFontMetrics(self.font())
        available = max(8, self.width() - 2)
        display = metrics.elidedText(self._full_text, Qt.ElideRight, available)
        super().setText(display)



class DeviceCard(QFrame):
    select_requested = Signal(str)
    connect_requested = Signal(str)
    disconnect_requested = Signal(str)
    overlay_requested = Signal(str)
    lock_requested = Signal(str)
    style_requested = Signal(str)
    favorite_requested = Signal(str)
    forget_requested = Signal(str)
    auto_reconnect_requested = Signal(str, bool)

    def __init__(self, profile: DeviceProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.key = profile.key
        self._selected = False
        self.setObjectName("DeviceCard")
        self.setProperty("selected", False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._build()
        self.update_from(profile, {})

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 12, 12)
        outer.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(9)
        self.avatar = QLabel("❤")
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setFixedSize(38, 38)
        self.avatar.setStyleSheet(
            "background: rgba(255,59,92,0.13); border: 1px solid rgba(255,59,92,0.22);"
            "border-radius: 19px; color: #FF5C77; font-size: 19px;"
        )
        top.addWidget(self.avatar)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        self.name_label = ElidedLabel("未命名设备")
        self.name_label.setProperty("role", "h2")
        self.name_label.setStyleSheet("font-size: 14px;")
        self.meta_label = ElidedLabel("—")
        self.meta_label.setProperty("role", "dim")
        text_box.addWidget(self.name_label)
        text_box.addWidget(self.meta_label)
        top.addLayout(text_box, 1)

        self.star_button = QToolButton()
        self.star_button.setObjectName("Star")
        self.star_button.setCursor(Qt.PointingHandCursor)
        self.star_button.setToolTip("收藏设备，下次可从收藏列表快速连接")
        self.star_button.clicked.connect(lambda: self.favorite_requested.emit(self.key))
        top.addWidget(self.star_button, 0, Qt.AlignTop)

        self.menu_button = QToolButton()
        self.menu_button.setObjectName("IconButton")
        self.menu_button.setText("⋯")
        self.menu_button.setToolTip("更多操作")
        self.menu_button.setCursor(Qt.PointingHandCursor)
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        self._menu = QMenu(self.menu_button)
        self.auto_action = QAction("自动重连", self._menu)
        self.auto_action.setCheckable(True)
        self.auto_action.toggled.connect(
            lambda checked: self.auto_reconnect_requested.emit(self.key, checked)
        )
        self.connect_action = QAction("连接", self._menu)
        self.connect_action.triggered.connect(lambda: self.connect_requested.emit(self.key))
        self.disconnect_action = QAction("断开连接", self._menu)
        self.disconnect_action.triggered.connect(lambda: self.disconnect_requested.emit(self.key))
        self.style_action = QAction("悬浮窗样式…", self._menu)
        self.style_action.triggered.connect(lambda: self.style_requested.emit(self.key))
        self.star_action = QAction("收藏 / 取消收藏", self._menu)
        self.star_action.triggered.connect(lambda: self.favorite_requested.emit(self.key))
        self.forget_action = QAction("忘记此设备", self._menu)
        self.forget_action.triggered.connect(lambda: self.forget_requested.emit(self.key))
        self._menu.addAction(self.connect_action)
        self._menu.addAction(self.disconnect_action)
        self._menu.addAction(self.auto_action)
        self._menu.addSeparator()
        self._menu.addAction(self.star_action)
        self._menu.addAction(self.style_action)
        self._menu.addSeparator()
        self._menu.addAction(self.forget_action)
        self.menu_button.setMenu(self._menu)
        top.addWidget(self.menu_button, 0, Qt.AlignTop)
        outer.addLayout(top)

        metric = QHBoxLayout()
        metric.setSpacing(4)
        self.bpm_label = QLabel("—")
        self.bpm_label.setProperty("role", "bpm")
        self.bpm_label.setStyleSheet("font-size: 38px;")
        self.unit_label = QLabel("BPM")
        self.unit_label.setProperty("role", "unit")
        metric.addWidget(self.bpm_label)
        metric.addWidget(self.unit_label, 0, Qt.AlignBottom)
        metric.addStretch(1)
        self.battery_label = QLabel("")
        self.battery_label.setProperty("role", "chip")
        metric.addWidget(self.battery_label, 0, Qt.AlignVCenter)
        self.status_label = QLabel("未连接")
        self.status_label.setProperty("state", "idle")
        metric.addWidget(self.status_label, 0, Qt.AlignVCenter)
        outer.addLayout(metric)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.primary_button = QPushButton("连接")
        self.primary_button.setCursor(Qt.PointingHandCursor)
        self.primary_button.clicked.connect(self._on_primary)
        self.lock_button = QPushButton("锁定")
        self.lock_button.setCursor(Qt.PointingHandCursor)
        self.lock_button.clicked.connect(lambda: self.lock_requested.emit(self.key))
        self.style_button = QPushButton("Aa")
        self.style_button.setObjectName("Chip")
        self.style_button.setFixedWidth(32)
        self.style_button.setCursor(Qt.PointingHandCursor)
        self.style_button.setToolTip("自定义悬浮窗的文本、字体、颜色、间距")
        self.style_button.clicked.connect(lambda: self.style_requested.emit(self.key))
        actions.addWidget(self.primary_button, 1)
        actions.addWidget(self.lock_button, 1)
        actions.addWidget(self.style_button, 0)
        for button in (self.primary_button, self.lock_button):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        outer.addLayout(actions)

    def _on_primary(self) -> None:
        if getattr(self, "_connected", False):
            self.overlay_requested.emit(self.key)
        else:
            self.connect_requested.emit(self.key)

    def update_from(self, profile: DeviceProfile, session: dict[str, Any]) -> None:
        self.profile = profile
        self._connected = bool(session.get("connected", False))
        state = str(session.get("state", "disconnected"))
        bpm = int(session.get("bpm", 0) or 0)
        battery = session.get("battery")
        has_overlay = bool(session.get("overlay_visible", profile.overlay_visible))
        locked = bool(session.get("overlay_locked", profile.overlay_locked))

        self.name_label.setText(profile.display_name)
        address = pretty_address(profile.address)
        last = format_ago(profile.last_connected)
        meta = f"{address} · {last}" if profile.address else last
        self.meta_label.setText(meta)
        self.meta_label.setToolTip(
            f"{profile.display_name}\n{profile.address}\n上次连接：{last}"
            + (f"\n状态：{session.get('message')}" if session.get("message") else "")
        )

        if self._connected and bpm > 0:
            self.bpm_label.setText(str(bpm))
            self.bpm_label.setStyleSheet("font-size: 38px; color: #FFFFFF;")
        elif self._connected:
            self.bpm_label.setText("—")
            self.bpm_label.setStyleSheet("font-size: 38px; color: #8D99AC;")
        else:
            self.bpm_label.setText("—")
            self.bpm_label.setStyleSheet("font-size: 38px; color: #4F5A6C;")

        self.battery_label.setText(f"⚡ {battery}%" if battery is not None else "")
        self.battery_label.setVisible(battery is not None)

        state_map = {
            "connected": ("已连接", "ok", "#4ADE80"),
            "connecting": ("连接中…", "warn", "#FBBF24"),
            "reconnecting": ("重连中…", "warn", "#FBBF24"),
            "error": ("连接失败", "error", "#F87171"),
            "disconnected": ("未连接", "idle", "#8D99AC"),
        }
        text, state_prop, status_color = state_map.get(state, ("未连接", "idle", "#8D99AC"))
        if not self._connected and state in {"disconnected", "error"} and profile.favorite:
            text = "已收藏"
        self.status_label.setText(f"● {text}")
        self.status_label.setProperty("state", state_prop)
        self.status_label.setStyleSheet(f"color: {status_color}; font-size: 11px;")
        self.status_label.setToolTip(session.get("message", ""))

        self.star_button.setText("★" if profile.favorite else "☆")
        self.star_button.setProperty("favorite", bool(profile.favorite))
        self.star_button.style().unpolish(self.star_button)
        self.star_button.style().polish(self.star_button)

        self.primary_button.setText(
            ("隐藏悬浮窗" if has_overlay else "显示悬浮窗") if self._connected else "连接"
        )
        self.primary_button.setObjectName("Primary")
        self.primary_button.style().unpolish(self.primary_button)
        self.primary_button.style().polish(self.primary_button)
        self.lock_button.setText("解锁" if locked else "锁定")
        self.lock_button.setEnabled(has_overlay)
        self.lock_button.setToolTip(
            "锁定后悬浮窗点击穿透，不会挡住游戏操作"
            if not locked
            else "解锁后可拖动和调整"
        )
        self.auto_action.blockSignals(True)
        self.auto_action.setChecked(bool(profile.auto_reconnect))
        self.auto_action.blockSignals(False)
        self.connect_action.setVisible(not self._connected)
        self.disconnect_action.setVisible(self._connected)
        self.forget_action.setToolTip("从常用设备中移除（历史记录仍保留）")

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.select_requested.emit(self.key)
        super().mousePressEvent(event)


class MultiDeviceCard(QFrame):
    """Compact live card used by the multi-device dashboard."""

    select_requested = Signal(str)
    detail_requested = Signal(str)
    overlay_requested = Signal(str)
    lock_requested = Signal(str)
    style_requested = Signal(str)

    def __init__(self, profile: DeviceProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.key = profile.key
        self._selected = False
        self.setObjectName("MultiCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._build()
        self.update_from(profile, {}, [], {}, [], "30 分钟", 1800, 2.0)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        avatar = QLabel("❤")
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(30, 30)
        avatar.setStyleSheet(
            "background: rgba(255,59,92,0.13); border: 1px solid rgba(255,59,92,0.22);"
            "border-radius: 15px; color: #FF5C77; font-size: 15px;"
        )
        top.addWidget(avatar)
        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        self.name_label = ElidedLabel("未命名设备")
        self.name_label.setStyleSheet("font-size: 13px; font-weight: 700;")
        self.meta_label = ElidedLabel("—")
        self.meta_label.setProperty("role", "dim")
        text_box.addWidget(self.name_label)
        text_box.addWidget(self.meta_label)
        top.addLayout(text_box, 1)
        self.status_label = QLabel("● 未连接")
        self.status_label.setStyleSheet("color: #8D99AC; font-size: 10px;")
        top.addWidget(self.status_label)
        self.battery_label = QLabel("")
        self.battery_label.setProperty("role", "chip")
        top.addWidget(self.battery_label)
        outer.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(8)
        bpm_box = QVBoxLayout()
        bpm_box.setSpacing(0)
        bpm_row = QHBoxLayout()
        bpm_row.setSpacing(3)
        self.bpm_label = QLabel("—")
        self.bpm_label.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 34px; font-weight: 800; color: #4F5A6C;"
        )
        unit = QLabel("BPM")
        unit.setProperty("role", "unit")
        bpm_row.addWidget(self.bpm_label)
        bpm_row.addWidget(unit, 0, Qt.AlignBottom)
        bpm_box.addLayout(bpm_row)
        self.update_label = QLabel("等待数据…")
        self.update_label.setProperty("role", "dim")
        bpm_box.addWidget(self.update_label)
        bpm_box.addStretch(1)
        body.addLayout(bpm_box, 0)
        self.chart = HeartChart(compact=True)
        self.chart.setMinimumHeight(72)
        self.chart.set_empty_text("等待心率…")
        body.addWidget(self.chart, 1)
        outer.addLayout(body, 2)

        stats = QHBoxLayout()
        stats.setSpacing(4)
        self.stat_values: dict[str, QLabel] = {}
        for caption in ("最低", "平均", "最高", "采样"):
            box = QVBoxLayout()
            box.setSpacing(0)
            value = QLabel("—")
            value.setStyleSheet(
                "font-family: 'Segoe UI'; font-size: 17px; font-weight: 700; color: #EEF2F8;"
            )
            label = QLabel(caption)
            label.setProperty("role", "dim")
            label.setStyleSheet("font-size: 9px;")
            box.addWidget(value)
            box.addWidget(label)
            stats.addLayout(box, 1)
            self.stat_values[caption] = value
        outer.addLayout(stats)

        history_header = QHBoxLayout()
        history_header.setSpacing(6)
        self.history_label = QLabel("历史 · 30 分钟")
        self.history_label.setProperty("role", "muted")
        self.history_label.setStyleSheet("font-size: 10px;")
        history_header.addWidget(self.history_label)
        history_header.addStretch(1)
        self.history_count = QLabel("")
        self.history_count.setProperty("role", "dim")
        history_header.addWidget(self.history_count)
        outer.addLayout(history_header)
        self.history_chart = HeartChart(compact=True, time_labels=True)
        self.history_chart.setMinimumHeight(104)
        self.history_chart.set_empty_text("暂无历史数据")
        outer.addWidget(self.history_chart, 2)

        actions = QHBoxLayout()
        actions.setSpacing(5)
        self.detail_button = QPushButton("详情")
        self.detail_button.setObjectName("Chip")
        self.detail_button.clicked.connect(lambda: self.detail_requested.emit(self.key))
        self.overlay_button = QPushButton("悬浮窗")
        self.overlay_button.setObjectName("Chip")
        self.overlay_button.clicked.connect(lambda: self.overlay_requested.emit(self.key))
        self.lock_button = QPushButton("锁定")
        self.lock_button.setObjectName("Chip")
        self.lock_button.clicked.connect(lambda: self.lock_requested.emit(self.key))
        self.style_button = QPushButton("Aa")
        self.style_button.setObjectName("Chip")
        self.style_button.setFixedWidth(32)
        self.style_button.clicked.connect(lambda: self.style_requested.emit(self.key))
        for button in (self.detail_button, self.overlay_button, self.lock_button, self.style_button):
            button.setCursor(Qt.PointingHandCursor)
        actions.addWidget(self.detail_button)
        actions.addWidget(self.overlay_button, 1)
        actions.addWidget(self.lock_button)
        actions.addWidget(self.style_button)
        outer.addLayout(actions)

    def update_from(
        self,
        profile: DeviceProfile,
        session: dict,
        points: list[tuple[float, int]],
        stats: dict,
        history_points: list[tuple[float, int]],
        history_label: str = "30 分钟",
        history_range_sec: int = 1800,
        history_bucket: float = 2.0,
    ) -> None:
        self.profile = profile
        self.name_label.setText(profile.display_name)
        meta = pretty_address(profile.address)
        if profile.last_connected:
            meta += " · " + format_ago(profile.last_connected)
        self.meta_label.setText(meta)
        connected = bool(session.get("connected"))
        bpm = int(session.get("bpm") or 0)
        state = str(session.get("state", "disconnected"))
        battery = session.get("battery")

        if connected and bpm > 0:
            self.bpm_label.setText(str(bpm))
            self.bpm_label.setStyleSheet(
                "font-family: 'Segoe UI'; font-size: 34px; font-weight: 800; color: #EEF2F8;"
            )
        else:
            self.bpm_label.setText("—")
            self.bpm_label.setStyleSheet(
                "font-family: 'Segoe UI'; font-size: 34px; font-weight: 800; color: #4F5A6C;"
            )
        self.chart.set_points(points, range_sec=180, bucket=1.0)
        self.stat_values["最低"].setText(str(stats.get("min") or "—"))
        self.stat_values["平均"].setText(str(stats.get("avg") or "—"))
        self.stat_values["最高"].setText(str(stats.get("max") or "—"))
        self.stat_values["采样"].setText(str(stats.get("count") or "—"))
        self.history_chart.set_points(
            history_points,
            range_sec=history_range_sec,
            bucket=history_bucket,
        )
        self.history_label.setText("历史 · " + history_label)
        self.history_count.setText(f"{len(history_points)} 点")
        last = session.get("last_update")
        if last:
            self.update_label.setText("更新 " + time.strftime("%H:%M:%S", time.localtime(last)))
        else:
            self.update_label.setText("等待数据…" if connected else "未连接")
        self.battery_label.setText(f"⚡ {battery}%" if battery is not None else "")
        self.battery_label.setVisible(battery is not None)

        state_map = {
            "connected": ("● 已连接", "#4ADE80"),
            "connecting": ("● 连接中", "#FBBF24"),
            "reconnecting": ("● 重连中", "#FBBF24"),
            "error": ("● 失败", "#F87171"),
            "disconnected": ("● 未连接", "#8D99AC"),
        }
        text, color = state_map.get(state, ("● 未连接", "#8D99AC"))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 10px;")

        has_overlay = bool(session.get("overlay_visible"))
        locked = bool(session.get("overlay_locked"))
        self.overlay_button.setText("隐藏悬浮窗" if has_overlay else "显示悬浮窗")
        self.lock_button.setText("解锁" if locked else "锁定")
        self.lock_button.setEnabled(has_overlay)

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.select_requested.emit(self.key)
        super().mousePressEvent(event)


class EmptyState(QWidget):
    action_requested = Signal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        button_text: str = "",
        icon: QPixmap | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(10)
        layout.addStretch(1)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        if icon is None:
            icon = heart_pixmap(72)
        icon_label.setPixmap(
            icon.scaled(84, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        layout.addWidget(icon_label)
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title_label)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setWordWrap(True)
        subtitle_label.setProperty("role", "muted")
        layout.addWidget(subtitle_label)
        if button_text:
            button = QPushButton(button_text)
            button.setObjectName("Primary")
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedWidth(150)
            button.clicked.connect(self.action_requested.emit)
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(button)
            row.addStretch(1)
            layout.addLayout(row)
        layout.addStretch(1)


class IconBadge(QLabel):
    def __init__(self, text: str = "❤", size: int = 42, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(size, size)
        self.setStyleSheet(
            "background: rgba(255,59,92,0.13); border: 1px solid rgba(255,59,92,0.22);"
            f"border-radius: {size // 2}px; color: #FF5C77; font-size: {int(size * 0.46)}px;"
        )
