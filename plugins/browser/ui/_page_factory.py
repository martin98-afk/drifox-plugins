# -*- coding: utf-8 -*-
"""页面工厂 — 统一创建具有正常浏览器链接行为的 QWebEnginePage。"""


def create_page(view, profile, new_page_callback=None):
    """创建页面：左键在当前标签跳转，右键可显式在新标签打开。"""
    from PyQt5.QtCore import Qt, QUrl
    from PyQt5.QtWidgets import QApplication, QMenu
    from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineSettings

    class BrowserPage(QWebEnginePage):
        def createWindow(self, window_type):
            # target=_blank/window.open 默认复用当前页，符合左键当前标签跳转的交互。
            return self

    page = BrowserPage(profile, view)
    settings = page.settings()
    settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
    settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
    settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
    settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
    settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)

    def show_context_menu(pos):
        data = page.contextMenuData()
        link_url = QUrl(data.linkUrl())
        menu = QMenu(view)

        if link_url.isValid() and not link_url.isEmpty():
            menu.addAction("在当前标签打开", lambda: view.setUrl(link_url))
            if new_page_callback is not None:
                menu.addAction("在新标签打开", lambda: new_page_callback(link_url))
            menu.addAction(
                "复制链接地址",
                lambda: QApplication.clipboard().setText(link_url.toString()),
            )
            menu.addSeparator()

        back = menu.addAction("后退", view.back)
        back.setEnabled(view.history().canGoBack())
        forward = menu.addAction("前进", view.forward)
        forward.setEnabled(view.history().canGoForward())
        menu.addAction("刷新", view.reload)
        menu.addSeparator()
        menu.addAction("复制", lambda: page.triggerAction(QWebEnginePage.Copy))
        menu.addAction("全选", lambda: page.triggerAction(QWebEnginePage.SelectAll))
        menu.exec_(view.mapToGlobal(pos))

    view.setContextMenuPolicy(Qt.CustomContextMenu)
    view.customContextMenuRequested.connect(show_context_menu)
    return page
