"""Modal dialogs: device picker, overlay style editor and settings."""

from __future__ import annotations

import dataclasses
import logging
from typing import Callable

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import DisplayConfig
from .render import paint_display
from .theme import BORDER, app_icon

log = logging.getLogger(__name__)


def _label(text: str, role: str = "", wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if role:
        label.setProperty("role", role)
    label.setWordWrap(wrap)
    return label


def _section(title: str) -> QLabel:
    label = QLabel(title)
    label.setStyleSheet("font-size: 12px; font-weight: 700; color: #B8C2D1;")
    return label


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = value if QColor(value).isValid() else "#FFFFFF"
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(126)
        self.clicked.connect(self._choose)
        self.set_color(self._color)

    def set_color(self, value: str, emit: bool = False) -> None:
        qcolor = QColor(value)
        if not qcolor.isValid():
            return
        self._color = qcolor.name().upper()
        lum = 0.2126 * qcolor.red() + 0.7152 * qcolor.green() + 0.0722 * qcolor.blue()
        text_color = "#101820" if lum > 150 else "#FFFFFF"
        self.setText(self._color)
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._color}; color: {text_color}; "
            f"border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 10px; "
            "font-size: 11px; font-weight: 600; }"
        )
        if emit:
            self.color_changed.emit(self._color)

    def _choose(self) -> None:
        initial = QColor(self._color)
        chosen = QColorDialog.getColor(initial, self, "选择颜色", QColorDialog.ShowAlphaChannel)
        if chosen.isValid():
            self.set_color(chosen.name().upper(), emit=True)


