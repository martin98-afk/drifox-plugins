# -*- coding: utf-8 -*-
"""收藏管理 — 收藏面板 + 数据操作

H2 修复：_reload 走 AsyncDataLoader 后台线程，主线程不阻塞。

通过浏览器卡片的菜单 → 收藏夹 打开面板。
支持：打开收藏、删除收藏、从当前页添加收藏。
"""

from typing import List

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon

from .data import AsyncDataLoader, add_bookmark, remove_bookmark
from .panel_base import _PanelMixin, build_footer, build_header, show_singleton_panel
from .theme import font_css, scrollbar_style, theme_colors


class BookmarkBar(QWidget):
    """地址栏下方的动态收藏栏，空间不足时把剩余项目放入溢出面板。"""

    open_url = pyqtSignal(str)

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._items: List[dict] = []
        self._visible_buttons = []
        self._overflow_items: List[dict] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 2, 8, 2)
        self._layout.setSpacing(4)
        self._more_btn = QToolButton(self)
        self._more_btn.setIcon(FluentIcon.MORE.qicon())
        self._more_btn.setToolTip("更多收藏")
        self._more_btn.clicked.connect(self._toggle_overflow)
        self._overflow = self._build_overflow(owner)
        self.setFixedHeight(34)
        self.hide()

    def _build_overflow(self, parent):
        panel = QFrame(parent)
        panel.setObjectName("bookmarkOverflow")
        panel.setFixedSize(280, 300)
        root = QVBoxLayout(panel)
        root.setContentsMargins(6, 6, 6, 6)
        scroll = QScrollArea(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget(scroll)
        self._overflow_layout = QVBoxLayout(body)
        self._overflow_layout.setContentsMargins(0, 0, 0, 0)
        self._overflow_layout.setSpacing(2)
        self._overflow_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll)
        self._overflow_scroll = scroll
        panel.hide()
        return panel

    def set_items(self, items):
        self._items = list(items)
        self.setVisible(bool(self._items))
        self._rebuild()

    def apply_theme(self):
        c = theme_colors(self._owner)
        button = (
            "QToolButton { border: none; border-radius: 6px; padding: 3px 10px;"
            f" {font_css(c['ff'], c['fs'] - 1)} color: {c['text']};"
            " background: transparent; text-align: left; }"
            f"QToolButton:hover {{ background: {c['hover']}; }}"
        )
        self.setStyleSheet(button)
        self._overflow.setStyleSheet(
            f"QFrame#bookmarkOverflow {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; }}"
            + button
            + scrollbar_style(self._owner)
        )

    def _clear_layout(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._more_btn:
                widget.deleteLater()
        self._visible_buttons.clear()

    def _make_button(self, item, parent):
        title = item.get("title") or item.get("url") or "收藏"
        btn = QToolButton(parent)
        btn.setText(title)
        btn.setToolTip(f"{title}\n{item.get('url', '')}")
        btn.setMaximumWidth(160)
        btn.clicked.connect(
            lambda checked=False, url=item.get("url", ""): self._open(url)
        )
        return btn

    def _rebuild(self):
        self._clear_layout()
        if not self._items:
            self._overflow.hide()
            return
        available = max(80, self.width() - 30)
        used = 0
        visible, overflow = [], []
        for item in self._items:
            probe = self._make_button(item, self)
            width = min(160, max(60, probe.sizeHint().width())) + self._layout.spacing()
            if used + width <= available:
                visible.append((item, probe))
                used += width
            else:
                probe.deleteLater()
                overflow.append(item)
        for item, button in visible:
            self._layout.addWidget(button)
            self._visible_buttons.append(button)
        self._overflow_items = overflow
        self._layout.addStretch(1)
        if overflow:
            self._layout.addWidget(self._more_btn)
            self._more_btn.show()
        else:
            self._more_btn.hide()
            self._overflow.hide()
        self._rebuild_overflow()
        self.apply_theme()

    def _rebuild_overflow(self):
        while self._overflow_layout.count() > 1:
            item = self._overflow_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for bookmark in self._overflow_items:
            self._overflow_layout.insertWidget(
                self._overflow_layout.count() - 1,
                self._make_button(bookmark, self._overflow),
            )

    def _toggle_overflow(self):
        visible = not self._overflow.isVisible()
        if visible:
            anchor = self._more_btn.mapTo(
                self._owner, self._more_btn.rect().bottomRight()
            )
            x = max(8, anchor.x() - self._overflow.width())
            self._overflow.move(x, anchor.y() + 4)
            self._overflow.raise_()
        self._overflow.setVisible(visible)

    def _open(self, url):
        if url:
            self._overflow.hide()
            self.open_url.emit(url)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild()


class BookmarksPanel(QFrame, _PanelMixin):
    """收藏管理面板（卡片内嵌悬浮 QFrame，与历史/下载弹窗同格式）

    H2 修复：异步加载，统一基类 _PanelMixin。
    弹窗格式统一：原为 QDialog 独立窗口，现与历史面板一致 —
    浏览器卡片内悬浮、菜单按钮下方定位（owner._position_popup）。
    """

    open_url = pyqtSignal(str)

    def __init__(self, owner, parent=None):
        super().__init__(parent or owner)
        self._owner = owner
        self.setObjectName("bookmarksPanel")
        self.setFixedSize(460, 320)
        self._loader = AsyncDataLoader(self)
        self._items_cache: List[dict] = []
        self._setup_ui()
        self._reload()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        def _header_actions(header: QHBoxLayout, _colors):
            self._btn_add = QPushButton("收藏当前页", self)
            self._btn_add.clicked.connect(self._add_current)
            header.addWidget(self._btn_add)

        root.addLayout(
            build_header(
                self, self._owner, "收藏夹",
                icon=FluentIcon.BOOK_SHELF, actions=_header_actions,
            )
        )

        self._list = QListWidget(self)
        self._list.itemDoubleClicked.connect(self._open_item)
        root.addWidget(self._list, 1)

        def _footer_actions(footer: QHBoxLayout):
            self._btn_open = QPushButton("打开", self)
            self._btn_delete = QPushButton("删除", self)
            self._btn_open.clicked.connect(self._open_selected)
            self._btn_delete.clicked.connect(self._delete_selected)
            footer.addWidget(self._btn_open)
            footer.addWidget(self._btn_delete)

        root.addLayout(build_footer(self, actions=_footer_actions))

        from .panel_base import apply_panel_theme
        apply_panel_theme(self, self._owner)

    # ── H2 修复：异步加载（统一基类 _reload_async） ──

    def _reload_async(self):
        """异步查询 bookmarks，缓存后渲染"""
        self._loader.load(
            "bookmarks",
            self._on_items_loaded,
            limit=500,
        )

    def _render_items(self):
        """同步渲染缓存到 QListWidget"""
        self._list.clear()
        if not self._items_cache:
            placeholder = QListWidgetItem("暂无收藏")
            self._list.addItem(placeholder)
            return
        for bm in self._items_cache:
            title = bm.get("title") or bm.get("url")
            item = QListWidgetItem(f"{title}\n   {bm.get('url')}")
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
            self.hide()  # 与历史面板一致：打开后收起悬浮面板

    def _delete_selected(self):
        item = self._list.currentItem()
        if item:
            url = item.data(Qt.UserRole)
            if url:
                remove_bookmark(url)
            self._reload()

    def showEvent(self, event):
        super().showEvent(event)
        from .panel_base import apply_panel_theme
        apply_panel_theme(self, self._owner)


def show_bookmarks_panel(owner):
    """从浏览器卡片打开收藏面板（单例复用 + 主题刷新 + 卡片内定位）

    与历史/下载面板同格式：position=True → owner._position_popup 在
    菜单按钮下方定位，卡片内悬浮显示。
    """
    show_singleton_panel(
        owner, "_bookmarks_panel",
        factory=lambda o: BookmarksPanel(o, o),
        position=True,
    )
