# -*- coding: utf-8 -*-
"""DevTools 集成 — 为当前活动标签打开独立 DevTools 窗口

依赖任务 0：build.py 已保留 qtwebengine_devtools_resources.pak，
否则 DevTools 页面无法加载。

实现：QWebEnginePage.setDevToolsPage() + 独立 QMainWindow 承载 devtools view。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from loguru import logger

# 保持 DevTools 窗口引用（防止 GC）
_open_devtools = []


def open_devtools_for(owner) -> None:
    """为浏览器当前活动标签打开 DevTools 窗口"""
    try:
        view = owner._current_view()
        if view is None:
            return

        from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView

        page = view.page()

        # 已有 DevTools 页面且窗口还在 → 聚焦
        existing = page.devToolsPage()
        if existing is not None and _focus_existing_devtools():
            return

        # 创建承载 devtools 的独立窗口
        window = QMainWindow()
        window.setWindowTitle("DevTools — DriFox 浏览器")
        window.resize(900, 600)
        window.setAttribute(Qt.WA_DeleteOnClose)

        container = QWidget(window)
        window.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        dev_view = QWebEngineView()
        layout.addWidget(dev_view)

        # 关键：创建 devtools page 并关联到源 page + dev_view
        devtools_page = QWebEnginePage(page.profile(), dev_view)
        page.setDevToolsPage(devtools_page)
        dev_view.setPage(devtools_page)

        # 窗口关闭时解除关联
        def _on_close():
            try:
                if page.devToolsPage() is devtools_page:
                    page.setDevToolsPage(None)
            except Exception:
                pass
            if window in _open_devtools:
                _open_devtools.remove(window)

        window.destroyed.connect(_on_close)
        _open_devtools.append(window)
        window.show()
        window.raise_()

    except Exception as e:
        logger.error(f"[browser] 打开 DevTools 失败: {e}")
        owner._set_status(f"DevTools 打开失败: {e}")


def _focus_existing_devtools() -> bool:
    """聚焦已有 DevTools 窗口；返回是否聚焦成功"""
    for win in list(_open_devtools):
        try:
            if win.isVisible():
                win.raise_()
                win.activateWindow()
                return True
        except RuntimeError:
            _open_devtools.remove(win)
    return False
