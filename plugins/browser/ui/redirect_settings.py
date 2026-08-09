# -*- coding: utf-8 -*-
"""浏览器拦截设置弹窗 — 控制系统软件浏览器拦截行为

宿主 MaskDialogBase 风格（与 git-panel 弹窗一致），提供 4 个开关：
- 启用拦截（全局总开关）
- 拦截打开系统默认浏览器（webbrowser/QDesktopServices 的 http/https 外链）
- 拦截 shell 工具打开 URL（bash start/explorer <url>）
- 拦截打开本地 html 文件（file:// 或磁盘 .html 路径）

保存即写盘生效（external_open 每次调用实时读配置，无需重启）。
"""

from typing import Optional

from PyQt5.QtCore import Qt, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import MaskDialogBase, SwitchButton

from .redirect_config import get_config

# MaskDialogBase 要求 parent 非 None（__init__ 里取 parent.width()）；
# 无有效父窗口时兜底到常驻隐藏 QWidget（惰性创建，避免 app 未实例化崩溃）。
_DIALOG_PARENT_BACKUP: Optional[QWidget] = None


def _get_dialog_parent_backup() -> QWidget:
    global _DIALOG_PARENT_BACKUP
    if _DIALOG_PARENT_BACKUP is None:
        _DIALOG_PARENT_BACKUP = QWidget()
    return _DIALOG_PARENT_BACKUP


def _dialog_parent(parent) -> QWidget:
    """返回对话框挂载父窗口：宿主 TabManagerWindow > 调用方顶层 > 活动窗口 > 兜底"""
    try:
        from app.widgets.tab_manager_window import TabManagerWindow

        win = TabManagerWindow.get_instance()
        if win is not None:
            return win
    except Exception:
        pass
    if parent is not None:
        top = parent.window()
        if top is not None:
            return top
    app = QApplication.instance()
    if app is not None and app.activeWindow() is not None:
        return app.activeWindow()
    return _get_dialog_parent_backup()


class _RedirectSettingsDialog(MaskDialogBase):
    """浏览器拦截设置弹窗（宿主 MaskDialogBase 风格）"""

    WIDTH = 460
    TITLE = "浏览器拦截设置"
    _FIELDS = (
        ("enabled", "启用拦截", "总开关，关闭后所有拦截失效（http/shell/html 全部走系统默认行为）"),
        ("intercept_system", "拦截系统浏览器外链", "webbrowser / QDesktopServices 打开的 http/https 链接 → 内置浏览器"),
        ("intercept_shell", "拦截 Shell 打开 URL", "大模型 bash 执行 start/explorer <url> → 内置浏览器"),
        ("intercept_html", "拦截本地 HTML 文件", "打开 file:// 或磁盘 .html/.htm 文件 → 内置浏览器"),
    )

    def __init__(self, parent=None):
        super().__init__(_dialog_parent(parent))
        self._cfg = get_config()
        self._switches: dict = {}
        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 100))
        self.setClosableOnMaskClicked(True)
        self.setDraggable(True)
        self.setMaskColor(QColor(0, 0, 0, 180))
        self._setup_ui()
        self._load_values()

    def _setup_ui(self):
        self.widget.setObjectName("redirectSettingsWidget")
        self.widget.setStyleSheet(
            "#redirectSettingsWidget { background: rgba(33,33,38,242);"
            " border: 1px solid rgba(128,128,128,0.15); border-radius: 12px; }"
        )
        ly = QVBoxLayout(self.widget)
        ly.setContentsMargins(20, 16, 20, 16)
        ly.setSpacing(6)

        # 标题
        title = QLabel(self.TITLE, self.widget)
        title.setStyleSheet(
            "color: #f2f2f2; font-size: 15px; font-weight: 600; background: transparent;"
        )
        ly.addWidget(title)

        # 开关行
        for key, name, desc in self._FIELDS:
            row = QWidget(self.widget)
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 4, 0, 4)
            rl.setSpacing(10)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            name_lb = QLabel(name, row)
            name_lb.setStyleSheet(
                "color: #f2f2f2; font-size: 13px; font-weight: 500; background: transparent;"
            )
            desc_lb = QLabel(desc, row)
            desc_lb.setWordWrap(True)
            desc_lb.setStyleSheet(
                "color: rgba(200,200,200,0.75); font-size: 11px; background: transparent;"
            )
            text_col.addWidget(name_lb)
            text_col.addWidget(desc_lb)
            rl.addLayout(text_col, 1)

            sw = SwitchButton(row)
            sw.setChecked(True)
            rl.addWidget(sw, 0, Qt.AlignVCenter)
            ly.addWidget(row)
            self._switches[key] = sw

        # 分隔 + 按钮
        sep = QWidget(self.widget)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(128,128,128,0.15);")
        ly.addSpacing(4)
        ly.addWidget(sep)
        ly.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("取消", self.widget)
        close_btn.setFixedSize(80, 30)
        close_btn.setStyleSheet(
            "QPushButton { background: rgba(128,128,128,0.12); border: none;"
            " border-radius: 6px; color: #d0d0d0; font-size: 13px; }"
            "QPushButton:hover { background: rgba(128,128,128,0.22); }"
        )
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        save_btn = QPushButton("保存", self.widget)
        save_btn.setFixedSize(80, 30)
        save_btn.setStyleSheet(
            "QPushButton { background: rgba(98,160,234,0.2); border: none;"
            " border-radius: 6px; color: #62a0ea; font-size: 13px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(98,160,234,0.35); }"
        )
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        ly.addLayout(btn_row)

        self.widget.setFixedSize(self.WIDTH, self._calc_height())

    def _calc_height(self) -> int:
        """按开关行数估算高度（每行约 58px + 标题/分隔/按钮）"""
        return 70 + len(self._FIELDS) * 58 + 66

    def _load_values(self):
        for key, _, _ in self._FIELDS:
            self._switches[key].setChecked(bool(self._cfg.get(key, True)))

    def _on_save(self):
        changes = {key: sw.isChecked() for key, sw in self._switches.items()}
        self._cfg.update(changes)
        self.accept()

    def _center_widget(self):
        x = max(0, (self.width() - self.widget.width()) // 2)
        y = max(0, (self.height() - self.widget.height()) // 2)
        self.widget.move(x, y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._center_widget()


def show_redirect_settings(parent=None):
    """打开拦截设置弹窗（阻塞式，保存即生效）"""
    dlg = _RedirectSettingsDialog(parent)
    dlg.exec_()