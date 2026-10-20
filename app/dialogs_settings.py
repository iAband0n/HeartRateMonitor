"""Application settings dialog."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import win32_utils
from .models import APP_DISPLAY_NAME, APP_VERSION
from .storage import AppPaths, ConfigStore
from .theme import app_icon

log = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        config_store: ConfigStore,
        paths: AppPaths,
        clear_history_callback,
        edit_default_display_callback,
    ) -> None:
        super().__init__(parent)
        self.config_store = config_store
        self.paths = paths
        self._clear_history_callback = clear_history_callback
        self._edit_default_display_callback = edit_default_display_callback
        self.setWindowTitle("设置")
        self.setWindowIcon(app_icon())
        self.resize(720, 580)
        self.setMinimumSize(640, 520)
        self._build()
        self._load()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("设置")
        title.setStyleSheet("font-size: 23px; font-weight: 700;")
        subtitle = QLabel("连接行为、悬浮窗置顶、历史记录与快捷键")
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

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general_tab(), "通用")
        self.tabs.addTab(self._build_data_tab(), "数据")
        self.tabs.addTab(self._build_about_tab(), "关于")
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存设置")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        footer.addWidget(cancel)
        footer.addWidget(save)
        root.addLayout(footer)

    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        behavior = QGroupBox("启动与窗口")
        form = QVBoxLayout(behavior)
        form.setSpacing(10)
        self.auto_reconnect_check = QCheckBox("启动时自动重连收藏设备")
        self.auto_reconnect_check.setToolTip(
            "开启后，程序启动时会自动连接已收藏且勾选自动重连的设备"
        )
        self.close_to_tray_check = QCheckBox("关闭主窗口时最小化到系统托盘")
        self.close_to_tray_check.setToolTip("关闭后仍会保持蓝牙连接与悬浮窗")
        self.hotkeys_check = QCheckBox("启用全局快捷键（Ctrl+Alt+L 锁定/解锁，Ctrl+Alt+H 显示/隐藏）")
        form.addWidget(self.auto_reconnect_check)
        form.addWidget(self.close_to_tray_check)
        form.addWidget(self.hotkeys_check)
        layout.addWidget(behavior)

        overlay = QGroupBox("悬浮窗与全屏")
        grid = QGridLayout(overlay)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.topmost_check = QCheckBox("增强置顶（定期重新置顶，兼容无边框全屏游戏）")
        self.topmost_check.setToolTip(
            "每秒把悬浮窗重新放到最上层。无边框全屏/窗口化全屏游戏可正常显示。"
        )
        grid.addWidget(self.topmost_check, 0, 0, 1, 3)
        grid.addWidget(QLabel("重新置顶间隔"), 1, 0)
        self.topmost_interval = QSpinBox()
        self.topmost_interval.setRange(300, 5000)
        self.topmost_interval.setSingleStep(100)
        self.topmost_interval.setSuffix(" ms")
        self.topmost_interval.setFixedWidth(130)
        grid.addWidget(self.topmost_interval, 1, 1)
        grid.addWidget(QLabel(""), 1, 2)
        default_style = QPushButton("编辑默认悬浮窗样式…")
        default_style.clicked.connect(self._edit_default_display_callback)
        grid.addWidget(default_style, 2, 0, 1, 2)
        note = QLabel(
            "说明：Windows 的「独占全屏」会绕过桌面合成器，任何普通置顶窗口都无法显示。"
            "请把游戏设为「无边框窗口 / 窗口化全屏」；本程序对该模式做了持续置顶增强。"
        )
        note.setProperty("role", "dim")
        note.setWordWrap(True)
        grid.addWidget(note, 3, 0, 1, 3)
        layout.addWidget(overlay)
        layout.addStretch(1)
        return page

    def _build_data_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        history = QGroupBox("心率历史")
        form = QVBoxLayout(history)
        row = QHBoxLayout()
        row.addWidget(QLabel("历史保留天数"))
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 3650)
        self.retention_spin.setSuffix(" 天")
        self.retention_spin.setFixedWidth(120)
        row.addWidget(self.retention_spin)
        row.addStretch(1)
        form.addLayout(row)
        note = QLabel("心率按秒记录到本地 SQLite 数据库，只保存在这台电脑上。")
        note.setProperty("role", "dim")
        note.setWordWrap(True)
        form.addWidget(note)
        clear = QPushButton("清空全部历史记录")
        clear.setObjectName("Danger")
        clear.clicked.connect(self._clear_history)
        form.addWidget(clear, 0, Qt.AlignLeft)
        layout.addWidget(history)

        files = QGroupBox("本地文件")
        file_form = QVBoxLayout(files)
        data_row = QHBoxLayout()
        data_row.addWidget(QLabel("数据目录"))
        path_label = QLabel(str(self.paths.data_dir))
        path_label.setProperty("role", "muted")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data_row.addWidget(path_label, 1)
        open_button = QPushButton("打开")
        open_button.setObjectName("Chip")
        open_button.clicked.connect(lambda: win32_utils.open_folder(str(self.paths.data_dir)))
        data_row.addWidget(open_button)
        file_form.addLayout(data_row)
        log_row = QHBoxLayout()
        log_row.addWidget(QLabel("日志文件"))
        log_label = QLabel(str(self.paths.log_file))
        log_label.setProperty("role", "muted")
        log_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        log_row.addWidget(log_label, 1)
        file_form.addLayout(log_row)
        layout.addWidget(files)
        layout.addStretch(1)
        return page

    def _build_about_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(72, 72))
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)
        name = QLabel(f"{APP_DISPLAY_NAME}  v{APP_VERSION}")
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(name)
        desc = QLabel(
            "通过低功耗蓝牙读取手环 / 手表的标准心率服务，并显示在可自定义、"
            "始终置顶的悬浮窗中。支持多设备、历史曲线、收藏常用设备。"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setProperty("role", "muted")
        layout.addWidget(desc)
        ref = QLabel(
            '<a href="https://github.com/ccc007ccc/HeartRateMonitor" '
            'style="color:#FF5C77; text-decoration:none;">参考项目：ccc007ccc/HeartRateMonitor</a>'
        )
        ref.setAlignment(Qt.AlignCenter)
        ref.setOpenExternalLinks(True)
        layout.addWidget(ref)
        layout.addSpacing(8)
        tip = QLabel(
            "使用提示\n"
            "• 部分手环需要在官方 App 中开启「心率广播」后才能被电脑读取。\n"
            "• 设备已连接手机时可能拒绝电脑连接，请先在手机端断开。\n"
            "• 锁定悬浮窗后点击会穿透到下层窗口；可在主窗口、托盘菜单或快捷键解锁。"
        )
        tip.setWordWrap(True)
        tip.setProperty("role", "muted")
        tip.setStyleSheet("line-height: 1.5;")
        tip_frame = QFrame()
        tip_frame.setObjectName("SubtleCard")
        tip_layout = QVBoxLayout(tip_frame)
        tip_layout.setContentsMargins(14, 12, 14, 12)
        tip_layout.addWidget(tip)
        layout.addWidget(tip_frame)
        layout.addStretch(1)
        copyright_label = QLabel("仅在本机运行 · 不上传任何健康数据")
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setProperty("role", "dim")
        layout.addWidget(copyright_label)
        return page

    # -- data --------------------------------------------------------------
    def _load(self) -> None:
        cfg = self.config_store.config
        self.auto_reconnect_check.setChecked(cfg.auto_reconnect_favorites)
        self.close_to_tray_check.setChecked(cfg.close_to_tray)
        self.hotkeys_check.setChecked(cfg.hotkeys_enabled)
        self.topmost_check.setChecked(cfg.topmost_enhance)
        self.topmost_interval.setValue(cfg.topmost_interval_ms)
        self.retention_spin.setValue(cfg.history_retention_days)

    def _clear_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空历史记录",
            "确定要删除所有设备的心率历史吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._clear_history_callback()

    def _save(self) -> None:
        cfg = self.config_store.config
        cfg.auto_reconnect_favorites = self.auto_reconnect_check.isChecked()
        cfg.close_to_tray = self.close_to_tray_check.isChecked()
        cfg.hotkeys_enabled = self.hotkeys_check.isChecked()
        cfg.topmost_enhance = self.topmost_check.isChecked()
        cfg.topmost_interval_ms = self.topmost_interval.value()
        cfg.history_retention_days = self.retention_spin.value()
        self.config_store.save()
        self.accept()
