"""Application palette, Qt stylesheet and small icon helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap

from .storage import resource_path

CHECK_ICON = resource_path("assets/check.png").as_posix()
CHEVRON_UP = resource_path("assets/chevron_up.png").as_posix()
CHEVRON_DOWN = resource_path("assets/chevron_down.png").as_posix()

# Palette -------------------------------------------------------------------
BG = "#0B0F16"
BG_RAISED = "#0F141D"
SURFACE = "#141A24"
SURFACE_ALT = "#1A2130"
SURFACE_HOVER = "#202838"
BORDER = "#242D3C"
BORDER_SOFT = "#1D2532"
TEXT = "#EEF2F8"
TEXT_MUTED = "#8D99AC"
TEXT_DIM = "#5E6A7D"
ACCENT = "#FF3B5C"
ACCENT_HOVER = "#FF5C77"
ACCENT_SOFT = "rgba(255, 59, 92, 0.14)"
GREEN = "#4ADE80"
AMBER = "#FBBF24"
RED = "#F87171"
BLUE = "#60A5FA"

STYLE = f"""
* {{
    outline: none;
}}
QWidget {{
    color: {TEXT};
    font-family: "Microsoft YaHei UI", "Segoe UI", "Microsoft YaHei";
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background-color: {BG};
}}
QWidget#Root {{
    background-color: {BG};
}}
QFrame#Card {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#SubtleCard {{
    background-color: {SURFACE_ALT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 12px;
}}
QFrame#Header {{
    background-color: {BG_RAISED};
    border-bottom: 1px solid {BORDER_SOFT};
}}
QFrame#DeviceCard {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#DeviceCard:hover {{
    background-color: {SURFACE_ALT};
    border-color: #303B4E;
}}
QFrame#DeviceCard QPushButton {{
    padding: 7px 8px;
    font-size: 11px;
}}
QFrame#DeviceCard[selected="true"] {{
    background-color: #191F2C;
    border: 1px solid {ACCENT};
}}
QFrame#MultiCard {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#MultiCard:hover {{
    background-color: {SURFACE_ALT};
    border-color: #303B4E;
}}
QFrame#MultiCard[selected="true"] {{
    background-color: #191F2C;
    border: 1px solid {ACCENT};
}}
QFrame#MultiCard QPushButton {{
    padding: 5px 8px;
    font-size: 11px;
}}
QFrame#EmptyCard {{
    background-color: transparent;
    border: 1px dashed #2A3445;
    border-radius: 16px;
}}
QLabel {{
    background: transparent;
}}
QLabel[role="title"] {{
    font-size: 20px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel[role="h1"] {{
    font-size: 26px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel[role="h2"] {{
    font-size: 17px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel[role="muted"] {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel[role="dim"] {{
    color: {TEXT_DIM};
    font-size: 11px;
}}
QLabel[role="bpm"] {{
    color: {TEXT};
    font-size: 46px;
    font-weight: 800;
}}
QLabel[role="bpmBig"] {{
    color: {TEXT};
    font-size: 78px;
    font-weight: 800;
}}
QLabel[role="unit"] {{
    color: {TEXT_MUTED};
    font-size: 12px;
    font-weight: 600;
}}
QLabel[role="metric"] {{
    color: {TEXT};
    font-size: 22px;
    font-weight: 700;
}}
QLabel[role="chip"] {{
    background-color: {SURFACE_ALT};
    border-radius: 9px;
    color: {TEXT_MUTED};
    font-size: 11px;
    padding: 3px 8px;
}}
QLabel[role="chipAccent"] {{
    background-color: {ACCENT_SOFT};
    border-radius: 9px;
    color: {ACCENT_HOVER};
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
}}
QLabel[role="heart"] {{
    color: {ACCENT};
}}
QLabel[state="ok"] {{
    color: {GREEN};
    font-size: 12px;
}}
QLabel[state="warn"] {{
    color: {AMBER};
    font-size: 12px;
}}
QLabel[state="error"] {{
    color: {RED};
    font-size: 12px;
}}
QLabel[state="idle"] {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QPushButton {{
    background-color: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 9px;
    color: {TEXT};
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {SURFACE_HOVER};
    border-color: #334054;
}}
QPushButton:pressed {{
    background-color: #182030;
}}
QPushButton:disabled {{
    background-color: #121821;
    color: #4F5A6C;
    border-color: #1C2430;
}}
QPushButton#Primary {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: #FFFFFF;
    padding: 9px 18px;
    font-size: 13px;
}}
QPushButton#Primary:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#Primary:pressed {{
    background-color: #E22B4A;
}}
QPushButton#Primary:disabled {{
    background-color: #3B2028;
    border-color: #4A2932;
    color: #8A5C66;
}}
QPushButton#Ghost {{
    background-color: transparent;
    border: 1px solid {BORDER};
    color: {TEXT_MUTED};
}}
QPushButton#Ghost:disabled {{
    color: #4F5A6C;
    border-color: #1C2430;
}}
QPushButton#Ghost:hover {{
    background-color: {SURFACE_ALT};
    color: {TEXT};
}}
QPushButton#Danger {{
    background-color: rgba(248, 113, 113, 0.10);
    border: 1px solid rgba(248, 113, 113, 0.28);
    color: {RED};
}}
QPushButton#Danger:hover {{
    background-color: rgba(248, 113, 113, 0.18);
}}
QPushButton#Chip {{
    background-color: {SURFACE_ALT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 8px;
    padding: 5px 10px;
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QPushButton#Chip:hover {{
    color: {TEXT};
    border-color: {BORDER};
}}
QPushButton#SectionButton {{
    background: transparent;
    border: none;
    border-top: 1px solid {BORDER_SOFT};
    border-radius: 0px;
    color: {TEXT_MUTED};
    padding: 8px 2px 5px 2px;
    font-size: 11px;
    font-weight: 600;
    text-align: left;
}}
QPushButton#SectionButton:hover {{
    color: {TEXT};
    background: transparent;
    border-top-color: #334054;
}}
QPushButton#SectionButton:checked {{
    color: {TEXT_MUTED};
}}
QPushButton#RangeButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: {TEXT_MUTED};
    padding: 5px 9px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#RangeButton:hover {{
    color: {TEXT};
    background-color: {SURFACE_ALT};
}}
QPushButton#RangeButton:checked {{
    color: {ACCENT_HOVER};
    background-color: {ACCENT_SOFT};
    border-color: rgba(255, 59, 92, 0.22);
}}
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    color: {TEXT_MUTED};
    padding: 4px;
}}
QToolButton:hover {{
    background-color: {SURFACE_ALT};
    color: {TEXT};
}}
QToolButton#Star {{
    color: {TEXT_DIM};
    font-size: 18px;
    padding: 1px 4px;
}}
QToolButton#Star[favorite="true"] {{
    color: {AMBER};
}}
QToolButton#IconButton {{
    font-size: 16px;
    padding: 6px;
    border: 1px solid transparent;
}}
QToolButton#IconButton:hover {{
    border-color: {BORDER};
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {{
    background-color: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT};
    padding: 7px 9px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QSpinBox, QDoubleSpinBox {{
    padding-right: 27px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QFontComboBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    color: {TEXT_DIM};
}}
QComboBox, QFontComboBox {{
    padding-right: 26px;
}}
QComboBox::drop-down, QFontComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    border: none;
    width: 24px;
}}
QComboBox::down-arrow, QFontComboBox::down-arrow {{
    image: url("{CHEVRON_DOWN}");
    width: 10px;
    height: 6px;
}}
QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT};
    selection-background-color: {SURFACE_HOVER};
    padding: 4px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    width: 21px;
    background: transparent;
    border-left: 1px solid {BORDER};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-position: top right;
    height: 50%;
    border-top-right-radius: 7px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-position: bottom right;
    height: 50%;
    border-bottom-right-radius: 7px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {SURFACE_ALT};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{CHEVRON_UP}");
    width: 8px;
    height: 5px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{CHEVRON_DOWN}");
    width: 8px;
    height: 5px;
}}
QFrame#OverlayControls {{
    background-color: rgba(10, 14, 20, 210);
    border: 1px solid rgba(255, 255, 255, 34);
    border-radius: 11px;
}}
QFrame#OverlayControls QPushButton {{
    background: transparent;
    border: none;
    color: #E8EDF5;
    padding: 2px 7px;
    font-size: 11px;
    font-family: "Microsoft YaHei UI";
    font-weight: 600;
}}
QFrame#OverlayControls QPushButton:hover {{
    background-color: rgba(255, 255, 255, 30);
    border-radius: 6px;
}}
QFrame#OverlayControls QPushButton:pressed {{
    background-color: rgba(255, 59, 92, 90);
}}

