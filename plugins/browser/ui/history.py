# -*- coding: utf-8 -*-
"""历史记录 — 历史面板 + 数据操作

H2 修复：_reload 走 AsyncDataLoader 后台线程，主线程不阻塞。
打开面板时缓存为空 → 立即显示空列表 + 加载状态；后台数据到达后回填渲染。

UI 结构（与收藏/下载一致）：
- 头部：图标 + 标题 + 搜索框
- 中部：QListWidget
- 底部：打开 / 清空 / 关闭
"""

from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from qfluentwidgets import FluentIcon

from loguru import logger

from .data import AsyncDataLoader, clear_history
from .panel_base import _PanelMixin, apply_panel_theme, build_footer, build_header, show_singleton_panel


class HistoryPanel(QFrame, _PanelMixin):
    """浏览器卡片内的悬浮历史记录面板（统一基类 _PanelMixin）"""

    def __init__(self, owner, parent=None):
        super().__init__(parent or owner)
        self._owner = owner
        self.setObjectName("historyPanel")
        self.setFixedSize(420, 270)
        self._loader = AsyncDataLoader(self)
        self._items_cache: List[dict] = []
        self._setup_ui()
        self._reload()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        def _header_actions(header: QHBoxLayout, _colors):
            self._search = QLineEdit(self)
            self._search.setPlaceholderText("搜索历史…")
            self._search.textChanged.connect(self._on_search)
            self._search.setClearButtonEnabled(True)
            self._search.setFixedWidth(200)
            header.addWidget(self._search)

        root.addLayout(
            build_header(
                self, self._owner, "历史记录",
                icon=FluentIcon.HISTORY, actions=_header_actions,
            )
        )

        from PyQt5.QtWidgets import QListWidget
        self._list = QListWidget(self)
        self._list.itemDoubleClicked.connect(self._open_item)
        root.addWidget(self._list, 1)

        def _footer_actions(footer: QHBoxLayout):
            self._btn_open = QPushButton("打开", self)
            self._btn_clear = QPushButton("清空历史", self)
            self._btn_open.clicked.connect(self._open_selected)
            self._btn_clear.clicked.connect(self._clear)
            footer.addWidget(self._btn_open)
            footer.addWidget(self._btn_clear)

        root.addLayout(build_footer(self, actions=_footer_actions))

    # ── H2 修复：异步加载 ──

    def _reload_async(self):
        """异步查询 history（走 AsyncDataLoader，主线程不阻塞）"""
        self._loader.load(
            "history",
            self._on_items_loaded,
            limit=200,
        )

    def _on_search(self, text: str):
        """搜索也走异步（H2 修复）"""
        text = text.strip()
        self._list.clear()
        placeholder = QListWidgetItem("加载中…")
        self._list.addItem(placeholder)
        if text:
            self._loader.load(
                "search_history",
                self._on_items_loaded,
                on_error=lambda e: logger.error(f"[browser] 搜索历史失败: {e}"),
                keyword=text,
                limit=100,
            )
        else:
            self._loader.load(
                "history",
                self._on_items_loaded,
                limit=200,
            )

    def _render_items(self):
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

        if (
            QMessageBox.question(self, "清空历史", "确定要清空全部历史记录吗？")
            == QMessageBox.Yes
        ):
            n = clear_history()
            self._reload()
            self._owner._set_status(f"已清空 {n} 条历史记录")

    def showEvent(self, event):
        super().showEvent(event)
        # 主题切换后重新应用样式
        apply_panel_theme(self, self._owner)


def show_history_panel(owner):
    """从浏览器卡片打开历史面板（单例复用 + 主题刷新 + 卡片内定位）"""
    show_singleton_panel(
        owner, "_history_panel",
        factory=lambda o: HistoryPanel(o, o),
        position=True,
    )