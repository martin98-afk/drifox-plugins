# -*- coding: utf-8 -*-
"""隐身模式 — 独立窗口 + 全新 OTR Profile（关闭即焚，无残留）

H1 修复：
- 每次 open_incognito_window() 调用 get_incognito_profile() 拿到全新匿名 profile
- 不再复用旧的 module-level 单例
- closeEvent 显式调用 purge_incognito_profile() 清空 Cookie/HttpCache/ServiceWorker 残留
- 释放 self._profile 引用让 Qt 端销毁 OTR profile

样式改造（子任务 #18，遵循 frontend-architect 架构守则）：
- 主题 token 化：颜色/字号全部由 theme.theme_colors() 派生（真 token，QSS 收口 theme.py）
- owner ctx：继承浏览器主卡片（BrowserWindowCard）的 _context_provider，ctx 真正生效
- 去 emoji：banner/窗口标题改纯文字；「＋」换 FluentIcon.ADD SVG 图标
- 统一刷新入口 _apply_theme()：所有控件（横幅/按钮/窗口/复用组件）一次收敛

- 独立 QMainWindow（带工具栏/地址栏/标签栏，复用浏览器组件）
- QWebEngineProfile() 匿名实例 → OTR：无 Cookie/历史/缓存持久化
- 关闭窗口即销毁 Profile，无痕迹
"""

from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QMainWindow, QWidget
from qfluentwidgets import FluentIcon

from ._page_factory import create_page
from .profile_manager import get_incognito_profile, purge_incognito_profile
from .tab_widget import ChromeTabBar
from .theme import _adjust_color, font_css, theme_colors
from .url_bar import UrlBar

# 保持窗口引用（防止 GC）
_open_windows = []


