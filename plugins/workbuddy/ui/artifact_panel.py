# -*- coding: utf-8 -*-
"""workbuddy 产物面板 — 轻量级 artifact 卡片视图

支持 Markdown / HTML / 文本 / 二进制 meta 四种渲染模式：
- Markdown：QTextBrowser + markdown 库（无依赖时降级纯文本）
- HTML：QWebEngineView 内嵌预览
- 文本：QTextBrowser 等宽字体
- 其他：仅显示元信息 + "用系统应用打开"按钮

数据来源：通过 _state 模块读取 wb_present 写入的记录（按 workdir 索引）
"""
import os
import sys
from pathlib import Path

# 注入插件根到 sys.path 以便跨模块导入 _state
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from PyQt5.QtCore import QUrl, Qt  # noqa: E402
from PyQt5.QtGui import QDesktopServices  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon  # noqa: E402

try:
    import markdown as _md
    _MARKDOWN_OK = True
except Exception:
    _MARKDOWN_OK = False

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    _WEB_ENGINE_OK = True
except Exception:
    _WEB_ENGINE_OK = False

import _state  # noqa: E402

_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_TYPE_ICON = {
    "text": FluentIcon.DOCUMENT,
    "image": FluentIcon.PHOTO,
    "pdf": FluentIcon.DOCUMENT,
    "ppt": FluentIcon.PROJECTOR,
    "sheet": FluentIcon.ZIP_FOLDER,
    "doc": FluentIcon.DOCUMENT,
    "file": FluentIcon.FOLDER,
}

# 模块级当前卡片引用（供 /artifacts 命令 handler 访问）
_CURRENT_CARD: "ArtifactPanelCard | None" = None


def _get_workdir(owner) -> str:
    """从 owner 上下文提取 workdir（兼容多种 owner 类型）"""
    for attr in ("workdir", "project_root"):
        v = getattr(owner, attr, None)
        if v:
            return str(v)
    main = getattr(owner, "main_window", None) or getattr(owner, "window", None)
    if main is not None:
        for attr in ("workdir", "project_root"):
            v = getattr(main, attr, None)
            if v:
                return str(v)
    return ""


