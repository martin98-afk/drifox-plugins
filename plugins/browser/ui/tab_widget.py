# -*- coding: utf-8 -*-
"""标签栏 — Chrome 风格多标签

- 关闭按钮（hover 显示 ×）
- 标题同步：页面 titleChanged → 标签文本；loading 时前缀 ●
- 右键菜单：新建标签 / 关闭标签 / 关闭其他
- 超过 MAX_ALIVE_TABS 时后台标签冻结（setLifecycleState Frozen，M3 性能）
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QMenu, QTabBar

# 后台标签冻结阈值：超过此数量的标签，非活跃标签冻结释放内存
MAX_ALIVE_TABS = 6


class ChromeTabBar(QTabBar):
    """Chrome 风格标签栏"""

    new_tab_requested = pyqtSignal()
    close_others_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setExpanding(False)
        self.setDocumentMode(True)
        self.setElideMode(Qt.ElideRight)
        self.setUsesScrollButtons(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setStyleSheet(_tab_bar_style())
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
            menu.addAction("关闭其他标签", lambda: self.close_others_requested.emit(idx))
        menu.exec_(self.mapToGlobal(pos))

    def apply_theme(self, text: str, surface: str):
        """应用标签栏及右键菜单主题。"""
        self.setStyleSheet(_tab_bar_style(text))
        self._menu_style = (
            f"QMenu {{ background: {surface}; color: {text}; border: 1px solid rgba(128,128,128,0.25); }}"
            "QMenu::item { padding: 6px 24px 6px 10px; }"
            "QMenu::item:selected { background: rgba(128,128,128,0.20); }"
        )


def _tab_bar_style(text: str = "rgba(220,220,220,0.9)") -> str:
    return """
    QTabBar::tab {
        background: transparent;
        border: none;
        padding: 0 8px;
        min-width: 150px;
        max-width: 280px;
        height: 36px;
        font-size: 14px;
        color: __TEXT_COLOR__;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }
    QTabBar::tab:selected {
        background: rgba(128,128,128,0.22);
        color: __TEXT_COLOR__;
    }
    QTabBar::tab:hover:!selected {
        background: rgba(128,128,128,0.10);
    }
    QTabBar::close-button {
        border: none;
        border-radius: 8px;
        width: 16px;
        height: 16px;
        margin: 2px;
        subcontrol-origin: padding;
        subcontrol-position: right;
    }
    QTabBar::close-button:hover {
        background: rgba(255,80,80,0.8);
    }
    """.replace("__TEXT_COLOR__", text)
