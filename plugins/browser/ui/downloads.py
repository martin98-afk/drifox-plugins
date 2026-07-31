# -*- coding: utf-8 -*-
"""下载管理 — downloadRequested 托管 + 进度面板

- attach_download_handler: 挂到每个 WebEngineView 的 page().profile()
  （QWebEngineProfile.downloadRequested 是 profile 级信号，只需挂一次）
- M1 修复：热重载兼容 — reset_handled_profiles() 显式 disconnect + 清空 set，
  避免 Qt 端信号连接残留（lambda 改用 functools.partial 以便精确 disconnect）
- 下载面板：显示进度条、状态、打开文件夹
"""

import os
import webbrowser
from functools import partial
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .data import AsyncDataLoader, update_download_state, upsert_download
from .theme import dialog_style, scrollbar_style, theme_colors

# M1 修复：用 dict 存 profile → partial 引用，便于热重载时精确 disconnect
_HANDLED_PROFILES: dict = {}


def attach_download_handler(view, owner) -> None:
    """为 view 的 profile 挂载 downloadRequested 托管（幂等）

    M1 修复：使用 partial 而非 lambda，便于 reset_handled_profiles() 精确 disconnect。
    """
    try:
        profile = view.page().profile()
        if id(profile) in _HANDLED_PROFILES:
            return
        slot = partial(_on_download_requested, owner)
        profile.downloadRequested.connect(slot)
        _HANDLED_PROFILES[id(profile)] = (profile, slot)
    except Exception:
        pass


def reset_handled_profiles() -> None:
    """M1 修复：热重载时清理所有挂载的 downloadRequested 信号

    遍历已挂载的 profile，对每个槽函数调用 disconnect，
    确保 Python 重新加载后不会因 Qt 端残留连接而重复触发或崩溃。
    """
    for pid, (profile, slot) in list(_HANDLED_PROFILES.items()):
        try:
            profile.downloadRequested.disconnect(slot)
        except (TypeError, RuntimeError):
            # 信号未连接或 Qt 对象已销毁，忽略
            pass
    _HANDLED_PROFILES.clear()


def _on_download_requested(owner, item) -> None:
    """接管下载：记录到 SQLite + 连接进度信号"""
    try:
        url = item.url().toString()
        # 默认路径：profile 下载目录 + 文件名
        path = item.downloadDirectory() or str(Path.home() / "Downloads")
        filename = item.downloadFileName() or url.split("/")[-1] or "download"
        target = os.path.join(path, filename)
        item.setDownloadDirectory(os.path.dirname(target))
        item.setDownloadFileName(os.path.basename(target))

        download_id = upsert_download(url, target, "downloading", 0, item.totalBytes())
        item.accept()

        # 进度信号
        def _on_download_progress(received, total):
            update_download_state(download_id, "downloading", received, total)
            owner._set_status(f"⬇ 下载中: {filename} ({received // 1024}KB)")

        def _on_download_finished():
            update_download_state(download_id, "finished", item.receivedBytes(), item.totalBytes())
            owner._set_status(f"✅ 下载完成: {filename}")
            owner._refresh_download_panel()

        def _on_download_state_changed(state):
            from PyQt5.QtWebEngineCore import QWebEngineDownloadItem

            if state == QWebEngineDownloadItem.DownloadCancelled:
                update_download_state(download_id, "cancelled", item.receivedBytes(), item.totalBytes())
                owner._set_status(f"⛔ 下载取消: {filename}")
            elif state == QWebEngineDownloadItem.DownloadInterrupted:
                update_download_state(download_id, "interrupted", item.receivedBytes(), item.totalBytes())
                owner._set_status(f"⚠️ 下载中断: {filename}")

        item.downloadProgress.connect(_on_download_progress)
        item.finished.connect(_on_download_finished)
        item.stateChanged.connect(_on_download_state_changed)
    except Exception:
        pass


