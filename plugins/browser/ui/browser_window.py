# -*- coding: utf-8 -*-
"""浏览器主窗口（浮动卡片）— M1 基础浏览器

结构（Chrome 风格）：
┌──────────────────────────────────────────┐
│ [<][>][reload][stop] [ 地址栏 ] [+][menu] │  ← 工具栏
│ ┌────┐┌────┐┌────┐                       │  ← 标签栏
│ │Tab1││Tab2││Tab3│                       │
│ └────┘└────┘└────┘                       │
│ ┌──────────────────────────────────────┐ │
│ │          QStackedWidget              │ │  ← 页面区
│ │      (每个标签一个 QWebEngineView)    │ │
│ └──────────────────────────────────────┘ │
│ [收藏] [历史] [下载] [DevTools] [隐身]    │  ← 底部状态栏
└──────────────────────────────────────────┘

性能设计（M3 强化）：
- MAX_ALIVE_TABS=6：超过时后台标签 setLifecycleState(Frozen) 释放内存
- 懒创建：标签页只在激活时创建 QWebEngineView（延迟到首次显示）
- 地址栏进度合并：url_bar 内置 QTimer 合并 80ms 内连续进度更新（无需主卡片介入）
"""

import os
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon

from ._page_factory import create_page
from .bookmarks import BookmarkBar
from .data import AsyncDataLoader, add_bookmark, record_history, remove_bookmark
from .profile_manager import get_browser_profile, reset_profiles
from .tab_widget import ChromeTabBar, MAX_ALIVE_TABS
from .theme import font_css, theme_colors
from .url_bar import UrlBar, is_blank_page, normalize_url

# 图标资源目录（ui/assets/）
_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# 内核 H.264 解码能力（内核级属性，与页面无关 → 只探测一次，缓存结果）
_H264_SUPPORTED: Optional[bool] = None
_NO_H264_HINT = "当前内核不支持 H.264 视频播放，可点右上角用外部浏览器打开"


def _icon_path(name: str, is_dark: bool) -> str:
    """返回 assets 下图标路径：深色主题用 _dark 后缀版本"""
    return os.path.join(_ICON_DIR, f"{name}_dark.svg" if is_dark else f"{name}.svg")


def _tool_btn_style(c: dict) -> str:
    """工具栏按钮 QSS：28×28 布局 + 6px 圆角 + fs 字号 + hover token。"""
    return (
        "QToolButton { border: none; border-radius: 6px;"
        f" {font_css(c['ff'], max(10, c['fs'] - 1))} color: {c['text']};"
        " background: transparent; }"
        f"QToolButton:hover {{ background: {c['hover']}; }}"
        f"QToolButton:pressed {{ background: {c['hover']}; }}"
        f"QToolButton:disabled {{ color: {c['secondary']}; }}"
    )


# 模块级单例引用（供 function 命令 handler 访问，热重载时更新）
_CURRENT_CARD: Optional["BrowserWindowCard"] = None


def _get_current_card() -> Optional["BrowserWindowCard"]:
    """获取当前浏览器卡片实例（用于 function 命令 handler）"""
    return _CURRENT_CARD


