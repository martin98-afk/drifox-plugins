# -*- coding: utf-8 -*-
"""历史记录 — 历史面板 + 数据操作

H2 修复：_reload / _on_search 走 AsyncDataLoader 后台线程，主线程不阻塞。
打开面板时缓存为空 → 立即显示空列表 + 加载状态；后台数据到达后回填渲染。
"""

from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from loguru import logger

from .data import AsyncDataLoader, clear_history
from .theme import dialog_style, scrollbar_style, theme_colors


class HistoryPanel(QFrame):
    """浏览器卡片内的悬浮历史记录面板。"""

    def __init__(self, owner, parent=None):
        super().__init__(parent or owner)
        self._owner = owner
        self.setObjectName("historyPanel")
        self.setFixedSize(420, 270)
        self._loader = AsyncDataLoader(self)
        self._items_cache: List[dict] = []  # 最近一次查询结果（供同步渲染）
        self._setup_ui()
        self._reload()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("🕘 历史记录")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("搜索历史…")
        self._search.textChanged.connect(self._on_search)
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(200)
        header.addWidget(self._search)
        root.addLayout(header)

        self._list = QListWidget(self)
        self._list.itemDoubleClicked.connect(self._open_item)
        root.addWidget(self._list, 1)

        footer = QHBoxLayout()
        self._btn_open = QPushButton("打开")
        self._btn_clear = QPushButton("清空历史")
        self._btn_close = QPushButton("关闭")
        self._btn_open.clicked.connect(self._open_selected)
        self._btn_clear.clicked.connect(self._clear)
        self._btn_close.clicked.connect(self.close)
        footer.addWidget(self._btn_open)
        footer.addWidget(self._btn_clear)
        footer.addStretch(1)
        footer.addWidget(self._btn_close)
        root.addLayout(footer)

        colors = theme_colors(self._owner)
        self.setStyleSheet(
            f"QFrame#historyPanel {{ background: {colors['surface']}; border: 1px solid {colors['border']};"
            " border-radius: 8px; }}"
            + dialog_style(self._owner, include_line_edit=True)
            + scrollbar_style(self._owner)
        )

    # ── H2 修复：异步加载 ──

    def _reload(self, items: Optional[List[dict]] = None):
        """刷新列表

        - items=None：异步查询 history（走 AsyncDataLoader，主线程不阻塞）
        - items=List[dict]：同步回填缓存（来自 worker 回调或 search_history 结果）
        """
        if items is None:
            # 显示加载占位 + 异步拉取
            self._list.clear()
            placeholder = QListWidgetItem("加载中…")
            self._list.addItem(placeholder)
            self._loader.load(
                "history",
                self._on_history_loaded,
                limit=200,
            )
            return
        self._items_cache = list(items)
        self._render_list()

    def _on_history_loaded(self, items):
        """后台线程回调 → 缓存 + 渲染"""
        self._items_cache = list(items)
        self._render_list()

    def _render_list(self):
        """同步渲染缓存到 QListWidget（毫秒级，500+ 条不卡）"""
        self._list.clear()
        if not self._items_cache:
            placeholder = QListWidgetItem("暂无历史记录")
            self._list.addItem(placeholder)
            return
        for h in self._items_cache:
            title = h.get("title") or h.get("url")
            count = h.get("visit_count", 1)
            item = QListWidgetItem(f"{title}  ({count} 次访问)\n   {h.get('url')}")
            item.setData(Qt.UserRole, h.get("url"))
            item.setToolTip(h.get("url"))
            self._list.addItem(item)

    def _on_search(self, text: str):
        """搜索也走异步（H2 修复）"""
        text = text.strip()
        self._list.clear()
        placeholder = QListWidgetItem("加载中…")
        self._list.addItem(placeholder)
        if text:
            self._loader.load(
                "search_history",
                self._on_history_loaded,
                on_error=lambda e: logger.error(f"[browser] 搜索历史失败: {e}"),
                keyword=text,
                limit=100,
            )
        else:
            self._loader.load(
                "history",
                self._on_history_loaded,
                limit=200,
            )

    def _open_item(self, item):
        self._open_url(item)

    def _open_selected(self):
        item = self._list.currentItem()
        if item:
            self._open_url(item)

    def _open_url(self, item):
        url = item.data(Qt.UserRole)
        if url:
            self._owner._new_tab(url)
            self.hide()

    def _clear(self):
        from PyQt5.QtWidgets import QMessageBox

        if QMessageBox.question(self, "清空历史", "确定要清空全部历史记录吗？") == QMessageBox.Yes:
            n = clear_history()
            self._reload()
            self._owner._set_status(f"已清空 {n} 条历史记录")


def show_history_panel(owner):
    """从浏览器卡片打开历史面板（单例复用）"""
    if not hasattr(owner, "_history_panel") or owner._history_panel is None:
        owner._history_panel = HistoryPanel(owner, owner)
    colors = theme_colors(owner)
    owner._history_panel.setStyleSheet(
        f"QFrame#historyPanel {{ background: {colors['surface']}; border: 1px solid {colors['border']};"
        " border-radius: 8px; }}"
        + dialog_style(owner, include_line_edit=True)
        + scrollbar_style(owner)
    )
    owner._history_panel._reload()
    owner._history_panel.show()
    owner._position_popup(owner._history_panel)