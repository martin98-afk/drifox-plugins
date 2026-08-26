# -*- coding: utf-8 -*-
"""workbuddy 产物面板 — WorkBuddy 风格 Tab 视图

布局（还原 WorkBuddy Artifacts 体验）：
- 头部 tab 条：每个已呈现的产物一个 tab（可关闭、可拖动排序），新 present 自动追加并激活
- 下方整个区域为当前产物内容：
  - Markdown → QTextBrowser(HTML)
  - HTML     → QWebEngineView 内嵌预览（缺 QtWebEngine 时降级提示）
  - 文本     → QTextBrowser 等宽字体
  - 图片     → QLabel 缩放位图
  - 其他     → 元信息 + 「在系统中打开」（点击链接调起默认应用）

数据来源：_state 模块读取 wb_present 写入的记录（按 workdir 索引，key 已规范化）。
增量同步：refresh 只追加新产物 / 重载已变更文件，不重建已有 tab，避免闪烁。
"""
import os
import sys
from pathlib import Path

# 注入插件根到 sys.path 以便跨模块导入 _state
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from PyQt5.QtCore import QUrl, Qt, pyqtSignal, pyqtSlot  # noqa: E402
from PyQt5.QtGui import QDesktopServices, QPixmap  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon  # noqa: E402

from .theme import (  # noqa: E402
    theme_colors,
    make_style,
    panel_style,
    tab_style,
    viewer_style,
    btn_style,
)

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

_MD_EXTS = {".md", ".markdown"}
_HTML_EXTS = {".html", ".htm"}
_TEXT_PREVIEW_LIMIT = 2 * 1024 * 1024


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


def _label_for_type(kind: str) -> str:
    return {
        "text": "📝", "image": "🖼 ", "pdf": "📕",
        "ppt": "📊", "sheet": "📈", "doc": "📘",
    }.get(kind, "📄")


def _wrap_html(body: str, is_dark: bool) -> str:
    """给 markdown 渲染结果加主题化样式包装"""
    if is_dark:
        base = (
            "body{background:#161e2d;color:rgba(255,255,255,0.90);}"
            "pre,code{background:#1d2533;color:#e0e0e0;}"
            "a{color:#66c6ff;} th{background:#1d2533;}"
        )
    else:
        base = "body{background:#ffffff;color:rgba(0,0,0,0.85);} pre,code{background:#f4f4f4;} a{color:#0078d4;}"
    return (
        '<html><head><meta charset="utf-8">'
        f"<style>body{{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;"
        f" line-height:1.65;padding:14px;}} {base} "
        'pre{padding:10px;border-radius:6px;overflow:auto;} '
        'code{padding:2px 5px;border-radius:3px;} '
        'table{border-collapse:collapse;} th,td{border:1px solid rgba(128,128,128,0.35);'
        ' padding:5px 10px;} blockquote{border-left:3px solid rgba(128,128,128,0.4);'
        ' margin-left:0;padding-left:12px;color:rgba(128,128,128,0.9);}'
        '</style></head><body>' + body + "</body></html>"
    )


