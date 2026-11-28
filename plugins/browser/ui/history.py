# -*- coding: utf-8 -*-
"""历史记录 — 历史面板 + 数据操作

H2 修复：_reload 走 AsyncDataLoader 后台线程，主线程不阻塞。
打开面板时缓存为空 → 立即显示空列表 + 加载状态；后台数据到达后回填渲染。

UI 结构（与收藏/下载一致）：
- 头部：图标 + 标题 + 搜索框
- 中部：QListWidget
- 底部：打开 / 清空，关闭按钮位于标题行
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

from .data import AsyncDataLoader, clear_history
from .panel_base import PageRowDelegate, _PanelMixin, apply_panel_theme, build_footer, build_header, show_singleton_panel


class HistoryPanel(QFrame, _PanelMixin):
    """浏览器卡片内的悬浮历史记录面板（统一基类 _PanelMixin）"""

    preferred_size = (500, 380)

    def __init__(self, owner, parent=None):
        super().__init__(parent or owner)
        self._owner = owner
        self.setObjectName("historyPanel")
        self._loader = AsyncDataLoader(self)
        self._items_cache: List[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        root.addLayout(build_header(self, self._owner, "历史记录", icon=FluentIcon.HISTORY))
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("搜索标题或网址")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._reload)
        root.addWidget(self._search)

        from PyQt5.QtWidgets import QListWidget
        self._list = QListWidget(self)
        self._list.setItemDelegate(PageRowDelegate(self._list))
        self._list.itemDoubleClicked.connect(self._open_item)
        root.addWidget(self._build_results(), 1)

        def _footer_actions(footer: QHBoxLayout):
            self._btn_open = QPushButton("打开", self)
            self._btn_clear = QPushButton("清空历史", self)
            self._btn_open.clicked.connect(self._open_selected)
            self._btn_open.setEnabled(False)
            self._list.itemSelectionChanged.connect(lambda: self._btn_open.setEnabled(bool(self._list.selectedItems())))
            self._btn_clear.clicked.connect(self._clear)
            footer.addWidget(self._btn_open)
            footer.addWidget(self._btn_clear)

        root.addLayout(build_footer(_footer_actions))

    # ── H2 修复：异步加载 ──

    def _list_query(self):
        text = self._search.text().strip()
        if text:
            return "search_history", {"keyword": text, "limit": 100}
        return "history", {"limit": 200}

    def _render_items(self):
        """同步渲染缓存到 QListWidget（毫秒级，500+ 条不卡）"""
        self._list.clear()
        if not self._items_cache:
            self._show_message("没有匹配的历史记录" if self._search.text().strip() else "暂无浏览记录")
            return
        for h in self._items_cache:
            title = h.get("title") or h.get("url")
            count = h.get("visit_count", 1)
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole + 1, f"{count} 次访问 · {h.get('url')}")
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