class DownloadsPanel(QDialog):
    """下载管理面板"""

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner
        self.setWindowTitle("下载管理")
        self.setMinimumSize(520, 400)
        self.setWindowFlag(Qt.Window)
        self._loader = AsyncDataLoader(self)
        self._items_cache: list = []
        self._setup_ui()
        self._reload()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("⬇ 下载管理")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)

        self._btn_refresh = QPushButton("刷新")
        self._btn_close = QPushButton("关闭")
        self._btn_refresh.clicked.connect(self._reload)
        self._btn_close.clicked.connect(self.close)
        header.addWidget(self._btn_refresh)
        header.addWidget(self._btn_close)
        root.addLayout(header)

        self._list = QListWidget(self)
        root.addWidget(self._list, 1)

        self.setStyleSheet(dialog_style(self._owner) + scrollbar_style(self._owner))

    def _reload(self):
        """H2 修复：异步加载下载列表（主线程不阻塞）"""
        self._list.clear()
        placeholder = QListWidgetItem("加载中…")
        self._list.addItem(placeholder)
        self._loader.load(
            "downloads",
            self._on_downloads_loaded,
            limit=100,
        )

    def _on_downloads_loaded(self, items):
        """后台线程回调 → 缓存 + 渲染"""
        self._items_cache = list(items)
        self._render_list()

    def _render_list(self):
        """同步渲染缓存"""
        self._list.clear()
        if not self._items_cache:
            placeholder = QListWidgetItem("暂无下载记录")
            self._list.addItem(placeholder)
            return
        for d in self._items_cache:
            item = QListWidgetItem()
            widget = _DownloadItemWidget(d, self._owner)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, d.get("path", ""))
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)


def open_folder(path: str) -> bool:
    """N14 修复：跨平台打开文件夹

    Windows 用 os.startfile，其他平台用 webbrowser.open fallback。
    Returns True 成功打开。
    """
    if not path:
        return False
    try:
        folder = os.path.dirname(path)
        if os.path.exists(folder):
            if hasattr(os, "startfile"):
                os.startfile(folder)  # type: ignore[attr-defined]  # noqa: S606
            else:
                # Linux/macOS fallback：调用系统默认应用打开文件夹
                webbrowser.open(f"file:///{folder.replace(os.sep, '/')}")
            return True
    except Exception:
        pass
    return False


class _DownloadItemWidget(QWidget):
    """单个下载项：文件名 + 状态 + 进度条"""

    def __init__(self, data: dict, owner=None, parent=None):
        super().__init__(parent)
        colors = theme_colors(owner)
        self._path = data.get("path", "")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        name = os.path.basename(self._path) or data.get("url", "下载")
        state_map = {
            "downloading": "下载中",
            "finished": "✅ 完成",
            "cancelled": "⛔ 已取消",
            "interrupted": "⚠️ 中断",
        }
        state = state_map.get(data.get("state", ""), data.get("state", ""))

        row = QHBoxLayout()
        label = QLabel(f"{name}  [{state}]")
        label.setStyleSheet(f"color: {colors['text']}; font-size: 13px;")
        row.addWidget(label, 1)

        received = data.get("bytes_received", 0)
        total = data.get("bytes_total", 0)
        pct = int(received / total * 100) if total > 0 else 0
        size_txt = f"{received // 1024}KB / {total // 1024}KB" if total > 0 else f"{received // 1024}KB"

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(pct)
        self._progress.setTextVisible(True)
        self._progress.setFormat(f"{size_txt}")
        self._progress.setFixedHeight(16)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {colors['raised']}; border: none; border-radius: 4px;"
            f" color: {colors['secondary']}; font-size: 11px; text-align: center; }}"
            "QProgressBar::chunk { background: #2f9df0; border-radius: 4px; }"
        )
        row.addWidget(self._progress, 2)

        if data.get("state") == "finished" and self._path:
            btn = QPushButton("📂")
            btn.setToolTip("打开所在文件夹")
            btn.setFixedSize(28, 24)
            btn.clicked.connect(lambda: open_folder(self._path))
            row.addWidget(btn)

        layout.addLayout(row)


def show_downloads_panel(owner):
    """从浏览器卡片打开下载面板（单例复用）"""
    if not hasattr(owner, "_downloads_panel") or owner._downloads_panel is None:
        owner._downloads_panel = DownloadsPanel(owner)
    owner._downloads_panel.setStyleSheet(dialog_style(owner) + scrollbar_style(owner))
    owner._downloads_panel._reload()
    owner._downloads_panel.show()
    owner._downloads_panel.raise_()