class ArtifactPanelCard(QFrame):
    """workbuddy 产物卡片：头部 tab 条 + 下方整区内容预览（WorkBuddy 风格）。"""

    # 自动弹出信号：由 _state 监听者（可能运行在后台线程）emit，
    # 经 QueuedConnection 投递到主线程执行 UI 操作，避免跨线程 Qt 崩溃
    _auto_popup = pyqtSignal()

    # 类级单例（最近实例化的卡片，供 state listener 与 /artifacts 命令共享）
    _instance: "ArtifactPanelCard | None" = None

    # 待聚焦的产物绝对路径：present_files listener 写入，refresh 后消费激活对应 tab
    _pending_focus: str | None = None

    def __init__(self, owner=None, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._workdir = _get_workdir(owner)
        self._card_context_provider = None
        self._card_context = {}
        # absolute path -> {"tab_index": int, "mtime": float|None}
        self._open_tabs: dict[str, dict] = {}
        self._build_ui()
        self.refresh()
        ArtifactPanelCard._instance = self
        self._auto_popup.connect(self._do_auto_popup, Qt.QueuedConnection)

    # ── UI 构建 ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._title = QLabel("📦 产物", self)
        header.addWidget(self._title)
        self._summary = QLabel("", self)
        self._summary.setWordWrap(True)
        header.addWidget(self._summary, 1)
        self._folder_btn = QPushButton("打开目录", self)
        self._folder_btn.clicked.connect(self._on_open_folder)
        header.addWidget(self._folder_btn)
        self._refresh_btn = QPushButton("刷新", self)
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        self._clear_btn = QPushButton("清空", self)
        self._clear_btn.clicked.connect(self._on_clear)
        header.addWidget(self._clear_btn)
        root.addLayout(header)

        self._tabs = QTabWidget(self)
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close)
        root.addWidget(self._tabs, 1)

        self._apply_theme()

    # ── 数据加载（增量同步） ──────────────────────────────────

    @staticmethod
    def request_focus(absolute_path: str) -> None:
        """供 listener 调用：下次 refresh 后激活指定产物的 tab（不存在则新增）"""
        ArtifactPanelCard._pending_focus = absolute_path or None

    def refresh(self):
        self._apply_theme()
        wd = self._resolve_workdir()
        entries = _state.get_all(wd)

        seen: dict[str, dict] = {}   # absolute -> item（去重，保留最新元数据）
        for entry in entries:
            for it in entry.get("items", []):
                abs_key = it.get("absolute") or it.get("path", "")
                if abs_key:
                    seen[abs_key] = it

        focus_target = ArtifactPanelCard._pending_focus
        ArtifactPanelCard._pending_focus = None
        activated = -1

        for abs_key, item in seen.items():
            try:
                mtime = Path(abs_key).stat().st_mtime if Path(abs_key).exists() else None
            except OSError:
                mtime = None
            info = self._open_tabs.get(abs_key)
            if info is None:
                idx = self._add_tab(item)
                self._open_tabs[abs_key] = {"tab_index": idx, "mtime": mtime}
                if abs_key == focus_target:
                    activated = idx
            else:
                if mtime != info["mtime"]:
                    w = self._tabs.widget(info["tab_index"])
                    if w is not None:
                        self._load_content(w, item)
                    info["mtime"] = mtime
                if abs_key == focus_target:
                    activated = info["tab_index"]

        if activated >= 0:
            self._tabs.setCurrentIndex(activated)
        elif seen and self._tabs.currentIndex() < 0:
            self._tabs.setCurrentIndex(max(0, self._tabs.count() - 1))

        msg = _state.last_message(wd)
        total = len(seen)
        self._summary.setText(f"{total} 个产物 · {msg}" if msg else f"{total} 个产物")
        if total == 0:
            self._show_empty()

    def _show_empty(self):
        empty = QTextBrowser(self)
        empty.setFrameShape(QFrame.NoFrame)
        c = self._current_theme()
        empty.setStyleSheet(viewer_style(c, c["ff"], c["fs"]))
        empty.setPlainText(
            "暂无产物\n\n"
            "在对话中让助手完成任务后，它会调用 present_files 工具把成果文件呈现在这里；"
            "每个成果以标签页打开，下方即为完整内容。"
        )
        self._tabs.clear()
        self._open_tabs.clear()
        self._tabs.addTab(empty, "空")

    def _add_tab(self, item: dict) -> int:
        holder = QWidget(self)
        v = QVBoxLayout(holder)
        v.setContentsMargins(6, 6, 6, 6)
        viewer = self._make_viewer(item)
        v.addWidget(viewer)
        self._load_content_into(viewer, holder, item)
        name = Path(item.get("path", "?")).name or item.get("path", "?")
        return self._tabs.addTab(
            holder, f"{_label_for_type(item.get('type', 'file'))} {name}"
        )

    # ── viewer 工厂与渲染 ─────────────────────────────────────

    def _make_viewer(self, item: dict) -> QWidget:
        kind = item.get("type", "file")
        suffix = Path(item.get("absolute", "")).suffix.lower()
        if kind == "image":
            lbl = QLabel("加载中…", self)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setProperty("wb_role", "image")
            return lbl
        if suffix in _HTML_EXTS and _WEB_ENGINE_OK:
            web = QWebEngineView(self)
            web.setProperty("wb_role", "web")
            return web
        tb = QTextBrowser(self)
        tb.setFrameShape(QFrame.NoFrame)
        tb.setOpenExternalLinks(False)
        tb.setOpenLinks(False)
        tb.anchorClicked.connect(lambda url, t=tb: self._on_anchor(url))
        tb.setProperty("wb_role", "text")
        return tb

    def _load_content(self, widget_holder: QWidget, item: dict):
        viewer = widget_holder.findChild(QWidget)
        self._load_content_into(viewer, widget_holder, item)

    def _load_content_into(self, viewer: QWidget, holder: QWidget, item: dict):
        """按类型把文件内容载入 viewer。"""
        if viewer is None:
            return
        full = Path(item.get("absolute") or item.get("path", ""))
        kind = item.get("type", "file")
        suffix = full.suffix.lower()
        role = viewer.property("wb_role")

        def _meta(html: str):
            if role == "web":
                viewer.setUrl(QUrl("about:blank"))
            if role == "image":
                viewer.setText(html)
            else:
                c = self._current_theme()
                viewer.setHtml(
                    f"<body style=\"font-family:'{c['ff']}';font-size:{c['fs']}px;\">{html}</body>"
                )

        if not full.exists():
            _meta(f"<p>文件不存在：</p><p>{full}</p>")
            return

        try:
            # 图片：按视口上限缩放（KeepAspectRatio + SmoothTransformation）
            if role == "image":
                pm = QPixmap(str(full))
                if pm.isNull():
                    _meta(f"无法解码图片：{full.name}")
                else:
                    vw = max(self._tabs.viewport() and self._tabs.viewport().width() or 600, 300)
                    vh = max(self._tabs.viewport() and self._tabs.viewport().height() or 400, 200)
                    scaled = pm.scaled(vw - 24, vh - 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    viewer.setPixmap(scaled)
                    viewer.setToolTip(full.as_uri())
                return

            # HTML → WebEngine / 降级文本
            if role == "web":
                viewer.setUrl(QUrl.fromLocalFile(str(full)))
                return

            # Markdown → HTML 渲染
            if suffix in _MD_EXTS:
                text = full.read_text(encoding="utf-8", errors="replace")
                if _MARKDOWN_OK:
                    html = _md.markdown(text, extensions=["fenced_code", "tables"])
                    c = self._current_theme()
                    viewer.setHtml(_wrap_html(html, c["is_dark"]))
                else:
                    viewer.setPlainText(text)
                return

            # 普通文本（≤2MB）
            if kind == "text":
                if full.stat().st_size > _TEXT_PREVIEW_LIMIT:
                    uri = full.as_uri()
                    _meta(
                        f"<p>文本过大（&gt;2 MB），不支持内嵌预览。</p>"
                        f"<p><a href=\"{uri}\">在系统中打开 {full}</a></p>"
                    )
                    return
                text = full.read_text(encoding="utf-8", errors="replace")
                viewer.setPlainText(text)
                return

            # 二进制/office 等：元信息 + 打开链接
            size = full.stat().st_size
            lines = item.get("lines")
            uri = full.as_uri()
            _meta(
                f"<p>该类型不支持内嵌预览：</p>"
                f"<p><a href=\"{uri}\">{full}</a></p>"
                f"<p>类型：{kind}　大小：{size:,} 字节　行数：{lines if lines is not None else '—'}</p>"
            )
        except OSError as exc:
            _meta(f"读取失败：{exc}")

    def _on_anchor(self, url: QUrl):
        QDesktopServices.openUrl(url)

    # ── 动作 ──────────────────────────────────────────────────

    def _on_tab_close(self, index: int):
        w = self._tabs.widget(index)
        if w is not None:
            for abs_key, info in list(self._open_tabs.items()):
                if info["tab_index"] == index:
                    del self._open_tabs[abs_key]
                elif info["tab_index"] > index:
                    info["tab_index"] -= 1
            self._tabs.removeTab(index)

    def _on_clear(self):
        _state.clear(self._resolve_workdir())
        self._open_tabs.clear()
        self.refresh()

    def _on_open_folder(self):
        wd = self._resolve_workdir()
        if wd:
            QDesktopServices.openUrl(QUrl.fromLocalFile(wd))

    @pyqtSlot()
    def _do_auto_popup(self):
        """主线程槽：由 _auto_popup 信号（QueuedConnection）触发。

        所有 Qt UI 操作集中在此，确保只在主线程执行。
        """
        try:
            self.refresh()
            self.show()
            self.raise_()
        except Exception:
            from loguru import logger
            logger.exception("[workbuddy] 自动弹窗失败")

    def closeEvent(self, event):
        """关闭时清理类级单例，避免僵尸 _instance 引用已析构 C++ 对象。"""
        if ArtifactPanelCard._instance is self:
            ArtifactPanelCard._instance = None
        super().closeEvent(event)

    # ── 上下文 / 主题 ──────────────────────────────────────────

    def set_context_provider(self, provider) -> None:
        """registry 拉模型注入：保存 provider 以便动态获取 workdir 与主题色。"""
        self._card_context_provider = provider
        try:
            self._card_context = provider() or {}
        except Exception:
            self._card_context = {}

    def _ui_context(self) -> dict:
        ctx = {}
        if self._card_context_provider is not None:
            try:
                ctx = self._card_context_provider() or {}
            except Exception:
                ctx = {}
        if not ctx and isinstance(self._card_context, dict):
            ctx = self._card_context
        return ctx

    def _resolve_workdir(self) -> str:
        """从 registry 注入的 UI 上下文动态解析 workdir。

        present_files 按真实项目 workdir 写入 _state；卡片实例化时 owner 为
        None（registry 只传 parent），必须每次从 context provider 取。
        key 经 _state 内部规范化，无需此处再做 normcase。
        """
        ctx = self._ui_context()
        wd = ctx.get("project_root") or ctx.get("workdir") or self._workdir
        if wd:
            try:
                return str(Path(wd).resolve())
            except Exception:
                return str(wd)
        # provider 未就绪时回退 cwd：避免面板因短暂拿不到上下文而永远空白
        # （_state key 已在模块内规范化，两侧口径一致）
        return os.getcwd()

    def _current_theme(self) -> dict:
        return theme_colors(self._ui_context())

    def _apply_theme(self) -> None:
        """按当前 UI 上下文（深浅 / 字体 / 主题色）刷新所有控件的 QSS。"""
        c = self._current_theme()
        ff, fs = c["ff"], c["fs"]
        self.setStyleSheet(panel_style(c))
        self._title.setStyleSheet(
            make_style(c["text"], ff, max(fs - 1, 12)) + "font-weight:600;"
        )
        self._summary.setStyleSheet(make_style(c["secondary"], ff, 11))
        self._tabs.setStyleSheet(tab_style(c, ff, fs))
        self._folder_btn.setStyleSheet(btn_style(c, ff, fs))
        self._refresh_btn.setStyleSheet(btn_style(c, ff, fs))
        self._clear_btn.setStyleSheet(btn_style(c, ff, fs))

    # ── /artifacts 命令 handler ──────────────────────────────

    @staticmethod
    def handle_command(args: str = "", owner=None):
        """/artifacts 命令调用入口：刷新并显示面板（修复旧实现引用未赋值的
        _CURRENT_CARD 导致永远返回 False 的 bug，统一走类级单例）"""
        card = ArtifactPanelCard._instance
        if card is None:
            return False
        card.refresh()
        card.show()
        card.raise_()
        return True


def cleanup() -> None:
    """卸载/热重载清理"""
    ArtifactPanelCard._instance = None
    ArtifactPanelCard._pending_focus = None
