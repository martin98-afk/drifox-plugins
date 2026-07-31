# -*- coding: utf-8 -*-
"""收藏管理 — 收藏面板 + 数据操作

H2 修复：_reload 走 AsyncDataLoader 后台线程，主线程不阻塞。

通过浏览器卡片的菜单 → 收藏夹 打开面板。
支持：打开收藏、删除收藏、从当前页添加收藏。
"""

from typing import List

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from loguru import logger

from .data import AsyncDataLoader, add_bookmark, remove_bookmark
from .theme import dialog_style


class BookmarksPanel(QDialog):
    """收藏管理面板（H2 修复：异步加载）"""

    open_url = pyqtSignal(str)

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner
        self.setWindowTitle("收藏夹")
        self.setMinimumSize(480, 420)
        self.setWindowFlag(Qt.Window)
        self._loader = AsyncDataLoader(self)
        self._items_cache: List[dict] = []
        self._setup_ui()
        self._reload()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("★ 收藏夹")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)

        self._btn_add = QPushButton("＋ 收藏当前页")
        self._btn_add.clicked.connect(self._add_current)
        header.addWidget(self._btn_add)
        root.addLayout(header)

        self._list = QListWidget(self)
        self._list.itemDoubleClicked.connect(self._open_item)
        root.addWidget(self._list, 1)

        footer = QHBoxLayout()
        self._btn_open = QPushButton("打开")
        self._btn_delete = QPushButton("删除")
        self._btn_close = QPushButton("关闭")
        self._btn_open.clicked.connect(self._open_selected)
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_close.clicked.connect(self.close)
        footer.addWidget(self._btn_open)
        footer.addWidget(self._btn_delete)
        footer.addStretch(1)
        footer.addWidget(self._btn_close)
        root.addLayout(footer)

        self.setStyleSheet(dialog_style(self._owner))

    # ── H2 修复：异步加载 ──

    def _reload(self):
        """异步查询 bookmarks，缓存后渲染"""
        self._list.clear()
        placeholder = QListWidgetItem("加载中…")
        self._list.addItem(placeholder)
        self._loader.load(
            "bookmarks",
            self._on_bookmarks_loaded,
            limit=500,
        )

    def _on_bookmarks_loaded(self, items):
        """后台线程回调 → 缓存 + 渲染"""
        self._items_cache = list(items)
        self._render_list()

    def _render_list(self):
        """同步渲染缓存到 QListWidget"""
        self._list.clear()
        if not self._items_cache:
            placeholder = QListWidgetItem("暂无收藏")
            self._list.addItem(placeholder)
            return
        for bm in self._items_cache:
            title = bm.get("title") or bm.get("url")
            item = QListWidgetItem(f"★ {title}\n   {bm.get('url')}")
            item.setData(Qt.UserRole, bm.get("url"))
            item.setToolTip(bm.get("url"))
            self._list.addItem(item)

    def _add_current(self):
        view = self._owner._current_view()
        if view is None:
            return
        url = view.url().toString()
        if not url or url == "about:blank":
            return
        idx = self._owner._tab_bar.currentIndex()
        title = self._owner._views[idx].get("title", "")
        add_bookmark(url, title)
        self._reload()

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

    def _delete_selected(self):
        item = self._list.currentItem()
        if item:
            url = item.data(Qt.UserRole)
            if url:
                remove_bookmark(url)
            self._reload()


def show_bookmarks_panel(owner):
    """从浏览器卡片打开收藏面板（单例复用）"""
    if not hasattr(owner, "_bookmarks_panel") or owner._bookmarks_panel is None:
        owner._bookmarks_panel = BookmarksPanel(owner)
    owner._bookmarks_panel.setStyleSheet(dialog_style(owner))
    owner._bookmarks_panel._reload()
    owner._bookmarks_panel.show()
    owner._bookmarks_panel.raise_()