class BrowserWindowCard(QWidget):
    """浏览器浮动卡片"""

    closed = Signal()

    # ── 生命周期管理 ──

    def __init__(self, parent=None):
        super().__init__(parent)
        global _CURRENT_CARD
        _CURRENT_CARD = self

        self._context_provider = None
        self._is_dark = True
        self._c = theme_colors(None)  # 主题派生色缓存（apply_theme 前的默认观感）
        self._loader = AsyncDataLoader(self)
        self._views = []  # [{view, url, title, placeholder}]
        # H2 修复：地址栏补全数据走异步加载，主线程读内存缓存
        self._suggestions_cache: List[Tuple[str, str]] = []
        self._bookmarks_cache: List[dict] = []

        self._setup_ui()
        self._setup_shortcuts()
        self._new_tab()
        # 主题实时刷新：主程序 theme_manager reload 时回调 refresh_theme()
        try:
            from app.utils.theme_manager import theme_manager

            theme_manager.register_refresh_target(self)
        except Exception:
            pass

    def set_context_provider(self, provider):
        self._context_provider = provider

    def show_card(self):
        """浮动卡片显示时调用（registry 拉模型）"""
        self.refresh_theme()
        self._refresh_panels()
        self.setVisible(True)

    def refresh_theme(self):
        """主题实时刷新入口：_apply_theme + 已加载 WebEngine 页面背景重设。"""
        self._apply_theme()
        c = theme_colors(self)
        for entry in self._views:
            view = entry.get("view")
            if view is not None:
                try:
                    view.page().setBackgroundColor(QColor(c["surface"]))
                except Exception:
                    pass

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumSize(520, 320)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("BrowserWindowCard { background: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 工具栏 ──
        toolbar = QWidget(self)
        toolbar.setObjectName("browserToolbar")
        toolbar.setStyleSheet("#browserToolbar { background: transparent; }")
        tly = QHBoxLayout(toolbar)
        tly.setContentsMargins(12, 8, 12, 4)
        tly.setSpacing(2)

        self._btn_back = self._make_tool_btn(FluentIcon.LEFT_ARROW, "后退")
        self._btn_forward = self._make_tool_btn(FluentIcon.RIGHT_ARROW, "前进")
        self._btn_reload = self._make_tool_btn(FluentIcon.SYNC, "刷新")
        self._btn_stop = self._make_tool_btn(FluentIcon.CANCEL, "停止")
        self._btn_stop.setVisible(False)
        tly.addWidget(self._btn_back)
        tly.addWidget(self._btn_forward)
        tly.addWidget(self._btn_reload)
        tly.addWidget(self._btn_stop)

        self._btn_back.clicked.connect(self._go_back)
        self._btn_forward.clicked.connect(self._go_forward)
        self._btn_reload.clicked.connect(self._reload)
        self._btn_stop.clicked.connect(self._stop)

        # 地址栏
        self._url_bar = UrlBar(toolbar)
        self._url_bar.navigate_requested.connect(self._navigate_to_url)
        self._url_bar.set_completer_source(self._get_suggestions)
        tly.addWidget(self._url_bar, 1)

        # 收藏星标（★/☆ 保留字符，_update_bookmark_state 动态切换）
        self._btn_bookmark = self._make_tool_btn("☆", "收藏当前网页")
        self._btn_bookmark.clicked.connect(self._toggle_current_bookmark)
        tly.addWidget(self._btn_bookmark)

        # 新标签按钮
        self._btn_new_tab = self._make_tool_btn(FluentIcon.ADD, "新建标签")
        self._btn_new_tab.clicked.connect(self._new_tab)
        tly.addWidget(self._btn_new_tab)

        # 菜单按钮（收藏/历史/下载）
        self._btn_menu = self._make_tool_btn(FluentIcon.MENU, "菜单")
        self._btn_menu.clicked.connect(self._toggle_menu)
        tly.addWidget(self._btn_menu)

        # 在外部浏览器打开（系统默认浏览器，绕过内置浏览器重定向）
        self._btn_external = self._make_tool_btn(
            QIcon(_icon_path("external_open", self._is_dark)), "在外部浏览器打开"
        )
        self._btn_external.clicked.connect(self._open_in_system_browser)
        tly.addWidget(self._btn_external)

        self._btn_close = self._make_tool_btn(FluentIcon.CLOSE, "关闭浏览器")
        self._btn_close.clicked.connect(self._close_card)
        tly.addWidget(self._btn_close)

        root.addWidget(toolbar)

        # ── 收藏栏（有收藏时显示）──
        self._bookmark_bar = BookmarkBar(self, self)
        self._bookmark_bar.open_url.connect(self._navigate_to_url)
        root.addWidget(self._bookmark_bar)

        # ── 标签栏 ──
        tab_row = QWidget(self)
        trly = QHBoxLayout(tab_row)
        trly.setContentsMargins(12, 0, 12, 0)
        trly.setSpacing(4)

        self._tab_bar = ChromeTabBar(tab_row)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tabCloseRequested.connect(self._close_tab)
        self._tab_bar.new_tab_requested.connect(self._new_tab)
        self._tab_bar.close_others_requested.connect(self._close_others)
        self._tab_bar.tabMoved.connect(self._on_tab_moved)
        trly.addWidget(self._tab_bar, 1)

        # 隐身标识（默认隐藏）
        self._incognito_badge = QLabel("隐身", tab_row)
        self._incognito_badge.setVisible(False)
        self._incognito_badge.setStyleSheet(
            f"{font_css(self._c['ff'], max(10, self._c['fs'] - 2))}"
            f" color: {self._c['tag_purple']}; padding: 0 8px;"
        )
        trly.addWidget(self._incognito_badge)

        root.addWidget(tab_row)

        # ── 页面区（QStackedWidget）──
        self._stack = QStackedWidget(self)
        self._stack.setStyleSheet(
            f"QStackedWidget {{ background: {self._c['surface']}; border: none; }}"
        )
        root.addWidget(self._stack, 1)

        # ── 底部状态栏 ──
        status = QWidget(self)
        sly = QHBoxLayout(status)
        sly.setContentsMargins(12, 2, 12, 6)
        sly.setSpacing(4)

        self._status_lb = QLabel("就绪", status)
        self._status_lb.setStyleSheet(
            f"{font_css(self._c['ff'], max(10, self._c['fs'] - 1))}"
            f" color: {self._c['secondary']}; background: transparent;"
        )
        sly.addWidget(self._status_lb)
        sly.addStretch(1)

        # 拦截配置摘要（右侧）：让用户一眼看到拦截开关状态
        from .redirect_config import config_summary

        self._intercept_status_lb = QLabel(config_summary(), status)
        self._intercept_status_lb.setStyleSheet(
            f"{font_css(self._c['ff'], max(10, self._c['fs'] - 2))}"
            f" color: {self._c['muted']}; background: transparent; padding: 0 4px;"
        )
        self._intercept_status_lb.setCursor(Qt.PointingHandCursor)
        self._intercept_status_lb.setToolTip("点击打开浏览器拦截设置")
        self._intercept_status_lb.mousePressEvent = lambda _e: self._open_redirect_settings()
        sly.addWidget(self._intercept_status_lb)

        self._menu_panel = self._build_menu_panel(self)
        self._menu_panel.setVisible(False)

        self._status_widget = status
        status.setVisible(False)
        root.addWidget(status)

    def _make_tool_btn(self, icon, tip: str) -> QToolButton:
        """工具栏按钮：支持 FluentIcon/qicon、QIcon 或文本（★/☆ 收藏星标）。"""
        btn = QToolButton(self)
        if isinstance(icon, str):
            btn.setText(icon)
        else:
            if hasattr(icon, "qicon"):
                icon = icon.qicon()
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))
        btn.setToolTip(tip)
        btn.setFixedSize(28, 28)
        btn.setStyleSheet(_tool_btn_style(self._c))
        return btn

    # ── 标签管理 ──

    def _new_tab(self, url: str = ""):
        """新建标签（懒创建：先占位，激活时才创建 WebEngineView）"""
        # 懒渲染：占位 widget 直到真正显示
        placeholder = QWidget(self._stack)
        placeholder.setStyleSheet(f"background: {self._c['surface']};")

        idx = self._stack.addWidget(placeholder)
        self._views.append(
            {
                "view": None,
                "url": url or "",
                "title": "新标签页",
                "placeholder": placeholder,
            }
        )

        self._tab_bar.addTab("新标签页")
        self._tab_bar.setCurrentIndex(idx)
        self._stack.setCurrentWidget(placeholder)

        if url:
            self._ensure_view(idx)
        else:
            # 空白页显示起始页
            self._ensure_view(idx)
        self._update_tab_buttons()
        self._apply_tab_limits()
        return idx

    def _ensure_view(self, idx: int):
        """确保指定标签的 WebEngineView 已创建（懒加载）"""
        entry = self._views[idx]
        if entry["view"] is not None:
            return entry["view"]

        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        view.setPage(
            create_page(
                view, get_browser_profile(), self._new_popup_page, self._is_dark
            )
        )
        entry["view"] = view

        # WebEngine 防白闪：页面背景色跟随主题（主题切换时 refresh_theme 重设）
        try:
            view.page().setBackgroundColor(QColor(self._c["surface"]))
        except Exception:
            pass

        # 替换占位
        self._stack.removeWidget(entry["placeholder"])
        entry["placeholder"].deleteLater()
        entry["placeholder"] = None
        self._stack.insertWidget(idx, view)
        self._stack.setCurrentWidget(view)

        # 信号连接
        view.urlChanged.connect(lambda u, v=view: self._on_url_changed(v, u))
        view.titleChanged.connect(lambda t, v=view: self._on_title_changed(v, t))
        view.loadStarted.connect(lambda v=view: self._on_load_started(v))
        view.loadProgress.connect(lambda p, v=view: self._on_load_progress(v, p))
        view.loadFinished.connect(lambda ok, v=view: self._on_load_finished(v, ok))
        view.iconChanged.connect(lambda ic, v=view: self._on_icon_changed(v, ic))

        # 下载托管（M2）
        from .downloads import attach_download_handler

        attach_download_handler(view, self)

        # 历史记录（M2）：加载完成后记录，避免重复
        view.loadFinished.connect(lambda ok, v=view: self._on_page_loaded(v, ok))

        target = entry["url"]
        if target:
            entry["url"] = ""
            view.setUrl(_to_qurl(target))
        else:
            view.setHtml(_start_page_html(theme_colors(self)), _to_qurl("about:blank"))
        return view

    def _new_popup_page(self, url=None):
        """由右键菜单显式在新标签打开链接。"""
        target = url.toString() if hasattr(url, "toString") else (url or "")
        idx = self._new_tab(target)
        view = self._views[idx].get("view")
        return view.page() if view is not None else None

    def _close_tab(self, idx: int):
        if idx < 0 or idx >= len(self._views):
            return
        entry = self._views.pop(idx)
        self._tab_bar.removeTab(idx)
        # 记录关闭栈（Ctrl+Shift+T 恢复）
        closed_url = entry.get("url") or ""
        if closed_url and not is_blank_page(closed_url):
            if not hasattr(self, "_closed_stack"):
                self._closed_stack = []
            self._closed_stack.append(closed_url)
            if len(self._closed_stack) > 10:
                self._closed_stack.pop(0)
        view = entry.get("view")
        if view is not None:
            self._stack.removeWidget(view)
            view.deleteLater()
        self._apply_tab_limits()
        if not self._views:
            # 全部关闭 → 新建一个空白标签（Chrome 行为）
            self._new_tab()
        self._update_tab_buttons()

    def _close_others(self, keep_idx: int):
        for i in range(len(self._views) - 1, -1, -1):
            if i != keep_idx:
                self._close_tab(i)

    def _on_tab_moved(self, from_idx: int, to_idx: int):
        if from_idx == to_idx or not (0 <= from_idx < len(self._views)):
            return
        entry = self._views.pop(from_idx)
        self._views.insert(to_idx, entry)
        widget = entry.get("view") or entry.get("placeholder")
        if widget is not None:
            self._stack.setCurrentWidget(widget)
        self._sync_url_bar(to_idx)
        self._update_bookmark_state()
        self._update_tab_buttons()

    def _on_tab_changed(self, idx: int):
        if 0 <= idx < len(self._views):
            entry = self._views[idx]
            if entry["view"] is None:
                self._ensure_view(idx)
            else:
                self._stack.setCurrentWidget(entry["view"])
                # 激活标签恢复 Active，后台标签重新评估冻结
                self._apply_tab_limits()
                self._sync_url_bar(idx)
            self._update_bookmark_state()
            self._update_tab_buttons()

    def _index_for_view(self, view) -> int:
        for idx, entry in enumerate(self._views):
            if entry.get("view") is view:
                return idx
        return -1

    def _on_url_changed(self, view, url):
        idx = self._index_for_view(view)
        if idx < 0 or idx >= len(self._views):
            return
        self._views[idx]["url"] = url.toString()
        if idx == self._tab_bar.currentIndex():
            self._sync_url_bar(idx)
            self._update_bookmark_state()
            self._update_tab_buttons()

    def _on_title_changed(self, view, title: str):
        idx = self._index_for_view(view)
        if idx < 0 or idx >= len(self._views):
            return
        if not title:
            title = self._views[idx].get("url") or "新标签页"
        self._views[idx]["title"] = title
        if idx == self._tab_bar.currentIndex():
            self._update_bookmark_state()
        loading = self._views[idx].get("loading", False)
        display = f"● {title}" if loading else title
        self._tab_bar.setTabText(idx, display)
        self._tab_bar.setTabToolTip(idx, self._views[idx].get("url", ""))

    def _on_icon_changed(self, view, icon):
        idx = self._index_for_view(view)
        if idx < 0 or idx >= len(self._views):
            return
        try:
            if icon and not icon.isNull():
                self._tab_bar.setTabIcon(idx, icon)
        except Exception:
            pass

    def _sync_url_bar(self, idx: int):
        if 0 <= idx < len(self._views):
            self._url_bar.set_url(self._views[idx].get("url", ""))

    # ── 加载状态（80ms 合并）──

    def _on_load_started(self, view):
        idx = self._index_for_view(view)
        if idx < 0 or idx >= len(self._views):
            return
        self._views[idx]["loading"] = True
        self._set_status("加载中…")
        self._tab_bar.setTabText(idx, f"● {self._views[idx].get('title', '')}")
        if idx == self._tab_bar.currentIndex():
            self._btn_reload.setVisible(False)
            self._btn_stop.setVisible(True)
            self._url_bar.set_loading(True, 5)
            self._update_tab_buttons()

    def _on_load_progress(self, view, progress: int):
        idx = self._index_for_view(view)
        if idx == self._tab_bar.currentIndex():
            self._url_bar.set_loading(True, progress)

    def _on_load_finished(self, view, ok: bool):
        idx = self._index_for_view(view)
        if idx < 0 or idx >= len(self._views):
            return
        self._views[idx]["loading"] = False
        if idx == self._tab_bar.currentIndex():
            self._btn_reload.setVisible(True)
            self._btn_stop.setVisible(False)
            self._url_bar.set_loading(False, 100 if ok else 0)
            self._update_tab_buttons()
        self._set_status("完成" if ok else "加载失败")
        # 刷新标题（去掉 ● 前缀）
        title = self._views[idx].get("title", "")
        self._tab_bar.setTabText(idx, title)
        if ok:
            self._maybe_check_h264(view)

    # ── 视频解码能力探测（H.264 缺失提示）──

    def _maybe_check_h264(self, view):
        """页面加载成功后探测内核 H.264 解码能力（仅首次探测）

        内核能力是全局属性，与具体页面无关 → 探测一次并缓存结果，
        避免每个页面反复 runJavaScript 的开销与状态栏刷屏。
        探测失败按"支持"处理（不打扰用户，仅失去提示机会）。
        """
        global _H264_SUPPORTED
        if _H264_SUPPORTED is not None:
            return
        try:
            page = view.page()
            page.runJavaScript(
                "document.createElement('video').canPlayType('video/mp4; codecs=\"avc1.42E01E\"')",
                self._on_h264_probe,
            )
        except RuntimeError:
            _H264_SUPPORTED = True  # view 已销毁，按支持处理避免反复探测

    def _on_h264_probe(self, result):
        """canPlayType 探测回调：空串 = 无 H.264 解码器 → 状态栏提示外部浏览器"""
        global _H264_SUPPORTED
        _H264_SUPPORTED = bool(result and result != "")
        if not _H264_SUPPORTED:
            try:
                self._set_status(_NO_H264_HINT)
            except RuntimeError:
                pass  # 窗口已销毁

    # ── 导航 ──

    def _navigate_to_url(self, url: str):
        """地址栏导航入口"""
        idx = self._tab_bar.currentIndex()
        if idx < 0:
            return
        view = self._ensure_view(idx)
        view.setUrl(_to_qurl(url))
        view.setFocus()

    def _go_back(self):
        view = self._current_view()
        if view:
            view.back()
            view.setFocus()

    def _go_forward(self):
        view = self._current_view()
        if view:
            view.forward()
            view.setFocus()

    def _reload(self):
        view = self._current_view()
        if view:
            view.reload()

    def _stop(self):
        view = self._current_view()
        if view:
            view.stop()

    def _current_view(self):
        idx = self._tab_bar.currentIndex()
        if 0 <= idx < len(self._views):
            return self._views[idx].get("view")
        return None

    def _update_tab_buttons(self):
        view = self._current_view()
        can_back, can_forward = False, False
        if view is not None:
            try:
                can_back = view.history().canGoBack()
                can_forward = view.history().canGoForward()
            except Exception:
                # 历史状态未知时允许点击，由 back()/forward() 自行处理
                can_back = can_forward = True
        self._btn_back.setEnabled(can_back)
        self._btn_forward.setEnabled(can_forward)

    # ── 性能：后台标签冻结 ──

    def _apply_tab_limits(self):
        """超过 MAX_ALIVE_TABS 时冻结非活跃标签（释放渲染内存）"""
        from PySide6.QtWebEngineWidgets import QWebEnginePage

        current = self._tab_bar.currentIndex()
        alive = 0
        for i, entry in enumerate(self._views):
            view = entry.get("view")
            if view is None:
                continue
            page = view.page()
            if i == current:
                try:
                    page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
                except Exception:
                    pass
                alive += 1
            elif alive < MAX_ALIVE_TABS:
                alive += 1
                # 后台标签保持 Active（在配额内）
                try:
                    if page.lifecycleState() != QWebEnginePage.LifecycleState.Active:
                        page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
                except Exception:
                    pass
            else:
                # 超出配额 → 冻结
                try:
                    page.setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
                except Exception:
                    pass

    # ── 主题 ──

    def _apply_theme(self):
        """拉取最新主题派生色并应用到全部控件（无 ctx 时跟随 FluentWidgets 主题）。"""
        c = theme_colors(self)
        self._c = c
        self._is_dark = c["is_dark"]

        font = QFont(c["ff"])
        font.setPixelSize(c["fs"])
        self.setFont(font)

        self._stack.setStyleSheet(
            f"QStackedWidget {{ background: {c['surface']}; border: none; }}"
        )
        self._status_lb.setStyleSheet(
            f"{font_css(c['ff'], max(10, c['fs'] - 1))} color: {c['secondary']}; background: transparent;"
        )
        # 拦截摘要 label 同步主题色 + 刷新文字（配置可能已变更）
        if hasattr(self, "_intercept_status_lb"):
            from .redirect_config import config_summary

            self._intercept_status_lb.setStyleSheet(
                f"{font_css(c['ff'], max(10, c['fs'] - 2))}"
                f" color: {c['muted']}; background: transparent; padding: 0 4px;"
            )
            self._intercept_status_lb.setText(config_summary())
        self._incognito_badge.setStyleSheet(
            f"{font_css(c['ff'], max(10, c['fs'] - 2))} color: {c['tag_purple']}; padding: 0 8px;"
        )

        button_style = _tool_btn_style(c)
        for button in (
            self._btn_back,
            self._btn_forward,
            self._btn_reload,
            self._btn_stop,
            self._btn_bookmark,
            self._btn_new_tab,
            self._btn_menu,
            self._btn_external,
            self._btn_close,
        ):
            button.setStyleSheet(button_style)

        # 外部打开按钮图标随主题切换（深色主题用浅色线条版本）
        self._btn_external.setIcon(QIcon(_icon_path("external_open", c["is_dark"])))

        self._menu_panel.setStyleSheet(
            f"QFrame {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; }}"
            f"QLabel {{ color: {c['text']}; {font_css(c['ff'], max(10, c['fs'] - 1))} padding: 4px 8px; }}"
            f"QToolButton {{ border: none; color: {c['text']}; {font_css(c['ff'], max(10, c['fs'] - 1))}"
            " padding: 4px 10px; border-radius: 6px; text-align: left; }"
            f"QToolButton:hover {{ background: {c['hover']}; }}"
        )
        self._url_bar.apply_theme(c)
        self._tab_bar.apply_theme(c)
        self._bookmark_bar.apply_theme()
        for entry in self._views:
            placeholder = entry.get("placeholder")
            if placeholder is not None:
                placeholder.setStyleSheet(f"background: {c['surface']};")
            view = entry.get("view")
            if view is not None:
                # 已加载页面背景色跟随主题（防白闪）
                try:
                    view.page().setBackgroundColor(QColor(c["surface"]))
                except Exception:
                    pass

    # ── 菜单面板（收藏/历史/下载 管理）──

    def _build_menu_panel(self, parent) -> QWidget:
        panel = QFrame(parent)
        panel.setFixedWidth(150)
        ply = QVBoxLayout(panel)
        ply.setContentsMargins(6, 6, 6, 6)
        ply.setSpacing(2)

        for icon, text, slot in (
            (FluentIcon.BOOK_SHELF, "收藏夹", self._toggle_bookmarks),
            (FluentIcon.HISTORY, "历史记录", self._toggle_history),
            (FluentIcon.DOWNLOAD, "下载管理", self._toggle_downloads),
        ):
            btn = QToolButton(panel)
            btn.setIcon(icon.qicon())
            btn.setIconSize(QSize(16, 16))
            btn.setText(text)
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            btn.clicked.connect(slot)
            ply.addWidget(btn)

        # 拦截设置（分离线）
        sep = QFrame(panel)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(128,128,128,0.15);")
        ply.addWidget(sep)

        btn = QToolButton(panel)
        btn.setIcon(FluentIcon.SETTING.qicon())
        btn.setIconSize(QSize(16, 16))
        btn.setText("拦截设置")
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.clicked.connect(self._open_redirect_settings)
        ply.addWidget(btn)
        return panel

    def _position_popup(self, panel):
        panel.adjustSize()
        anchor = self._btn_menu.mapTo(
            self, QPoint(self._btn_menu.width(), self._btn_menu.height())
        )
        x = max(8, anchor.x() - panel.width())
        panel.move(x, anchor.y() + 4)
        panel.raise_()

    def _position_menu(self):
        self._position_popup(self._menu_panel)

    # 卡片内嵌悬浮面板（历史/收藏/下载统一弹窗格式）的属性名清单：
    # 菜单打开时互斥隐藏、resize 时统一重定位
    _POPUP_PANEL_ATTRS = ("_history_panel", "_bookmarks_panel", "_downloads_panel")

    def _hide_popup_panels(self):
        """隐藏全部卡片内嵌悬浮面板（互斥显示，同一时刻只留一个）"""
        for attr in self._POPUP_PANEL_ATTRS:
            panel = getattr(self, attr, None)
            if panel is not None:
                panel.hide()

    def _reposition_popup_panels(self):
        """resize 时重定位所有可见悬浮面板（越界会被卡片裁切）"""
        for attr in self._POPUP_PANEL_ATTRS:
            panel = getattr(self, attr, None)
            if panel is not None and panel.isVisible():
                self._position_popup(panel)

    def _toggle_menu(self):
        visible = not self._menu_panel.isVisible()
        if visible:
            self._hide_popup_panels()
            self._position_menu()
        self._menu_panel.setVisible(visible)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_menu_panel") and self._menu_panel.isVisible():
            self._position_menu()
        self._reposition_popup_panels()

    def _toggle_bookmarks(self):
        from .bookmarks import show_bookmarks_panel

        self._menu_panel.setVisible(False)
        self._hide_popup_panels()  # 互斥：同一时刻只显示一个悬浮面板
        show_bookmarks_panel(self)

    def _toggle_history(self):
        from .history import show_history_panel

        self._menu_panel.setVisible(False)
        self._hide_popup_panels()
        show_history_panel(self)

    def _toggle_downloads(self):
        from .downloads import show_downloads_panel

        self._menu_panel.setVisible(False)
        self._hide_popup_panels()
        show_downloads_panel(self)

    def _open_redirect_settings(self):
        """打开拦截设置弹窗（菜单 → 拦截设置）"""
        from .redirect_settings import show_redirect_settings

        self._menu_panel.setVisible(False)
        show_redirect_settings(self, owner=self)

    def open_devtools(self):
        from .devtools import open_devtools_for

        open_devtools_for(self)

    def open_incognito(self):
        from .incognito import open_incognito_window

        open_incognito_window(self)

    # ── 数据接口 ──

    def _current_bookmark_url(self) -> str:
        view = self._current_view()
        return view.url().toString() if view is not None else ""

    def _update_bookmark_state(self):
        url = self._current_bookmark_url()
        valid = bool(url and not is_blank_page(url))
        saved = valid and any(item.get("url") == url for item in self._bookmarks_cache)
        self._btn_bookmark.setEnabled(valid)
        self._btn_bookmark.setText("★" if saved else "☆")
        self._btn_bookmark.setToolTip("取消收藏" if saved else "收藏当前网页")
        self._btn_external.setEnabled(valid)

    def _toggle_current_bookmark(self):
        url = self._current_bookmark_url()
        if not url or is_blank_page(url):
            return
        existing = next(
            (item for item in self._bookmarks_cache if item.get("url") == url), None
        )
        if existing is not None:
            if not remove_bookmark(url):
                self._set_status("取消收藏失败")
                return
        else:
            idx = self._tab_bar.currentIndex()
            title = (
                self._views[idx].get("title", "") if 0 <= idx < len(self._views) else ""
            )
            if not title or title == "新标签页":
                title = urlparse(url).hostname or url
            if not add_bookmark(url, title):
                self._set_status("收藏失败")
                return
        self._refresh_bookmarks()
        self._async_refresh_suggestions()

    def _refresh_bookmarks(self):
        self._loader.load("bookmarks", self._on_bookmarks_ready, limit=500)

    def _on_bookmarks_ready(self, items):
        self._bookmarks_cache = list(items)
        self._bookmark_bar.set_items(self._bookmarks_cache)
        self._update_bookmark_state()

    def _open_in_system_browser(self):
        """在系统默认浏览器中打开当前标签页 URL（绕过内置浏览器重定向）"""
        url = self._current_bookmark_url()
        if not url or is_blank_page(url):
            return
        if open_in_system_browser(url):
            self._set_status("已在系统默认浏览器打开")
        else:
            self._set_status("打开系统浏览器失败")

    def _close_card(self):
        self._menu_panel.hide()
        self._bookmark_bar._overflow.hide()
        self.hide()
        self.closed.emit()

    def _on_page_loaded(self, view, ok: bool):
        """页面加载完成后记录历史（url + 标题）"""
        idx = self._index_for_view(view)
        if not ok:
            return
        if idx < 0 or idx >= len(self._views):
            return
        view = self._views[idx].get("view")
        if view is None:
            return
        url_str = view.url().toString()
        if url_str and not is_blank_page(url_str):
            title = self._views[idx].get("title", "")
            record_history(url_str, title)
            # H2 修复：异步刷新地址栏补全（主线程不阻塞）
            self._async_refresh_suggestions()

    def _refresh_download_panel(self):
        """刷新下载面板（下载完成时调用）"""
        panel = getattr(self, "_downloads_panel", None)
        if panel is not None and panel.isVisible():
            panel._reload()

    def _get_suggestions(self):
        """url_bar.completer_source 同步兜底 — 返回内存缓存

        H2 修复：地址栏输入时频繁触发，不会阻塞主线程。
        数据由 _async_refresh_suggestions() 在后台加载完成后回填。
        """
        return list(self._suggestions_cache)

    def _async_refresh_suggestions(self):
        """H2 修复：后台异步加载地址栏补全数据"""
        self._loader.load(
            "suggestions",
            self._on_suggestions_ready,
            limit=50,
        )

    def _on_suggestions_ready(self, items: List[Tuple[str, str]]):
        """suggestions 异步回调 — 更新内存缓存 + 重建 QCompleter"""
        self._suggestions_cache = list(items)
        self._url_bar.update_completer()

    def _refresh_panels(self):
        """show_card 时异步刷新补全与收藏数据。"""
        self._async_refresh_suggestions()
        self._refresh_bookmarks()

    def _set_status(self, text: str):
        self._status_lb.setText(text)

    # ── 快捷键 ──

    def _setup_shortcuts(self):
        from .shortcuts import install_shortcuts

        install_shortcuts(self)

    # ── 关闭 ──

    def deleteLater(self):
        global _CURRENT_CARD
        if _CURRENT_CARD is self:
            _CURRENT_CARD = None
        # 主题刷新目标注销（weakref 注册，显式移除避免脏引用）
        try:
            from app.utils.theme_manager import theme_manager

            theme_manager.unregister_refresh_target(self)
        except Exception:
            pass
        # N12 修复：释放持久 Profile 单例引用（避免热重载/卸载时 Qt 端 C++ 对象悬空）
        try:
            reset_profiles()
        except Exception:
            pass
        # 关闭所有隐身窗口，释放它们持有的 OTR profile
        try:
            from .incognito import close_all_incognito_windows

            close_all_incognito_windows()
        except Exception:
            pass
        self._loader.cleanup()
        for entry in self._views:
            view = entry.get("view")
            if view is not None:
                try:
                    view.deleteLater()
                except RuntimeError:
                    pass
        super().deleteLater()

    # ══════════════════════════════════════════════════════
    # function 命令 handlers（类级静态方法，供 FunctionCommandHandlers）
    # ══════════════════════════════════════════════════════

    @staticmethod
    def handle_browser_command(args: str):
        """/browser [url] — 打开/聚焦浏览器，可选导航到 URL"""
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        registry = UIPluginRegistry.get_instance()
        registry.toggle_floating_card("browser")
        card = _get_current_card()
        if card is None:
            return
        args = (args or "").strip()
        if args:
            url = normalize_url(args)
            if url:
                card._navigate_to_url(url)
            else:
                card._navigate_to_url(_search_url(args))

    @staticmethod
    def handle_browser_new(args: str):
        """/browser-new — 新建标签页"""
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        UIPluginRegistry.get_instance().toggle_floating_card("browser")
        card = _get_current_card()
        if card is not None:
            card._new_tab()

    @staticmethod
    def handle_browser_devtools(args: str):
        """/browser-devtools — 打开 DevTools"""
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        UIPluginRegistry.get_instance().toggle_floating_card("browser")
        card = _get_current_card()
        if card is not None:
            card.open_devtools()

    @staticmethod
    def handle_browser_incognito(args: str):
        """/browser-incognito — 打开隐身窗口"""
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        UIPluginRegistry.get_instance().toggle_floating_card("browser")
        card = _get_current_card()
        if card is not None:
            card.open_incognito()


