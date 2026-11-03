# -*- coding: utf-8 -*-
"""标签栏 — Chrome 风格多标签

- 关闭按钮（hover 显示 ×）
- 标题同步：页面 titleChanged → 标签文本；loading 时前缀 ●
- 右键菜单：新建标签 / 关闭标签 / 关闭其他
- 超过 MAX_ALIVE_TABS 时后台标签冻结（setLifecycleState Frozen，M3 性能）
"""

import os

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu, QTabBar, QToolButton

from .theme import menu_style, theme_colors

# 图标资源目录（ui/assets/）
_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

def _close_icon(is_dark: bool) -> QIcon:
    return QIcon(os.path.join(_ICON_DIR, "close_dark.svg" if is_dark else "close.svg"))

# 后台标签冻结阈值：超过此数量的标签，非活跃标签冻结释放内存
MAX_ALIVE_TABS = 6


class ChromeTabBar(QTabBar):
    """Chrome 风格标签栏"""

    new_tab_requested = pyqtSignal()
    close_others_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._c = theme_colors(None)  # 主题派生色缓存（apply_theme 前默认观感）
        self.setTabsClosable(False)  # 关闭按钮自绘（原生按钮在深色下是一团圆点 + 英文 tooltip）
        self.setMovable(True)
        self.setExpanding(False)
        self.setDocumentMode(True)
        self.setElideMode(Qt.ElideRight)
        self.setUsesScrollButtons(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setStyleSheet(_tab_bar_style(self._c))
        self._menu_style = ""

        # 拖到空白处新建标签（Chrome 行为）
        self._drag_start_pos = None

    def mouseDoubleClickEvent(self, event):
        """双击空白区域新建标签"""
        if event.button() == Qt.LeftButton:
            tab_idx = self.tabAt(event.pos())
            if tab_idx == -1:
                self.new_tab_requested.emit()
        super().mouseDoubleClickEvent(event)

    def _show_context_menu(self, pos):
        idx = self.tabAt(pos)
        menu = QMenu(self)
        if self._menu_style:
            menu.setStyleSheet(self._menu_style)
        menu.addAction("新建标签", self.new_tab_requested.emit)
        if idx >= 0:
            menu.addSeparator()
            menu.addAction("关闭标签", lambda: self.tabCloseRequested.emit(idx))
            menu.addAction(
                "关闭其他标签", lambda: self.close_others_requested.emit(idx)
            )
        menu.exec_(self.mapToGlobal(pos))

    def apply_theme(self, c: dict):
        """应用主题派生色字典（来自 theme.theme_colors(owner)）。"""
        self._c = c
        self.setStyleSheet(_tab_bar_style(c))
        icon = _close_icon(c["is_dark"])
        for i in range(self.count()):
            btn = self.tabButton(i, QTabBar.RightSide)
            if isinstance(btn, QToolButton):
                btn.setIcon(icon)
        # 收敛到 menu_style 组合器：selected 背景用 hover（对齐主程序 QMenu 规格，
        # 弱化选中感避免与浏览器页面右键菜单观感割裂）
        self._menu_style = menu_style(c["ff"], c["fs"], c["card"], c["border"], c["hover"], c["text"])

    # ── 自绘关闭按钮 ──

    def tabInserted(self, index):
        super().tabInserted(index)
        self._sync_close_buttons()

    def tabRemoved(self, index):
        super().tabRemoved(index)
        self._sync_close_buttons()

    def _sync_close_buttons(self):
        for i in range(self.count()):
            if isinstance(self.tabButton(i, QTabBar.RightSide), QToolButton):
                continue
            self.setTabButton(i, QTabBar.RightSide, self._make_close_button())

    def _make_close_button(self) -> QToolButton:
        btn = QToolButton(self)
        btn.setIcon(_close_icon(self._c["is_dark"]))
        btn.setIconSize(QSize(12, 12))
        btn.setFixedSize(18, 18)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("关闭标签")
        btn.clicked.connect(lambda _checked=False, b=btn: self._close_from_button(b))
        return btn

    def _close_from_button(self, btn: QToolButton):
        pos = btn.mapTo(self, btn.rect().center())
        idx = self.tabAt(pos)
        if idx >= 0:
            self.tabCloseRequested.emit(idx)


def _tab_bar_style(c: dict) -> str:
    # 选中标签用页面同色 + 顶部 2px accent 指示条，未选中降为 secondary
    # （原来是 selected_bg 铺满整块，彩色块观感廉价）
    return f"""
    QTabBar {{
        background: transparent;
    }}
    QTabBar::tab {{
        background: transparent;
        border: none;
        border-top: 2px solid transparent;
        padding: 0 10px;
        min-width: 120px;
        max-width: 220px;
        height: 34px;
        font-family: '{c["ff"]}';
        font-size: {max(11, c["fs"] - 1)}px;
        color: {c["secondary"]};
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    QTabBar::tab:selected {{
        background: {c["surface"]};
        border-top: 2px solid {c["accent"]};
        color: {c["text"]};
    }}
    QTabBar::tab:hover:!selected {{
        background: {c["hover"]};
        color: {c["text"]};
    }}
    QTabBar QToolButton {{
        border: none;
        border-radius: 9px;
        background: transparent;
    }}
    QTabBar QToolButton:hover {{
        background: {c["hover"]};
    }}
    """