QCheckBox {{
    color: {TEXT};
    spacing: 9px;
    font-size: 12px;
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid #354155;
    background: {BG_RAISED};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    image: url("{CHECK_ICON}");
}}
QSlider::groove:horizontal {{
    height: 5px;
    background: #232C3A;
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 15px;
    height: 15px;
    margin: -5px 0;
    border-radius: 8px;
    background: #FFFFFF;
    border: 2px solid {ACCENT};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2B3546;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3A475D;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #2B3546;
    border-radius: 4px;
    min-width: 30px;
}}
QSplitter::handle {{
    background: transparent;
    width: 10px;
}}
QMenu {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
    color: {TEXT};
}}
QMenu::item {{
    padding: 7px 22px 7px 12px;
    border-radius: 6px;
    font-size: 12px;
}}
QMenu::item:selected {{
    background-color: {SURFACE_HOVER};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER_SOFT};
    margin: 5px 8px;
}}
QToolTip {{
    background-color: #1E2633;
    color: {TEXT};
    border: 1px solid #354155;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 11px;
}}
QProgressBar {{
    background-color: {SURFACE_ALT};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 4px;
}}
QGroupBox {{
    border: 1px solid {BORDER_SOFT};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px 10px 8px 10px;
    font-size: 12px;
    font-weight: 600;
    color: {TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: {TEXT_MUTED};
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom-color: {ACCENT};
}}
QListWidget {{
    background: transparent;
    border: none;
}}
QMessageBox {{
    background-color: {SURFACE};
}}
"""


def apply_theme(app) -> None:
    app.setStyle("Fusion")
    font = QFont("Microsoft YaHei UI", 9)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    app.setStyleSheet(STYLE)


def color(value: str, alpha: int = 255) -> QColor:
    qcolor = QColor(value)
    if not qcolor.isValid():
        qcolor = QColor("#FFFFFF")
    qcolor.setAlpha(max(0, min(255, alpha)))
    return qcolor


def draw_app_icon(size: int = 256) -> QPixmap:
    """Draw the heart + pulse mark, used when the .ico asset is absent."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    rect = QRectF(1, 1, size - 2, size - 2)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#FF5C77"))
    gradient.setColorAt(1.0, QColor("#D91E46"))
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.24, size * 0.24)
    painter.fillPath(path, gradient)
    # Heart silhouette
    heart = QPainterPath()
    cx, cy = size * 0.5, size * 0.52
    s = size * 0.29
    heart.moveTo(cx, cy + s * 0.82)
    heart.cubicTo(cx - s * 1.35, cy - s * 0.05, cx - s * 0.72, cy - s * 1.02, cx, cy - s * 0.38)
    heart.cubicTo(cx + s * 0.72, cy - s * 1.02, cx + s * 1.35, cy - s * 0.05, cx, cy + s * 0.82)
    painter.fillPath(heart, QColor(255, 255, 255, 245))
    # Pulse line
    pen = painter.pen()
    pen.setColor(QColor("#D91E46"))
    pen.setWidthF(max(2.0, size * 0.045))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    y = size * 0.50
    pulse = QPainterPath()
    pulse.moveTo(size * 0.18, y)
    pulse.lineTo(size * 0.34, y)
    pulse.lineTo(size * 0.40, y - size * 0.10)
    pulse.lineTo(size * 0.47, y + size * 0.12)
    pulse.lineTo(size * 0.54, y - size * 0.18)
    pulse.lineTo(size * 0.60, y)
    pulse.lineTo(size * 0.82, y)
    painter.drawPath(pulse)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    path = resource_path("assets/heart.ico")
    icon = QIcon()
    if Path(path).exists():
        icon.addFile(str(path))
    if icon.isNull():
        for size in (16, 24, 32, 48, 64, 128, 256):
            icon.addPixmap(draw_app_icon(size))
    return icon


def heart_pixmap(size: int = 64, color_value: str = ACCENT) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color(color_value))
    font = QFont("Segoe UI Emoji", int(size * 0.78))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "❤")
    painter.end()
    return pixmap