class ArtifactPanelCard(QFrame):
    """workbuddy 浮动卡片：左侧 artifact 列表，右侧 viewer 切换。"""

    # 类级单例（最近实例化的卡片，供 state listener 与 /artifacts 命令共享）
    _instance: "ArtifactPanelCard | None" = None

    def __init__(self, owner=None, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._workdir = _get_workdir(owner)
        self._build_ui()
        self.refresh()
        # 设置类级引用，供 listener 找到当前实例
        ArtifactPanelCard._instance = self

    # ── UI 构建 ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # 头部
        header = QHBoxLayout()
        title = QLabel("产物", self)
        title.setStyleSheet("font-weight:600; font-size:13px;")
        header.addWidget(title)
        header.addStretch(1)
        self._refresh_btn = QPushButton("刷新", self)
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        self._clear_btn = QPushButton("清空", self)
        self._clear_btn.clicked.connect(self._on_clear)
        header.addWidget(self._clear_btn)
        root.addLayout(header)

        # 中部：左列表 + 右 viewer
        body = QHBoxLayout()
        body.setSpacing(8)
        self._list = QListWidget(self)
        self._list.setMaximumWidth(260)
        self._list.currentRowChanged.connect(self._on_select)
        body.addWidget(self._list)

        self._stack = QStackedWidget(self)
        self._md_viewer = QTextBrowser(self)
        self._md_viewer.setOpenExternalLinks(True)
        self._stack.addWidget(self._md_viewer)
        if _WEB_ENGINE_OK:
            self._web_viewer = QWebEngineView(self)
            self._stack.addWidget(self._web_viewer)
        else:
            self._web_viewer = None
            fallback = QLabel("HTML 预览不可用（缺 QtWebEngine）", self)
            fallback.setAlignment(Qt.AlignCenter)
            self._stack.addWidget(fallback)
        self._meta_viewer = QTextBrowser(self)
        self._stack.addWidget(self._meta_viewer)
        body.addWidget(self._stack, 1)
        root.addLayout(body, 1)

        # 底部摘要
        self._summary = QLabel("", self)
        self._summary.setStyleSheet("color:#888; font-size:11px;")
        self._summary.setWordWrap(True)
        root.addWidget(self._summary)

        self._entries: list[dict] = []
        self._all_items: list[dict] = []

    # ── 数据加载 ─────────────────────────────────────────────

    def refresh(self):
        self._list.clear()
        self._entries = _state.get_all(self._workdir)
        all_items: list[dict] = []
        for entry in self._entries:
            all_items.extend(entry.get("items", []))
        self._all_items = all_items
        for it in all_items:
            w = QListWidgetItem(f"{_label_for_type(it.get('type', 'file'))}  {it.get('path', '')}")
            w.setData(Qt.UserRole, it)
            self._list.addItem(w)
        if not all_items:
            self._stack.setCurrentIndex(2)  # meta viewer 显示空
            self._md_viewer.clear()
            if self._web_viewer:
                self._web_viewer.setUrl(QUrl("about:blank"))
            self._meta_viewer.setPlainText("（暂无产物 — 在 DriFox 中调用 present_files 工具后会显示在此）")
        msg = _state.last_message(self._workdir)
        total = len(all_items)
        self._summary.setText(f"{total} 个产物 · {msg}" if msg else f"{total} 个产物")

    def _on_clear(self):
        _state.clear(self._workdir)
        self.refresh()

    def _on_select(self, row: int):
        if row < 0 or row >= len(self._all_items):
            return
        item = self._all_items[row]
        path_str = item.get("absolute") or item.get("path", "")
        kind = item.get("type", "file")
        full = Path(path_str)
        if not full.exists():
            self._stack.setCurrentIndex(2)
            self._meta_viewer.setPlainText(f"文件不存在：{path_str}")
            return
        # Markdown
        if kind == "text" and full.suffix.lower() in {".md", ".markdown"}:
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                self._stack.setCurrentIndex(2)
                self._meta_viewer.setPlainText(f"读取失败：{exc}")
                return
            if _MARKDOWN_OK:
                html = _md.markdown(text, extensions=["fenced_code", "tables"])
                self._md_viewer.setHtml(_wrap_html(html))
            else:
                self._md_viewer.setPlainText(text)
            self._stack.setCurrentIndex(0)
            return
        # HTML
        if kind in ("text", "file") and full.suffix.lower() in {".html", ".htm"}:
            if self._web_viewer:
                self._web_viewer.setUrl(QUrl.fromLocalFile(str(full)))
            self._stack.setCurrentIndex(1 if self._web_viewer else 2)
            return
        # 文本预览（≤2MB）
        if kind == "text":
            try:
                if full.stat().st_size > 2 * 1024 * 1024:
                    self._stack.setCurrentIndex(2)
                    self._meta_viewer.setPlainText(f"文本过大 (>2MB)，仅显示元信息")
                    return
                text = full.read_text(encoding="utf-8", errors="replace")
                self._md_viewer.setPlainText(text)
                self._stack.setCurrentIndex(0)
                return
            except OSError:
                pass
        # 兜底：元信息 + 打开按钮
        meta = (
            f"类型：{item.get('type')}\n"
            f"路径：{item.get('path')}\n"
            f"绝对路径：{item.get('absolute')}\n"
            f"大小：{item.get('size', 0):,} 字节\n"
            f"行数：{item.get('lines') if item.get('lines') is not None else '—'}\n\n"
            f"双击列表项或点击「在系统中打开」调起默认应用"
        )
        self._meta_viewer.setPlainText(meta)
        self._stack.setCurrentIndex(2)

    # ── /artifacts 命令 handler ──────────────────────────────

    @staticmethod
    def handle_command(args: str = "", owner=None):
        """FunctionCommandHandlers 调用入口：切换显示面板"""
        global _CURRENT_CARD
        card = _CURRENT_CARD
        if card is None:
            return False
        card.refresh()
        if hasattr(card, "show"):
            card.show()
        if hasattr(card, "raise_"):
            card.raise_()
        return True


def _label_for_type(kind: str) -> str:
    return {
        "text": "📝", "image": "🖼 ", "pdf": "📕",
        "ppt": "📊", "sheet": "📈", "doc": "📘",
    }.get(kind, "📄")


def _wrap_html(body: str) -> str:
    """给 markdown 渲染结果加最小化样式包装"""
    return (
        '<html><head><meta charset="utf-8">'
        '<style>body{font-family: -apple-system, "Segoe UI", sans-serif;'
        ' line-height:1.6; padding:8px;} '
        'pre{background:#f4f4f4; padding:8px; border-radius:4px; overflow:auto;} '
        'code{background:#f4f4f4; padding:2px 4px; border-radius:3px;} '
        'table{border-collapse:collapse;} th,td{border:1px solid #ccc; padding:4px 8px;}'
        '</style></head><body>' + body + "</body></html>"
    )


def cleanup() -> None:
    """卸载/热重载清理（占位）"""
    global _CURRENT_CARD
    _CURRENT_CARD = None