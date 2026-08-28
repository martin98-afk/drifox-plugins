# -*- coding: utf-8 -*-
"""快捷键 — Chrome 一致的浏览器内快捷键

作用域：绑定在浏览器卡片（BrowserWindowCard）上，context=WidgetWithChildrenShortcut，
只在浏览器获得焦点时生效，不会与主程序全局快捷键冲突。

全量映射（与 Chrome 一致）：
- Ctrl+L           聚焦地址栏并全选
- Ctrl+T           新建标签
- Ctrl+W           关闭当前标签
- Ctrl+Shift+T     恢复关闭的标签（保留接口）
- F5 / Ctrl+R      刷新
- Esc              停止加载 / 关闭菜单
- F12 / Ctrl+Shift+I  打开 DevTools
- Ctrl+Shift+N     新建隐身窗口
- Ctrl+H           打开历史记录
- Ctrl+D           收藏当前页
- Ctrl+Tab         切换到下一个标签
- Ctrl+Shift+Tab   切换到上一个标签
- Ctrl+1..8        跳转到指定标签
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut


def install_shortcuts(card) -> None:
    """在浏览器卡片上安装全量快捷键"""
    sc = QShortcut(QKeySequence("Ctrl+L"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(card._url_bar.select_all)

    sc = QShortcut(QKeySequence("Ctrl+T"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(lambda: card._new_tab())

    sc = QShortcut(QKeySequence("Ctrl+W"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(lambda: card._close_tab(card._tab_bar.currentIndex()))

    sc = QShortcut(QKeySequence("Ctrl+Shift+T"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(lambda: _restore_closed_tab(card))

    for key in ("F5", "Ctrl+R"):
        sc = QShortcut(QKeySequence(key), card)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(card._reload)

    sc = QShortcut(QKeySequence("Esc"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(lambda: card._stop() or card._menu_panel.setVisible(False))

    for key in ("F12", "Ctrl+Shift+I"):
        sc = QShortcut(QKeySequence(key), card)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(card.open_devtools)

    sc = QShortcut(QKeySequence("Ctrl+Shift+N"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(card.open_incognito)

    sc = QShortcut(QKeySequence("Ctrl+H"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(card._toggle_history)

    sc = QShortcut(QKeySequence("Ctrl+D"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(lambda: _bookmark_current(card))

    sc = QShortcut(QKeySequence("Ctrl+Tab"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(lambda: _cycle_tab(card, 1))

    sc = QShortcut(QKeySequence("Ctrl+Shift+Tab"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(lambda: _cycle_tab(card, -1))

    for num in range(1, 9):
        sc = QShortcut(QKeySequence(f"Ctrl+{num}"), card)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(lambda n=num - 1: _jump_tab(card, n))


# ── 辅助函数 ──


def _cycle_tab(card, delta: int):
    n = card._tab_bar.count()
    if n <= 1:
        return
    cur = card._tab_bar.currentIndex()
    card._tab_bar.setCurrentIndex((cur + delta) % n)


def _jump_tab(card, idx: int):
    if 0 <= idx < card._tab_bar.count():
        card._tab_bar.setCurrentIndex(idx)


def _bookmark_current(card):
    view = card._current_view()
    if view is None:
        return
    url = view.url().toString()
    if not url or url == "about:blank":
        return
    from .data import add_bookmark

    title = card._views[card._tab_bar.currentIndex()].get("title", "")
    add_bookmark(url, title)
    card._set_status(f"★ 已收藏: {title or url}")


def _restore_closed_tab(card):
    """恢复最近关闭的标签（M3 增强：维护关闭栈）"""
    if hasattr(card, "_closed_stack") and card._closed_stack:
        url = card._closed_stack.pop()
        card._new_tab(url)
    else:
        card._set_status("没有可恢复的标签")
