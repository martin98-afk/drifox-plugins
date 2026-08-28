# -*- coding: utf-8 -*-
"""浏览器拦截设置弹窗 — 控制系统软件浏览器拦截行为

宿主 MaskDialogBase 风格（与 git-panel 弹窗一致），提供 3 个开关：
- 启用拦截（全局总开关）
- 拦截打开网页（http/https —— 系统 webbrowser/QDesktopServices、
  os.startfile、bash start/explorer 全部入口统一控制）
- 拦截打开本地 html 文件（file:// / os.startfile / 磁盘 .html 路径）

保存即写盘生效（external_open 代理调用时动态读当前配置，无需重启；
热重载后同样实时生效 —— v1.4.0 修复了旧代理冻结旧配置导致的「失效」）。

配色：深浅主题自适应（v1.4.0 修复 —— 原硬编码深色 rgba(33,33,38,242)
背景 + #f2f2f2 浅字，浅色主题下也是黑的；现全部走 theme_colors token：
深色主题深底浅字 / 浅色主题白底深字）。
字体走 context_provider（与历史/收藏/下载弹窗一致），保证全应用统一。
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import MaskDialogBase, SwitchButton

from .redirect_config import get_config
from .theme import _adjust_color, font_css, theme_colors

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
        ("enabled", "启用拦截", "总开关，关闭后所有拦截失效（网页 / HTML 全部走系统默认行为）"),
        ("intercept_web", "拦截打开网页", "http/https 链接（系统浏览器外链、os.startfile、bash start 全入口）→ 内置浏览器"),
        ("intercept_html", "拦截打开本地 HTML", "打开 file:// / 磁盘 .html/.htm 文件 → 内置浏览器"),
    )

    def __init__(self, parent=None, owner=None):
        super().__init__(_dialog_parent(parent))
        # owner（浏览器卡片实例）用于取 _context_provider 字体
        self._owner = owner if owner is not None else self.parent()
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
        # 字体 + 配色全部走 theme_colors（深浅主题自适应，修复「浅色主题下也全黑」）
        c = theme_colors(self._owner)
        ff, fs = c["ff"], c["fs"]
        title_font = font_css(ff, fs + 1)
        body_font = font_css(ff, fs - 1)
        small_font = font_css(ff, fs - 3)
        btn_font = font_css(ff, fs - 1)
        text, secondary, surface = c["text"], c["secondary"], c["surface"]
        border, raised, hover, accent = c["border"], c["raised"], c["hover"], c["accent"]
        self.widget.setStyleSheet(
            f"#redirectSettingsWidget {{ background: {surface};"
            f" border: 1px solid {border}; border-radius: 12px; {body_font} }}"
        )
        ly = QVBoxLayout(self.widget)
        ly.setContentsMargins(20, 16, 20, 16)
        ly.setSpacing(6)

        # 标题
        title = QLabel(self.TITLE, self.widget)
        title.setStyleSheet(
            f"color: {text}; {title_font} font-weight: 600; background: transparent;"
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
                f"color: {text}; {body_font} font-weight: 500; background: transparent;"
            )
            desc_lb = QLabel(desc, row)
            desc_lb.setWordWrap(True)
            desc_lb.setStyleSheet(
                f"color: {secondary}; {small_font} background: transparent;"
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
        sep.setStyleSheet(f"background: {border};")
        ly.addSpacing(4)
        ly.addWidget(sep)
        ly.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("取消", self.widget)
        close_btn.setFixedSize(80, 30)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {raised}; border: none;"
            f" border-radius: 6px; color: {text}; {btn_font} }}"
            f"QPushButton:hover {{ background: {hover}; }}"
        )
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        save_btn = QPushButton("保存", self.widget)
        save_btn.setFixedSize(80, 30)
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {accent}; border: none;"
            f" border-radius: 6px; color: white; {btn_font} font-weight: 600; }}"
            f"QPushButton:hover {{ background: {_adjust_color(accent, 20)}; }}"
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
        # 通知浏览器卡片刷新状态栏摘要（让用户立刻看到配置变化）
        owner = self._owner
        if owner is not None and hasattr(owner, "refresh_theme"):
            try:
                owner.refresh_theme()
            except Exception:
                pass
        elif owner is not None and hasattr(owner, "_intercept_status_lb"):
            from .redirect_config import config_summary
            owner._intercept_status_lb.setText(config_summary())
        self.accept()

    def _center_widget(self):
        x = max(0, (self.width() - self.widget.width()) // 2)
        y = max(0, (self.height() - self.widget.height()) // 2)
        self.widget.move(x, y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._center_widget()


def show_redirect_settings(parent=None, owner=None):
    """打开拦截设置弹窗（阻塞式，保存即生效）

    Args:
        parent: 调用方顶层 widget（仅用于定位）
        owner:  浏览器卡片实例（取 _context_provider 字体；可省略）
    """
    dlg = _RedirectSettingsDialog(parent, owner=owner)
    dlg.exec()