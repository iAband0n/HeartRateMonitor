"""Hand-painted charts and small metric widgets (no charting dependency)."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .theme import ACCENT, TEXT, TEXT_DIM, TEXT_MUTED


class HeartChart(QWidget):
    """A compact, antialiased time-series chart with hover inspection."""

    def __init__(
        self,
        parent: QWidget | None = None,
        compact: bool = False,
        time_labels: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self._points: list[tuple[float, int]] = []
        self._range_sec = 300
        self._bucket = 1.0
        self._empty_text = "等待心率数据…"
        self._line_color = QColor(ACCENT)
        self._hover_index: int | None = None
        self._hover_pos: QPoint | None = None
        self._plot_rect = QRectF()
        self._start = 0.0
        self._end = 0.0
        self._visible: list[tuple[float, int]] = []
        self._compact = bool(compact)
        self._time_labels = (not self._compact) if time_labels is None else bool(time_labels)
        self.setMouseTracking(True)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_points(
        self,
        points: list[tuple[float, int]],
        range_sec: int | None = None,
        bucket: float | None = None,
    ) -> None:
        self._points = list(points or [])
        if range_sec is not None:
            self._range_sec = max(0, int(range_sec))
        if bucket is not None:
            self._bucket = max(0.2, float(bucket))
        self._hover_index = None
        self.update()

    def set_empty_text(self, text: str) -> None:
        self._empty_text = text
        self.update()

    def set_line_color(self, value: str) -> None:
        self._line_color = QColor(value)
        self.update()

    # -- geometry helpers --------------------------------------------------
    def _domain(self) -> tuple[float, float]:
        now = time.time()
        if self._range_sec <= 0:
            if not self._points:
                return now - 300, now
            return self._points[0][0], max(self._points[-1][0], self._points[0][0] + 1)
        return now - self._range_sec, now

    def _visible_points(self, start: float, end: float) -> list[tuple[float, int]]:
        return [p for p in self._points if start - 0.5 <= p[0] <= end + 0.5]

    def _x_for(self, ts: float, rect: QRectF, start: float, end: float) -> float:
        span = max(1e-6, end - start)
        return rect.left() + (ts - start) / span * rect.width()

    def _y_for(self, bpm: float, rect: QRectF, lo: float, hi: float) -> float:
        span = max(1e-6, hi - lo)
        return rect.bottom() - (bpm - lo) / span * rect.height()

    @staticmethod
    def _time_label(ts: float, span: float) -> str:
        if span <= 3600:
            return time.strftime("%H:%M:%S", time.localtime(ts))
        if span <= 86400 * 2:
            return time.strftime("%H:%M", time.localtime(ts))
        return time.strftime("%m-%d", time.localtime(ts))

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        widget_rect = QRectF(self.rect())
        if self._time_labels:
            bottom_margin = 24 if self._compact else 28
        else:
            bottom_margin = 8
        left_margin = 38 if self._compact else 46
        plot = QRectF(
            left_margin,
            14,
            max(10.0, widget_rect.width() - left_margin - 18),
            max(10.0, widget_rect.height() - 14 - bottom_margin),
        )
        self._plot_rect = plot
        start, end = self._domain()
        self._start, self._end = start, end
        visible = self._visible_points(start, end)
        self._visible = visible

        # Background.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawRect(widget_rect)

        # Y range from visible points (or a calm default).
        if visible:
            lows = [p[1] for p in visible]
            highs = [p[1] for p in visible]
            low_data, high_data = min(lows), max(highs)
            lo = max(30, int(math.floor((low_data - 8) / 10.0)) * 10)
            hi = min(230, int(math.ceil((high_data + 8) / 10.0)) * 10)
        else:
            lo, hi = 50, 150
        if hi - lo < 30:
            hi = lo + 30
        if hi - lo > 140:
            mid = (hi + lo) / 2
            lo, hi = int(mid - 70), int(mid + 70)

        grid_pen = QPen(QColor(255, 255, 255, 13))
        grid_pen.setWidthF(1.0)
        text_font = QFont("Segoe UI")
        text_font.setPixelSize(10)
        painter.setFont(text_font)

        # Horizontal grid + BPM labels.
        for i in range(5):
            frac = i / 4.0
            y = plot.bottom() - frac * plot.height()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            label = str(int(round(lo + frac * (hi - lo))))
            painter.setPen(QColor(TEXT_DIM))
            painter.drawText(
                QRectF(0, y - 8, plot.left() - 10, 16),
                Qt.AlignRight | Qt.AlignVCenter,
                label,
            )

        # Vertical grid + time labels.
        span = max(1e-6, end - start)
        label_indices = {0, 2, 4} if self._compact else {0, 1, 2, 3, 4}
        for i in range(5):
            frac = i / 4.0
            x = plot.left() + frac * plot.width()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            if not self._time_labels or i not in label_indices:
                continue
            ts = start + frac * span
            label = self._time_label(ts, span)
            painter.setPen(QColor(TEXT_DIM))
            if i == 0:
                rect = QRectF(x, plot.bottom() + 5, 64, 16)
                align = Qt.AlignLeft | Qt.AlignVCenter
            elif i == 4:
                rect = QRectF(x - 64, plot.bottom() + 5, 64, 16)
                align = Qt.AlignRight | Qt.AlignVCenter
            else:
                rect = QRectF(x - 34, plot.bottom() + 5, 68, 16)
                align = Qt.AlignHCenter | Qt.AlignVCenter
            painter.drawText(rect, align, label)

        if not visible:
            painter.setPen(QColor(TEXT_MUTED))
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(plot, Qt.AlignCenter, self._empty_text)
            painter.end()
            return

        # Split into segments so a disconnect does not draw a fake straight line.
        gap = max(8.0, self._bucket * 3.0)
        segments: list[list[tuple[float, int]]] = []
        current: list[tuple[float, int]] = []
        for point in visible:
            if current and point[0] - current[-1][0] > gap:
                if len(current) >= 1:
                    segments.append(current)
                current = []
            current.append(point)
        if current:
            segments.append(current)

        for segment in segments:
            if len(segment) < 2:
                continue
            line_path = QPainterPath()
            first = True
            for ts, bpm in segment:
                px = self._x_for(ts, plot, start, end)
                py = self._y_for(bpm, plot, lo, hi)
                if first:
                    line_path.moveTo(px, py)
                    first = False
                else:
                    line_path.lineTo(px, py)
            area_path = QPainterPath(line_path)
            area_path.lineTo(self._x_for(segment[-1][0], plot, start, end), plot.bottom())
            area_path.lineTo(self._x_for(segment[0][0], plot, start, end), plot.bottom())
            area_path.closeSubpath()
            gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
            top_color = QColor(self._line_color)
            top_color.setAlpha(70)
            bottom_color = QColor(self._line_color)
            bottom_color.setAlpha(0)
            gradient.setColorAt(0.0, top_color)
            gradient.setColorAt(1.0, bottom_color)
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawPath(area_path)
            pen = QPen(self._line_color)
            pen.setWidthF(2.2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(line_path)

        # Latest marker + subtle halo.
        last_ts, last_bpm = visible[-1]
        last_x = self._x_for(last_ts, plot, start, end)
        last_y = self._y_for(last_bpm, plot, lo, hi)
        halo = QColor(self._line_color)
        halo.setAlpha(45)
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(last_x, last_y), 8.0, 8.0)
        painter.setBrush(self._line_color)
        painter.drawEllipse(QPointF(last_x, last_y), 3.2, 3.2)

        # Hover crosshair.
        if self._hover_index is not None and 0 <= self._hover_index < len(visible):
            hts, hbpm = visible[self._hover_index]
            hx = self._x_for(hts, plot, start, end)
            hy = self._y_for(hbpm, plot, lo, hi)
            dash = QPen(QColor(255, 255, 255, 55))
            dash.setStyle(Qt.DashLine)
            painter.setPen(dash)
            painter.drawLine(QPointF(hx, plot.top()), QPointF(hx, plot.bottom()))
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._line_color)
            painter.drawEllipse(QPointF(hx, hy), 4.0, 4.0)
            label = f"{self._time_label(hts, span)}   {hbpm} BPM"
            label_font = QFont("Microsoft YaHei UI")
            label_font.setPixelSize(10)
            painter.setFont(label_font)
            lm = QFontMetricsF(label_font)
            width = lm.horizontalAdvance(label) + 16
            height = lm.height() + 10
            bx = min(max(plot.left(), hx - width / 2), plot.right() - width)
            by = max(plot.top(), hy - height - 10)
            bubble = QRectF(bx, by, width, height)
            painter.setBrush(QColor(24, 31, 43, 238))
            painter.setPen(QPen(QColor(63, 76, 96), 1))
            painter.drawRoundedRect(bubble, 6, 6)
            painter.setPen(QColor(TEXT))
            painter.drawText(bubble, Qt.AlignCenter, label)

        painter.end()

    # -- hover -------------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        self._hover_pos = pos
        if not self._plot_rect.contains(pos) or not self._visible:
            if self._hover_index is not None:
                self._hover_index = None
                self.update()
            return
        target_x = pos.x()
        best_index = None
        best_distance = 1e9
        for index, (ts, _bpm) in enumerate(self._visible):
            x = self._x_for(ts, self._plot_rect, self._start, self._end)
            distance = abs(x - target_x)
            if distance < best_distance:
                best_distance = distance
                best_index = index
        if best_index != self._hover_index:
            self._hover_index = best_index
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover_index = None
        self._hover_pos = None
        self.update()
        super().leaveEvent(event)


class StatTile(QFrame):
    def __init__(self, label: str, unit: str = "BPM", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SubtleCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.value_label = QLabel("—")
        self.value_label.setProperty("role", "metric")
        self.caption = QLabel(label)
        self.caption.setProperty("role", "muted")
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(4)
        bottom.addWidget(self.caption)
        bottom.addStretch(1)
        if unit:
            unit_label = QLabel(unit)
            unit_label.setProperty("role", "dim")
            bottom.addWidget(unit_label)
        layout.addWidget(self.value_label)
        layout.addLayout(bottom)
        self.setMinimumWidth(92)

    def set_value(self, value: int | str, suffix: str = "") -> None:
        if isinstance(value, int) and value <= 0:
            self.value_label.setText("—")
        else:
            self.value_label.setText(f"{value}{suffix}")