class DisplayPreview(QWidget):
    """Live preview with a checkerboard to show real transparency."""

    def __init__(self, config: DisplayConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config.normalized()
        self.bpm = 78
        self.device_name = "Mi Band 8"
        self.battery: int | None = 82
        self.connected = True
        self.setMinimumSize(320, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_config(self, config: DisplayConfig) -> None:
        self.config = config.normalized()
        self.update()

    def set_data(self, bpm: int, connected: bool, name: str = "", battery: int | None = None) -> None:
        self.bpm = max(0, int(bpm))
        self.connected = connected
        if name:
            self.device_name = name
        self.battery = battery
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        radius = 14
        clip = QPainterPath()
        clip.addRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
        painter.setClipPath(clip)
        cell = 14
        painter.fillRect(rect, QColor("#0E131B"))
        for y in range(0, self.height(), cell):
            for x in range(0, self.width(), cell):
                if (x // cell + y // cell) % 2 == 0:
                    painter.fillRect(x, y, cell, cell, QColor("#151C27"))
        painter.setClipping(False)
        painter.setPen(QColor(BORDER))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        from .render import build_layout

        layout = build_layout(
            self.config,
            self.bpm if self.connected else 0,
            self.device_name,
            self.battery,
            self.connected,
        )
        max_width = max(1.0, rect.width() - 32)
        max_height = max(1.0, rect.height() - 32)
        scale = min(1.0, max_width / max(1.0, layout.box_width), max_height / max(1.0, layout.box_height))
        painter.save()
        painter.translate(rect.center())
        painter.scale(scale, scale)
        box = QRectF(
            -layout.box_width / 2,
            -layout.box_height / 2,
            layout.box_width,
            layout.box_height,
        )
        paint_display(
            painter,
            self.config,
            self.bpm if self.connected else 0,
            self.device_name,
            self.battery,
            self.connected,
            box,
        )
        painter.restore()
        painter.end()


class DisplaySettingsDialog(QDialog):
    """Edits a DisplayConfig and applies changes live via a callback."""

    def __init__(
        self,
        parent: QWidget,
        config: DisplayConfig,
        device_name: str,
        apply_callback: Callable[[DisplayConfig], None],
        sample_bpm: int = 78,
        sample_connected: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"悬浮窗样式 · {device_name}")
        self.setWindowIcon(app_icon())
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            width = min(1020, max(880, area.width() - 100))
            height = min(870, max(620, area.height() - 70))
            self.resize(width, height)
        else:
            self.resize(980, 820)
        self.setMinimumSize(860, 600)
        self._original = config.normalized()
        self._working = dataclasses.replace(self._original)
        self._apply_callback = apply_callback
        self._accepted = False
        self._loading = True
        self._device_name = device_name
        self._build()
        self._load_from_config(self._working)
        self._loading = False
        self._preview.set_data(
            sample_bpm, sample_connected, device_name, 82 if sample_connected else None
        )
        self._update_warning()
        self._preview.set_config(self._working)

    # -- UI ----------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("自定义悬浮窗")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        subtitle = QLabel(
            f"正在编辑「{self._device_name}」的显示效果 · 所有修改会实时预览"
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

        body = QHBoxLayout()
        body.setSpacing(14)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        self.form = QVBoxLayout(content)
        self.form.setContentsMargins(2, 2, 10, 2)
        self.form.setSpacing(12)
        self._build_content_group()
        self._build_typography_group()
        self._build_color_group()
        self.form.addStretch(1)
        self.scroll.setWidget(content)
        body.addWidget(self.scroll, 1)

        side = QFrame()
        side.setObjectName("Card")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(14, 14, 14, 14)
        side_layout.setSpacing(10)
        side_layout.addWidget(_section("实时预览"))
        self._preview = DisplayPreview(self._working)
        side_layout.addWidget(self._preview, 1)
        hint = QLabel("棋盘格代表透明区域\n保存后会立即应用到悬浮窗")
        hint.setProperty("role", "dim")
        hint.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(hint)
        side_layout.addWidget(_section("快速预设"))
        presets = QGridLayout()
        presets.setSpacing(6)
        preset_data = [
            ("经典红心", "classic"),
            ("极简数字", "minimal"),
            ("霓虹描边", "neon"),
            ("设备名称", "device"),
        ]
        for index, (text, key) in enumerate(preset_data):
            button = QPushButton(text)
            button.setObjectName("Chip")
            button.clicked.connect(lambda _=False, k=key: self._apply_preset(k))
            presets.addWidget(button, index // 2, index % 2)
        side_layout.addLayout(presets)
        side.setMinimumWidth(340)
        side.setMaximumWidth(430)
        body.addWidget(side, 0)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        reset = QPushButton("恢复默认")
        reset.setObjectName("Ghost")
        reset.clicked.connect(self._reset)
        footer.addWidget(reset)
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存并应用")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        footer.addWidget(cancel)
        footer.addWidget(save)
        root.addLayout(footer)

    def _build_content_group(self) -> None:
        group = QGroupBox("显示内容")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(_label("显示模板"))
        self.template_edit = QLineEdit()
        self.template_edit.setPlaceholderText("例如：❤{bpm}")
        self.template_edit.textChanged.connect(self._on_changed)
        row.addWidget(self.template_edit, 1)
        layout.addLayout(row)
        hint = QLabel(
            "{bpm} = 心率数字   {heart} = 心形字符   {name} = 设备名   "
            "{battery} = 电量   {time} = 当前时间"
        )
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.template_warning = QLabel("")
        self.template_warning.setStyleSheet("color: #FBBF24; font-size: 11px;")
        self.template_warning.setWordWrap(True)
        layout.addWidget(self.template_warning)

        heart_row = QHBoxLayout()
        heart_row.addWidget(_label("心形字符"))
        self.heart_edit = QLineEdit()
        self.heart_edit.setMaxLength(4)
        self.heart_edit.setFixedWidth(90)
        self.heart_edit.textChanged.connect(self._on_changed)
        heart_row.addWidget(self.heart_edit)
        for char in ("❤", "♥", "♡", "💓", "🖤"):
            button = QPushButton(char)
            button.setObjectName("Chip")
            button.setFixedWidth(38)
            button.clicked.connect(lambda _=False, c=char: self.heart_edit.setText(c))
            heart_row.addWidget(button)
        heart_row.addStretch(1)
        layout.addLayout(heart_row)
        self.form.addWidget(group)

    def _build_typography_group(self) -> None:
        group = QGroupBox("字体与排版")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.addWidget(_label("字体"), 0, 0)
        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self._on_changed)
        grid.addWidget(self.font_combo, 0, 1, 1, 3)

        grid.addWidget(_label("字号 (px)"), 1, 0)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(12, 220)
        self.size_spin.setSuffix(" px")
        self.size_spin.valueChanged.connect(self._on_changed)
        grid.addWidget(self.size_spin, 1, 1)

        grid.addWidget(_label("字符间距"), 1, 2)
        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(-4, 40)
        self.spacing_spin.setSingleStep(0.5)
        self.spacing_spin.setSuffix(" px")
        self.spacing_spin.valueChanged.connect(self._on_changed)
        grid.addWidget(self.spacing_spin, 1, 3)

        style_row = QHBoxLayout()
        self.bold_check = QCheckBox("粗体")
        self.bold_check.toggled.connect(self._on_changed)
        self.italic_check = QCheckBox("斜体")
        self.italic_check.toggled.connect(self._on_changed)
        style_row.addWidget(self.bold_check)
        style_row.addWidget(self.italic_check)
        style_row.addStretch(1)
        grid.addLayout(style_row, 2, 0, 1, 4)

        grid.addWidget(_label("内边距"), 3, 0)
        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(0, 80)
        self.padding_spin.setSuffix(" px")
        self.padding_spin.valueChanged.connect(self._on_changed)
        grid.addWidget(self.padding_spin, 3, 1)

        grid.addWidget(_label("圆角"), 3, 2)
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(0, 80)
        self.radius_spin.setSuffix(" px")
        self.radius_spin.valueChanged.connect(self._on_changed)
        grid.addWidget(self.radius_spin, 3, 3)

        grid.addWidget(_label("整体不透明度"), 4, 0)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(15, 100)
        self.opacity_slider.valueChanged.connect(self._on_changed)
        self.opacity_value = QLabel("100%")
        self.opacity_value.setFixedWidth(42)
        self.opacity_value.setProperty("role", "muted")
        grid.addWidget(self.opacity_slider, 4, 1, 1, 2)
        grid.addWidget(self.opacity_value, 4, 3)
        self.form.addWidget(group)

    def _build_color_group(self) -> None:
        group = QGroupBox("颜色与效果")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        grid.addWidget(_label("心形颜色"), 0, 0)
        self.heart_color = ColorButton("#FF3B5C")
        self.heart_color.color_changed.connect(self._on_changed)
        grid.addWidget(self.heart_color, 0, 1)
        grid.addWidget(_label("数字颜色"), 0, 2)
        self.number_color = ColorButton("#FFFFFF")
        self.number_color.color_changed.connect(self._on_changed)
        grid.addWidget(self.number_color, 0, 3)
        grid.addWidget(_label("其他文字"), 1, 0)
        self.text_color = ColorButton("#FFFFFF")
        self.text_color.color_changed.connect(self._on_changed)
        grid.addWidget(self.text_color, 1, 1)
        grid.addWidget(_label("描边颜色"), 1, 2)
        self.outline_color = ColorButton("#000000")
        self.outline_color.color_changed.connect(self._on_changed)
        grid.addWidget(self.outline_color, 1, 3)

        grid.addWidget(_label("背景颜色"), 2, 0)
        self.background_color = ColorButton("#0B0F16")
        self.background_color.color_changed.connect(self._on_changed)
        grid.addWidget(self.background_color, 2, 1)
        grid.addWidget(_label("描边粗细"), 2, 2)
        self.outline_spin = QSpinBox()
        self.outline_spin.setRange(0, 8)
        self.outline_spin.setSuffix(" px")
        self.outline_spin.valueChanged.connect(self._on_changed)
        grid.addWidget(self.outline_spin, 2, 3)

        grid.addWidget(_label("背景不透明度"), 3, 0)
        self.background_slider = QSlider(Qt.Horizontal)
        self.background_slider.setRange(0, 255)
        self.background_slider.valueChanged.connect(self._on_changed)
        self.background_value = QLabel("0%")
        self.background_value.setFixedWidth(42)
        self.background_value.setProperty("role", "muted")
        grid.addWidget(self.background_slider, 3, 1, 1, 2)
        grid.addWidget(self.background_value, 3, 3)

        self.shadow_check = QCheckBox("文字阴影")
        self.shadow_check.toggled.connect(self._on_changed)
        grid.addWidget(self.shadow_check, 4, 0)
        self.shadow_color = ColorButton("#000000")
        self.shadow_color.color_changed.connect(self._on_changed)
        grid.addWidget(self.shadow_color, 4, 1)
        grid.addWidget(_label("阴影浓度"), 4, 2)
        self.shadow_slider = QSlider(Qt.Horizontal)
        self.shadow_slider.setRange(0, 255)
        self.shadow_slider.valueChanged.connect(self._on_changed)
        grid.addWidget(self.shadow_slider, 4, 3)

        note = QLabel(
            "提示：❤ 与 ♥ 会使用上方设置的纯色心形；彩色 Emoji（如 💓）会保留字体自带颜色。"
        )
        note.setProperty("role", "dim")
        note.setWordWrap(True)
        grid.addWidget(note, 5, 0, 1, 4)
        self.form.addWidget(group)

    # -- data binding ------------------------------------------------------
    def _load_from_config(self, config: DisplayConfig) -> None:
        self.template_edit.setText(config.template)
        self.heart_edit.setText(config.heart_text)
        self.font_combo.setCurrentFont(QFont(config.font_family))
        self.size_spin.setValue(config.font_size)
        self.spacing_spin.setValue(config.letter_spacing)
        self.bold_check.setChecked(config.bold)
        self.italic_check.setChecked(config.italic)
        self.padding_spin.setValue(config.padding)
        self.radius_spin.setValue(config.radius)
        self.opacity_slider.setValue(int(round(config.opacity * 100)))
        self.heart_color.set_color(config.heart_color)
        self.number_color.set_color(config.number_color)
        self.text_color.set_color(config.text_color)
        self.outline_color.set_color(config.outline_color)
        self.background_color.set_color(config.background_color)
        self.outline_spin.setValue(config.outline_width)
        self.background_slider.setValue(config.background_opacity)
        self.shadow_check.setChecked(config.shadow_enabled)
        self.shadow_color.set_color(config.shadow_color)
        self.shadow_slider.setValue(config.shadow_opacity)
        self._sync_value_labels()

    def _sync_value_labels(self) -> None:
        self.opacity_value.setText(f"{self.opacity_slider.value()}%")
        self.background_value.setText(
            f"{int(round(self.background_slider.value() / 255 * 100))}%"
        )

    def _config_from_ui(self) -> DisplayConfig:
        cfg = dataclasses.replace(
            self._working,
            template=self.template_edit.text(),
            heart_text=self.heart_edit.text(),
            font_family=self.font_combo.currentFont().family(),
            font_size=self.size_spin.value(),
            bold=self.bold_check.isChecked(),
            italic=self.italic_check.isChecked(),
            letter_spacing=self.spacing_spin.value(),
            heart_color=self.heart_color._color,
            number_color=self.number_color._color,
            text_color=self.text_color._color,
            background_color=self.background_color._color,
            background_opacity=self.background_slider.value(),
            outline_color=self.outline_color._color,
            outline_width=self.outline_spin.value(),
            shadow_enabled=self.shadow_check.isChecked(),
            shadow_color=self.shadow_color._color,
            shadow_opacity=self.shadow_slider.value(),
            padding=self.padding_spin.value(),
            radius=self.radius_spin.value(),
            opacity=self.opacity_slider.value() / 100.0,
        )
        return cfg.normalized()

    def _on_changed(self, *args) -> None:
        if self._loading:
            return
        self._sync_value_labels()
        self._working = self._config_from_ui()
        self._preview.set_config(self._working)
        self._update_warning()
        try:
            self._apply_callback(self._working)
        except Exception:
            log.exception("Live overlay style preview failed")

    def _update_warning(self) -> None:
        text = self.template_edit.text()
        if not text.strip():
            self.template_warning.setText("显示模板不能为空，将回退为 ❤{bpm}。")
        elif "{bpm}" not in text:
            self.template_warning.setText(
                "当前模板没有包含 {bpm}，悬浮窗将不会显示心率数字。"
            )
        else:
            self.template_warning.setText("")

    def _apply_preset(self, key: str) -> None:
        base = dataclasses.replace(self._working)
        if key == "classic":
            cfg = dataclasses.replace(
                base,
                template="❤{bpm}",
                heart_text="❤",
                font_family="Segoe UI",
                font_size=56,
                bold=True,
                italic=False,
                letter_spacing=2,
                heart_color="#FF3B5C",
                number_color="#FFFFFF",
                text_color="#FFFFFF",
                background_opacity=0,
                outline_width=0,
                shadow_enabled=True,
                shadow_opacity=120,
                padding=16,
            )
        elif key == "minimal":
            cfg = dataclasses.replace(
                base,
                template="{bpm}",
                font_family="Segoe UI",
                font_size=72,
                bold=True,
                letter_spacing=0,
                number_color="#FFFFFF",
                background_opacity=0,
                outline_width=0,
                shadow_enabled=True,
                shadow_opacity=150,
                padding=10,
            )
        elif key == "neon":
            cfg = dataclasses.replace(
                base,
                template="♥ {bpm}",
                heart_text="♥",
                font_family="Segoe UI",
                font_size=60,
                bold=True,
                letter_spacing=3,
                heart_color="#FF2D6F",
                number_color="#FFE3EC",
                text_color="#FFE3EC",
                outline_color="#FF2D6F",
                outline_width=2,
                background_color="#140A11",
                background_opacity=120,
                shadow_enabled=True,
                shadow_color="#FF2D6F",
                shadow_opacity=180,
                padding=18,
                radius=20,
            )
        else:
            cfg = dataclasses.replace(
                base,
                template="{name}  ❤{bpm}",
                font_family="Segoe UI",
                font_size=42,
                bold=True,
                letter_spacing=1,
                heart_color="#FF3B5C",
                number_color="#FFFFFF",
                text_color="#A9B4C5",
                background_color="#0B0F16",
                background_opacity=170,
                outline_width=0,
                shadow_enabled=False,
                padding=18,
                radius=16,
            )
        self._loading = True
        self._load_from_config(cfg.normalized())
        self._loading = False
        self._working = cfg.normalized()
        self._preview.set_config(self._working)
        self._update_warning()
        self._apply_callback(self._working)

    def _reset(self) -> None:
        default = DisplayConfig().normalized()
        self._loading = True
        self._load_from_config(default)
        self._loading = False
        self._working = default
        self._preview.set_config(default)
        self._update_warning()
        self._apply_callback(default)

    def _save(self) -> None:
        self._working = self._config_from_ui()
        self._accepted = True
        self._apply_callback(self._working)
        self.accept()

    def reject(self) -> None:
        if not self._accepted:
            try:
                self._apply_callback(self._original)
            except Exception:
                pass
        super().reject()

    def closeEvent(self, event) -> None:
        if not self._accepted:
            try:
                self._apply_callback(self._original)
            except Exception:
                pass
        super().closeEvent(event)

    def result_config(self) -> DisplayConfig:
        return self._working