class IncognitoWindow(QMainWindow):
    """隐身浏览器窗口（每次全新 OTR Profile）"""

    def __init__(self, parent=None, owner=None):
        super().__init__(parent)
        # 继承浏览器主卡片上下文（深色/字号/colors），未提供时按 isDarkTheme fallback
        self._context_provider = getattr(owner, "_context_provider", None)
        self._c = theme_colors(self)  # 主题派生色缓存（供动态控件复用）
        self._is_dark = self._c["is_dark"]
        self.setWindowTitle("隐身窗口 — DriFox 浏览器")
        self.resize(1100, 720)
        self.setWindowFlag(Qt.Window)
        # 每次全新匿名 OTR profile（H1：不缓存、不复用）
        self._profile = get_incognito_profile()
        self._views = []  # [{view, url, title}]
        self._setup_ui()
        self._apply_theme()
        self._new_tab()

    # ── 主题（统一刷新入口） ──

    def _apply_theme(self):
        """拉取最新 ctx，收敛刷新全部控件样式（主题/字号切换后调用）。"""
        c = theme_colors(self)
        self._c = c
        self._is_dark = c["is_dark"]

        # 隐身横幅：tag_purple 系，调深一档保证白字对比度（深色主题 #b388ff 偏亮）
        banner_bg = _adjust_color(c["tag_purple"], -30)
        self._banner.setStyleSheet(
            f"background: {banner_bg}; color: #ffffff; padding: 6px 12px;"
            f" {font_css(c['ff'], max(11, c['fs'] - 1))}"
        )

        # 工具栏：窗口背景 + 新标签按钮（28×28 / 圆角 6px / fs 字号 / hover_bg）
        self.setStyleSheet(f"QMainWindow {{ background: {c['surface']}; }}")
        self._btn_new_tab.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 6px; {font_css(c['ff'], max(11, c['fs'] - 1))}"
            f" color: {c['text']}; }}"
            f"QToolButton:hover {{ background: {c['hover']}; }}"
            f"QToolButton:pressed {{ background: {c['selected']}; }}"
        )

        # 页面区背景
        self._stack.setStyleSheet(f"QStackedWidget {{ background: {c['surface']}; }}")

        # 复用组件：新签名统一传完整主题 dict
        self._url_bar.apply_theme(c)
        self._tab_bar.apply_theme(c)

    # ── UI 搭建 ──

    def _setup_ui(self):
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QToolButton, QVBoxLayout

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 隐身横幅（样式由 _apply_theme 统一收敛）
        self._banner = QLabel("您已进入隐身模式 — 不会保存浏览历史、Cookie、表单数据", central)
        root.addWidget(self._banner)

        # 工具栏
        toolbar = QWidget(central)
        tly = QHBoxLayout(toolbar)
        tly.setContentsMargins(8, 6, 8, 2)
        tly.setSpacing(2)

        self._url_bar = UrlBar(toolbar)
        self._url_bar.navigate_requested.connect(self._navigate)
        tly.addWidget(self._url_bar, 1)

        # 新标签按钮（SVG 图标，样式由 _apply_theme 收敛）
        self._btn_new_tab = QToolButton(toolbar)
        self._btn_new_tab.setIcon(FluentIcon.ADD.qicon())
        self._btn_new_tab.setIconSize(QSize(16, 16))
        self._btn_new_tab.setFixedSize(28, 28)
        self._btn_new_tab.setToolTip("新建标签")
        self._btn_new_tab.clicked.connect(self._new_tab)
        tly.addWidget(self._btn_new_tab)

        root.addWidget(toolbar)

        # 标签栏
        self._tab_bar = ChromeTabBar(central)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tabCloseRequested.connect(self._close_tab)
        self._tab_bar.new_tab_requested.connect(self._new_tab)
        root.addWidget(self._tab_bar)

        # 页面区
        self._stack = QStackedWidget(central)
        root.addWidget(self._stack, 1)

    # ── 标签管理 ──

    def _new_tab(self, url: str = ""):
        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        # N2 修复：统一通过 _page_factory.create_page() 创建（共享 browser_window）
        view.setPage(create_page(view, self._profile, self._new_popup_page, self._is_dark))

        idx = len(self._views)
        self._views.append({"view": view, "url": url, "title": "新标签页"})
        self._stack.addWidget(view)

        view.titleChanged.connect(lambda t, i=idx: self._on_title(i, t))
        view.urlChanged.connect(lambda u, i=idx: self._on_url(i, u))
        view.loadStarted.connect(lambda i=idx: self._tab_bar.setTabText(i, "● 加载中…"))
        view.loadFinished.connect(lambda ok, i=idx: self._on_loaded(i, ok))

        self._tab_bar.addTab("新标签页")
        self._tab_bar.setCurrentIndex(idx)
        self._stack.setCurrentIndex(idx)

        if url:
            view.setUrl(_to_qurl(url))
        return idx

    def _new_popup_page(self, url=None):
        """由右键菜单显式在隐身窗口的新标签打开链接。"""
        target = url.toString() if hasattr(url, "toString") else (url or "")
        idx = self._new_tab(target)
        return self._views[idx]["view"].page()

    def _close_tab(self, idx: int):
        if idx < 0 or idx >= len(self._views):
            return
        entry = self._views.pop(idx)
        self._tab_bar.removeTab(idx)
        view = entry.get("view")
        if view is not None:
            self._stack.removeWidget(view)
            view.deleteLater()
        if not self._views:
            self._new_tab()

    def _on_tab_changed(self, idx: int):
        if 0 <= idx < len(self._views):
            self._stack.setCurrentIndex(idx)
            self._url_bar.set_url(self._views[idx].get("url", ""))

    def _on_title(self, idx: int, title: str):
        if 0 <= idx < len(self._views):
            self._views[idx]["title"] = title
            self._tab_bar.setTabText(idx, title)

    def _on_url(self, idx: int, url):
        if 0 <= idx < len(self._views):
            self._views[idx]["url"] = url.toString()
            if idx == self._tab_bar.currentIndex():
                self._url_bar.set_url(url.toString())

    def _on_loaded(self, idx: int, ok: bool):
        if 0 <= idx < len(self._views):
            self._tab_bar.setTabText(idx, self._views[idx].get("title", ""))

    # ── 导航 ──

    def _navigate(self, url: str):
        idx = self._tab_bar.currentIndex()
        if 0 <= idx < len(self._views):
            self._views[idx]["view"].setUrl(_to_qurl(url))

    # ── H1 修复：关闭时彻底清理 OTR profile ──

    def closeEvent(self, event):
        # 1) 销毁所有 view（释放页面/渲染进程引用）
        for entry in self._views:
            view = entry.get("view")
            if view is not None:
                try:
                    view.deleteLater()
                except RuntimeError:
                    pass
        self._views.clear()

        # 2) 显式清理 OTR profile 的 Cookie/HttpCache/ServiceWorker 残留
        #    （即使匿名 profile 销毁时也会自动释放，这里兜底确保无残留）
        purge_incognito_profile(self._profile)

        # 3) 释放 profile 引用 → Qt 端可销毁匿名 profile
        self._profile = None

        # 4) 从全局窗口列表移除
        if self in _open_windows:
            _open_windows.remove(self)

        super().closeEvent(event)


def _to_qurl(url: str):
    from PySide6.QtCore import QUrl

    return QUrl(url)


def open_incognito_window(owner=None) -> Optional[IncognitoWindow]:
    """打开新的隐身窗口（每次独立 OTR Profile，H1 修复后无 Cookie 残留）"""
    win = IncognitoWindow(owner=owner)
    _open_windows.append(win)
    win.show()
    win.raise_()
    win.activateWindow()
    return win


def close_all_incognito_windows():
    """热重载/卸载时关闭所有隐身窗口（释放 OTR profile）"""
    for win in list(_open_windows):
        try:
            win.close()
        except RuntimeError:
            pass
        if win in _open_windows:
            _open_windows.remove(win)