# ══════════════════════════════════════════════════════════
# 工具函数（延迟导入避免循环依赖）
# ══════════════════════════════════════════════════════════

# N2 修复：_create_page 已抽到 ui/_page_factory.py，统一供 browser_window + incognito 使用
# N5 修复：_incognito 模块级标志已删除（主卡片永远非隐身，隐身走独立 IncognitoWindow）


def _to_qurl(url: str):
    from PySide6.QtCore import QUrl

    return QUrl(url)


def open_in_system_browser(url: str) -> bool:
    """在系统默认浏览器中打开 URL

    ⚠️ 不能直接用 webbrowser.open / QDesktopServices.openUrl / os.startfile：
    它们已被 external_open 重定向到内置浏览器，会形成回环
    （v1.4.0 修复：os.startfile 也被 patch，「外部打开」按钮曾再次被拦回）。
    统一走 external_open.open_url_external —— 通过代理属性取回原始入口。
    """
    if not url:
        return False
    try:
        from .external_open import open_url_external

        return open_url_external(url)
    except Exception:
        return False


def _search_url(query: str) -> str:
    from urllib.parse import quote

    return f"https://www.bing.com/search?q={quote(query)}"


def _start_page_html(c: dict) -> str:
    """起始页 HTML：双色标题 + hover 提示行 + kbd 键帽 + 双背景防白闪。

    ff 做单引号转义防御（主题字体名可能含 ' ）。
    """
    ff = c["ff"].replace("'", "\\'")
    fs = c["fs"]
    accent = c["accent"]
    surface = c["surface"]
    text = c["text"]
    secondary = c["secondary"]
    hover = c["hover"]
    border = c["border"]
    raised = c["raised"]
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
html {{ background:{surface}; }}
body {{ background:{surface}; color:{text};
       font-family:'{ff}','Microsoft YaHei','Segoe UI',sans-serif;
       display:flex; align-items:center; justify-content:center;
       height:100vh; margin:0; }}
.card {{ text-align:center; }}
h1 {{ font-size:{fs + 10}px; font-weight:300; color:{text}; margin:0 0 16px 0; }}
h1 .brand {{ font-weight:600; color:{accent}; }}
p.hint {{ color:{secondary}; font-size:{fs}px; padding:8px 14px;
         border:1px solid {border}; background:{hover}; border-radius:8px; }}
kbd {{ background:{raised}; border:1px solid {border}; color:{text};
       border-radius:4px; padding:1px 6px;
       font-family:'{ff}','Microsoft YaHei',sans-serif; font-size:{max(10, fs - 2)}px; }}
</style></head><body>
<div class="card">
  <h1><span class="brand">DriFox</span> 浏览器</h1>
  <p class="hint"><kbd>Ctrl</kbd>+<kbd>L</kbd> 聚焦地址栏 · <kbd>Ctrl</kbd>+<kbd>T</kbd> 新建标签</p>
</div>
</body></html>
"""
