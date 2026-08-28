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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import FluentIcon

from app.utils.design_tokens import Colors

from .data import AsyncDataLoader, clear_downloads, update_download_state, upsert_download
from .panel_base import _PanelMixin, apply_panel_theme, build_footer, build_header, show_singleton_panel
from .theme import font_css, theme_colors

# 状态色（design_tokens 常量，仅状态文字用，不作主题主色）
_STATE_COLORS = {
    "finished": Colors.SUCCESS,
    "cancelled": Colors.WARNING,
    "interrupted": Colors.ERROR,
}

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
            owner._set_status(f"下载中: {filename} ({received // 1024}KB)")

        def _on_download_finished():
            update_download_state(
                download_id, "finished", item.receivedBytes(), item.totalBytes()
            )
            owner._set_status(f"下载完成: {filename}")
            owner._refresh_download_panel()

        def _on_download_state_changed(state):
            from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

            if state == QWebEngineDownloadRequest.DownloadCancelled:
                update_download_state(
                    download_id, "cancelled", item.receivedBytes(), item.totalBytes()
                )
                owner._set_status(f"下载取消: {filename}")
            elif state == QWebEngineDownloadRequest.DownloadInterrupted:
                update_download_state(
                    download_id, "interrupted", item.receivedBytes(), item.totalBytes()
                )
                owner._set_status(f"下载中断: {filename}")

        item.downloadProgress.connect(_on_download_progress)
        item.finished.connect(_on_download_finished)
        item.stateChanged.connect(_on_download_state_changed)
    except Exception:
        pass


class DownloadsPanel(QFrame, _PanelMixin):
    """下载管理面板（卡片内嵌悬浮 QFrame，与历史/收藏弹窗同格式）

    H2 修复：异步加载，统一基类 _PanelMixin。
    弹窗格式统一：原为 QDialog 独立窗口，现与历史面板一致 —
    浏览器卡片内悬浮、菜单按钮下方定位（owner._position_popup）。
    """

    def __init__(self, owner, parent=None):
        super().__init__(parent or owner)
        self._owner = owner
        self.setObjectName("downloadsPanel")
        self.setFixedSize(460, 320)
        self._loader = AsyncDataLoader(self)
        self._items_cache: list = []
        self._setup_ui()
        self._reload()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        def _header_actions(header: QHBoxLayout, _colors):
            self._btn_refresh = QPushButton("刷新", self)
            self._btn_refresh.clicked.connect(self._reload)
            header.addWidget(self._btn_refresh)

        root.addLayout(
            build_header(
                self, self._owner, "下载管理",
                icon=FluentIcon.DOWNLOAD, actions=_header_actions,
            )
        )

        self._list = QListWidget(self)
        root.addWidget(self._list, 1)

        def _footer_actions(footer: QHBoxLayout):
            self._btn_open_folder = QPushButton("打开下载目录", self)
            self._btn_clear = QPushButton("清空记录", self)
            self._btn_open_folder.clicked.connect(self._open_download_dir)
            self._btn_clear.clicked.connect(self._clear)
            footer.addWidget(self._btn_open_folder)
            footer.addWidget(self._btn_clear)

        root.addLayout(build_footer(self, actions=_footer_actions))

        apply_panel_theme(self, self._owner)

    # ── H2 修复：异步加载（统一基类 _reload_async） ──

    def _reload_async(self):
        """异步查询 downloads，缓存后渲染"""
        self._loader.load(
            "downloads",
            self._on_items_loaded,
            limit=100,
        )

    def _render_items(self):
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

    def _open_download_dir(self):
        """打开默认下载目录（不存在则提示）"""
        from .profile_manager import get_default_download_dir

        path = get_default_download_dir()
        if path and Path(path).exists():
            if open_folder(path):
                self._owner._set_status(f"已打开下载目录: {path}")
            else:
                self._owner._set_status(f"打开下载目录失败: {path}")
        else:
            self._owner._set_status("下载目录不存在")

    def _clear(self):
        from PySide6.QtWidgets import QMessageBox

        if (
            QMessageBox.question(self, "清空下载", "确定要清空全部下载记录吗？")
            == QMessageBox.Yes
        ):
            n = clear_downloads()
            self._reload()
            self._owner._set_status(f"已清空 {n} 条下载记录")

    def showEvent(self, event):
        super().showEvent(event)
        apply_panel_theme(self, self._owner)


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
        c = theme_colors(owner)
        self._path = data.get("path", "")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        name = os.path.basename(self._path) or data.get("url", "下载")
        state_map = {
            "downloading": "下载中",
            "finished": "完成",
            "cancelled": "已取消",
            "interrupted": "中断",
        }
        state = state_map.get(data.get("state", ""), data.get("state", ""))

        row = QHBoxLayout()
        label = QLabel(name)
        label.setStyleSheet(f"{font_css(c['ff'], c['fs'])} color: {c['text']};")
        row.addWidget(label, 1)

        state_label = QLabel(f"[{state}]")
        state_color = _STATE_COLORS.get(data.get("state", ""))
        state_label.setStyleSheet(
            f"{font_css(c['ff'], c['fs'])} color: {state_color or c['secondary']};"
        )
        row.addWidget(state_label)

        received = data.get("bytes_received", 0)
        total = data.get("bytes_total", 0)
        pct = int(received / total * 100) if total > 0 else 0
        size_txt = (
            f"{received // 1024}KB / {total // 1024}KB"
            if total > 0
            else f"{received // 1024}KB"
        )

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(pct)
        self._progress.setTextVisible(True)
        self._progress.setFormat(f"{size_txt}")
        self._progress.setFixedHeight(16)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {c['raised']}; border: none; border-radius: 4px;"
            f" {font_css(c['ff'], c['fs'] - 2)} color: {c['secondary']}; text-align: center; }}"
            f"QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}"
        )
        row.addWidget(self._progress, 2)

        if data.get("state") == "finished" and self._path:
            btn = QPushButton()
            btn.setIcon(FluentIcon.FOLDER.qicon())
            btn.setToolTip("打开所在文件夹")
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; border-radius: 6px; }}"
                f"QPushButton:hover {{ background: {c['hover']}; }}"
            )
            btn.clicked.connect(lambda: open_folder(self._path))
            row.addWidget(btn)

        layout.addLayout(row)


def show_downloads_panel(owner):
    """从浏览器卡片打开下载面板（单例复用 + 主题刷新 + 卡片内定位）

    与历史/收藏面板同格式：position=True → owner._position_popup 在
    菜单按钮下方定位，卡片内悬浮显示。
    """
    show_singleton_panel(
        owner, "_downloads_panel",
        factory=lambda o: DownloadsPanel(o, o),
        position=True,
    )
