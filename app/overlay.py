"""Frameless, translucent, always-on-top heart-rate overlay window.

Interaction model:
* drag anywhere on the frame (except corner handles / control buttons)
* four corner handles resize the frame; the text scales with the content area
* a small control bar at bottom-centre provides lock / hide
* when locked the window is click-through and the controls disappear
"""

from __future__ import annotations

import logging
import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QPushButton, QWidget

from . import win32_utils
from .models import DisplayConfig
from .render import build_layout, paint_display

log = logging.getLogger(__name__)

CONTROL_BAR_HEIGHT = 32
HANDLE_SIZE = 9.0
HANDLE_INSET = 7.0
HANDLE_HIT = 15


class HeartOverlay(QWidget):
    lock_changed = Signal(str, bool)
    closed = Signal(str)
    style_requested = Signal(str)
    position_changed = Signal(str, int, int)
    size_changed = Signal(str, int, int)  # width, height; 0,0 = auto size
    bring_to_front = Signal(str)

    def __init__(
        self,
        device_key: str,
        device_name: str,
        display: DisplayConfig,
        *,
        bpm: int = 0,
        battery: int | None = None,
        connected: bool = False,
        locked: bool = False,
        topmost_enhance: bool = True,
        topmost_interval_ms: int = 1200,
        position: QPoint | None = None,
        size: QSize | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.device_key = device_key
        self.device_name = device_name
        self.display = display.normalized()
        self._bpm = int(bpm or 0)
        self._battery = battery
        self._connected = connected
        self._locked = locked
        self._topmost_enhance = topmost_enhance
        self._drag_offset: QPoint | None = None
        self._resize_corner: str | None = None
        self._resize_start_rect: QRect | None = None
        self._resize_start_global: QPoint | None = None
        self._custom_size = (
            QSize(int(size.width()), int(size.height()))
            if size is not None and size.width() > 0 and size.height() > 0
            else None
        )
        self._hover = False

        flags = (
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip("拖动移动 · 四角缩放 · 下方按钮可锁定/隐藏")
        self.setCursor(Qt.OpenHandCursor)

        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(max(300, int(topmost_interval_ms)))
        self._topmost_timer.timeout.connect(self._enforce_topmost)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._emit_position)

        self._build_controls()
        self._apply_size()
        if position is not None:
            self.move(position)
        self._position_controls()
        self.set_locked(locked, emit=False)

    # -- controls ---------------------------------------------------------
    def _build_controls(self) -> None:
        self.controls = QFrame(self)
        self.controls.setObjectName("OverlayControls")
        layout = QHBoxLayout(self.controls)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(1)
        self.lock_button = QPushButton("锁定", self.controls)
        self.lock_button.setToolTip("锁定后悬浮窗点击穿透，可在主窗口/托盘/快捷键解锁")
        self.hide_button = QPushButton("隐藏", self.controls)
        self.hide_button.setToolTip("隐藏悬浮窗，可从主窗口或托盘重新显示")
        for button in (self.lock_button, self.hide_button):
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            button.setFixedHeight(22)
        self.lock_button.clicked.connect(self.toggle_lock)
        self.hide_button.clicked.connect(self._request_hide)
        layout.addWidget(self.lock_button)
        layout.addWidget(self.hide_button)
        self.controls.adjustSize()

    def _position_controls(self) -> None:
        if not hasattr(self, "controls"):
            return
        self.controls.adjustSize()
        hint = self.controls.sizeHint()
        width = min(max(84, hint.width()), max(84, self.width()))
        height = min(max(24, hint.height()), CONTROL_BAR_HEIGHT - 4)
        x = (self.width() - width) // 2
        y = self.height() - height - 4
        self.controls.setGeometry(x, y, width, height)
        self.controls.raise_()

    def _request_hide(self) -> None:
        self.closed.emit(self.device_key)
        self.hide()

    # -- state -------------------------------------------------------------
    @property
    def locked(self) -> bool:
        return self._locked

    @property
    def custom_size(self) -> QSize | None:
        return QSize(self._custom_size) if self._custom_size is not None else None

    def _layout(self):
        return build_layout(
            self.display,
            self._bpm if self._connected else 0,
            self.device_name,
            self._battery,
            self._connected,
        )

    def _content_rect(self) -> QRectF:
        return QRectF(0, 0, self.width(), max(1, self.height() - CONTROL_BAR_HEIGHT))

    def _minimum_size(self) -> QSize:
        layout = self._layout()
        width = max(56, int(math.ceil(layout.box_width)))
        height = max(34, int(math.ceil(layout.box_height))) + CONTROL_BAR_HEIGHT
        return QSize(width, height)

    def _apply_size(self) -> bool:
        minimum = self._minimum_size()
        if self._custom_size is None:
            target = minimum
        else:
            target = QSize(
                max(minimum.width(), int(self._custom_size.width())),
                max(minimum.height(), int(self._custom_size.height())),
            )
            self._custom_size = QSize(target)
        changed = self.size() != target
        if changed:
            self.resize(target)
        self._position_controls()
        return changed

    def sizeHint(self) -> QSize:
        return self._minimum_size()

    def set_display(self, display: DisplayConfig) -> None:
        self.display = display.normalized()
        self.setWindowOpacity(self.display.opacity)
        self._apply_size()
        self.update()

    def set_device_name(self, name: str) -> None:
        if name and name != self.device_name:
            self.device_name = name
            self._apply_size()
            self.update()

    def set_data(self, bpm: int, connected: bool, battery: int | None = None) -> None:
        changed = (bpm != self._bpm) or (connected != self._connected) or (battery != self._battery)
        self._bpm = int(bpm or 0)
        self._connected = bool(connected)
        self._battery = battery
        if changed:
            self._apply_size()
            self.update()

    def set_connected(self, connected: bool) -> None:
        self.set_data(0 if not connected else self._bpm, connected, self._battery)

    def set_locked(self, locked: bool, emit: bool = True) -> None:
        self._locked = bool(locked)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self._locked)
        self._drag_offset = None
        self._resize_corner = None
        self.controls.setVisible(not self._locked)
        self.lock_button.setText("锁定")
        if self._locked:
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        hwnd = win32_utils.hwnd_of(self)
        win32_utils.apply_overlay_styles(hwnd, self._locked, topmost=True)
        self.setToolTip(
            "已锁定：点击穿透，请从主窗口、托盘或 Ctrl+Alt+L 解锁"
            if self._locked
            else "拖动移动 · 四角缩放 · 下方按钮可锁定/隐藏"
        )
        self._position_controls()
        if emit:
            self.lock_changed.emit(self.device_key, self._locked)
        self.update()

    def toggle_lock(self) -> None:
        self.set_locked(not self._locked)

    def reset_size(self) -> None:
        self._custom_size = None
        self._apply_size()
        self.update()
        self.size_changed.emit(self.device_key, 0, 0)

    def set_topmost_enhance(self, enabled: bool, interval_ms: int | None = None) -> None:
        self._topmost_enhance = bool(enabled)
        if interval_ms:
            self._topmost_timer.setInterval(max(300, int(interval_ms)))
        if enabled and self.isVisible():
            self._topmost_timer.start()
        else:
            self._topmost_timer.stop()
        self._enforce_topmost()

    def _enforce_topmost(self) -> None:
        if not self.isVisible():
            return
        hwnd = win32_utils.hwnd_of(self)
        win32_utils.apply_overlay_styles(hwnd, self._locked, topmost=True)

    # -- painting ----------------------------------------------------------
    def _handle_points(self) -> dict[str, QPointF]:
        content = self._content_rect()
        m = HANDLE_INSET
        return {
            "tl": QPointF(content.left() + m, content.top() + m),
            "tr": QPointF(content.right() - m, content.top() + m),
            "bl": QPointF(content.left() + m, content.bottom() - m),
            "br": QPointF(content.right() - m, content.bottom() - m),
        }

    def _corner_at(self, pos: QPoint) -> str | None:
        if self._locked:
            return None
        for corner, point in self._handle_points().items():
            if abs(pos.x() - point.x()) <= HANDLE_HIT and abs(pos.y() - point.y()) <= HANDLE_HIT:
                return corner
        return None

    def _cursor_for_corner(self, corner: str | None):
        if corner in ("tl", "br"):
            return Qt.SizeFDiagCursor
        if corner in ("tr", "bl"):
            return Qt.SizeBDiagCursor
        return Qt.OpenHandCursor

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        content = self._content_rect()
        layout = self._layout()
        scale = min(
            content.width() / max(1.0, layout.box_width),
            content.height() / max(1.0, layout.box_height),
        )
        if self._custom_size is None:
            scale = 1.0
        paint_display(
            painter,
            self.display,
            self._bpm if self._connected else 0,
            self.device_name,
            self._battery,
            self._connected,
            content,
            content_scale=max(0.1, scale),
        )

        if not self._locked:
            if self._hover:
                pen = QPen(QColor(255, 255, 255, 52))
                pen.setWidth(1)
                pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                inset = 1.5
                painter.drawRoundedRect(
                    content.adjusted(inset, inset, -inset, -inset),
                    max(2, self.display.radius),
                    max(2, self.display.radius),
                )
            # Four resize handles, visible whenever the overlay is unlocked.
            for point in self._handle_points().values():
                rect = QRectF(
                    point.x() - HANDLE_SIZE / 2,
                    point.y() - HANDLE_SIZE / 2,
                    HANDLE_SIZE,
                    HANDLE_SIZE,
                )
                painter.setPen(QPen(QColor(255, 59, 92, 190), 1))
                painter.setBrush(QColor(12, 16, 24, 220))
                painter.drawRoundedRect(rect, 2.5, 2.5)
        painter.end()

    # -- native window / visibility ---------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.setWindowOpacity(self.display.opacity)
        hwnd = win32_utils.hwnd_of(self)
        win32_utils.apply_overlay_styles(hwnd, self._locked, topmost=True)
        if self._topmost_enhance:
            self._topmost_timer.start()
        self.controls.setVisible(not self._locked)
        self._position_controls()
        QTimer.singleShot(30, self._after_show)

    def _after_show(self) -> None:
        self._enforce_topmost()
        self.ensure_on_screen()

    def hideEvent(self, event) -> None:
        self._topmost_timer.stop()
        super().hideEvent(event)

    def ensure_on_screen(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return
        rect = QRect(self.pos(), self.size())
        for screen in screens:
            if screen.availableGeometry().intersects(rect):
                return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 56, area.top() + 96)

    def closeEvent(self, event) -> None:
        self._topmost_timer.stop()
        self._emit_position()
        self.closed.emit(self.device_key)
        super().closeEvent(event)

    # -- interaction -------------------------------------------------------
    def enterEvent(self, event) -> None:
        self._hover = True
        if not self._locked:
            self.setCursor(Qt.OpenHandCursor)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._locked:
            event.ignore()
            return
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            corner = self._corner_at(pos)
            if corner is not None:
                self._resize_corner = corner
                self._resize_start_rect = QRect(self.geometry())
                self._resize_start_global = event.globalPosition().toPoint()
                self.setCursor(self._cursor_for_corner(corner))
                self.bring_to_front.emit(self.device_key)
                event.accept()
                return
            if self.controls.geometry().contains(pos):
                # Clicks on the control bar background are not drag gestures.
                event.ignore()
                return
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            self.bring_to_front.emit(self.device_key)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._locked:
            event.ignore()
            return
        if self._resize_corner is not None and self._resize_start_rect is not None:
            self._resize_to(
                self._resize_corner,
                self._resize_start_rect,
                event.globalPosition().toPoint() - (self._resize_start_global or QPoint(0, 0)),
            )
            event.accept()
            return
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        if self._hover:
            corner = self._corner_at(event.position().toPoint())
            self.setCursor(self._cursor_for_corner(corner))
        super().mouseMoveEvent(event)

    def _resize_to(self, corner: str, start: QRect, delta: QPoint) -> None:
        minimum = self._minimum_size()
        left = start.x()
        top = start.y()
        right = start.x() + start.width()
        bottom = start.y() + start.height()

        if "l" in corner:
            left += delta.x()
        if "r" in corner:
            right += delta.x()
        if "t" in corner:
            top += delta.y()
        if "b" in corner:
            bottom += delta.y()

        if right - left < minimum.width():
            if "l" in corner:
                left = right - minimum.width()
            else:
                right = left + minimum.width()
        if bottom - top < minimum.height():
            if "t" in corner:
                top = bottom - minimum.height()
            else:
                bottom = top + minimum.height()

        rect = QRect(QPoint(left, top), QPoint(right - 1, bottom - 1))
        self._custom_size = QSize(rect.width(), rect.height())
        self.setGeometry(rect)
        self.setCursor(self._cursor_for_corner(corner))
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._locked:
            event.ignore()
            return
        if event.button() == Qt.LeftButton and self._resize_corner is not None:
            self._resize_corner = None
            self._resize_start_rect = None
            self._resize_start_global = None
            self.setCursor(Qt.OpenHandCursor if self._hover else Qt.ArrowCursor)
            self.size_changed.emit(self.device_key, self.width(), self.height())
            self._save_timer.start()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.OpenHandCursor if self._hover else Qt.ArrowCursor)
            self._save_timer.start()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._locked:
            event.ignore()
            return
        if event.button() == Qt.LeftButton:
            if self._corner_at(event.position().toPoint()) is not None:
                event.ignore()
                return
            self.toggle_lock()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_controls()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.isVisible():
            self._save_timer.start()

    def _emit_position(self) -> None:
        self.position_changed.emit(self.device_key, self.x(), self.y())

    def contextMenuEvent(self, event) -> None:
        if self._locked:
            event.ignore()
            return
        menu = QMenu(self)
        lock_action = menu.addAction("锁定悬浮窗（点击穿透）")
        style_action = menu.addAction("悬浮窗样式…")
        menu.addSeparator()
        reset_size_action = menu.addAction("重置大小（自动适应）")
        reset_action = menu.addAction("重置位置")
        close_action = menu.addAction("隐藏悬浮窗")
        chosen = menu.exec(event.globalPos())
        if chosen is lock_action:
            self.toggle_lock()
        elif chosen is style_action:
            self.style_requested.emit(self.device_key)
        elif chosen is reset_size_action:
            self.reset_size()
        elif chosen is reset_action:
            screen = QGuiApplication.primaryScreen()
            if screen:
                area = screen.availableGeometry()
                self.move(area.center().x() - self.width() // 2, area.top() + 120)
                self._emit_position()
        elif chosen is close_action:
            self.closed.emit(self.device_key)
            self.hide()
