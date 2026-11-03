# -*- coding: utf-8 -*-
"""文档设计窗口：工具栏（打开/拾取/标注/发送标注/缩放）+ 分页预览 + 状态栏。

拾取：页面内 JS 点击监听回传锚点与矩形，Python 裁剪截图并回填。
标注：标注态点击元素弹注释框，角标编号；「发送标注」把全部注释一次性回填。
分页：sectPr 页面尺寸 + JS 装箱分页，页眉页脚随页重复。
"""

import hashlib
import json
from pathlib import Path

from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

from .docx_parser import docx_header_footer, docx_page_setup, parse_document
from .html_renderer import render_html
from .picker import DocxBridge, capture_view_rect, write_input
from .pick_format import format_annotations, format_pick
from .theme import theme_colors

_CURRENT_CARD = None


def _get_current_card():
    return _CURRENT_CARD


class DocxWindowCard(QWidget):
    """文档设计浮动卡片。widget 契约：__init__(parent=None) + show_card + set_context_provider。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        global _CURRENT_CARD
        _CURRENT_CARD = self

        self._context_provider = None
        self._blocks = []
        self._current_path = ""
        self._pick_on = False
        self._annotate_on = False
        self._count = 0
        self._annotations = []
        self._fs = 15
        self._accent_hex = "#66c6ff"
        self._outer_bg = "#1d2533"
        self._ff = "Microsoft YaHei"
        self._setup_ui()
        self._setup_webchannel()
        self.setAcceptDrops(True)
        try:
            from app.utils.theme_manager import theme_manager

            theme_manager.register_refresh_target(self)
        except Exception:
            pass

    def set_context_provider(self, provider):
        self._context_provider = provider

    def show_card(self):
        self.refresh_theme()
        self.setVisible(True)

    def refresh_theme(self):
        self._apply_theme()

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumSize(560, 420)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(10, 8, 10, 8)
        top.setSpacing(8)
        self._name_label = QLabel("未打开文档")
        top.addWidget(self._name_label, 1)
        self._btn_open = QPushButton("打开")
        self._btn_open.clicked.connect(self._on_open_clicked)
        self._btn_pick = QPushButton("拾取")
        self._btn_pick.clicked.connect(self.toggle_pick)
        self._btn_annotate = QPushButton("标注")
        self._btn_annotate.clicked.connect(self.toggle_annotate)
        self._btn_send = QPushButton("发送标注")
        self._btn_send.clicked.connect(self._send_annotations)
        self._btn_smaller = QPushButton("A−")
        self._btn_smaller.clicked.connect(lambda: self._zoom(-1))
        self._btn_bigger = QPushButton("A+")
        self._btn_bigger.clicked.connect(lambda: self._zoom(1))
        for b in (self._btn_open, self._btn_pick, self._btn_annotate,
                  self._btn_send, self._btn_smaller, self._btn_bigger):
            top.addWidget(b)
        root.addLayout(top)

        self._view = QWebEngineView(self)
        root.addWidget(self._view, 1)

        self._status = QLabel("拖入 .docx 文件，或点「打开」")
        self._status.setContentsMargins(10, 4, 10, 6)
        root.addWidget(self._status)
        self._apply_theme()

    def _setup_webchannel(self):
        self._bridge = DocxBridge(self)
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("docxbridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

    def _apply_theme(self):
        c = theme_colors(self)
        accent_hex = "#66c6ff" if c["is_dark"] else "#0078d4"
        self._accent_hex = accent_hex
        self._ff = c["ff"]
        self.setStyleSheet(
            f"DocxWindowCard {{ background: {c['surface']}; "
            f"font-family: '{c['ff']}'; font-size: {c['fs']}px; }}"
            f"QLabel {{ color: {c['text']}; font-family: '{c['ff']}'; font-size: {c['fs']}px; }}"
            f"QPushButton {{ background: {c['raised']}; border: 1px solid {c['border']};"
            f" border-radius: 6px; color: {c['text']}; padding: 5px 14px;"
            f" font-family: '{c['ff']}'; font-size: {c['fs']}px; }}"
            f"QPushButton:hover {{ background: {c['hover']}; }}"
            f"QPushButton:checked {{ border-color: {accent_hex}; }}"
        )
        self._outer_bg = c["raised"]

    # ── 打开文档 ──

    def _on_open_clicked(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 Word 文档", "", "Word 文档 (*.docx)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        """解析并渲染 docx。供工具侧调用；返回是否成功。"""
        p = Path(path)
        if not p.is_file():
            self._set_status(f"文件不存在: {path}")
            return False
        if p.suffix.lower() != ".docx":
            self._set_status("仅支持 .docx 文件")
            return False
        try:
            blocks = parse_document(str(p))
        except Exception as e:
            self._set_status(f"解析失败: {e}")
            return False
        self._blocks = blocks
        self._current_path = str(p)
        self._count = 0
        self._pick_on = False
        self._annotate_on = False
        self._btn_pick.setDown(False)
        self._btn_annotate.setDown(False)
        restored = self._load_annotations()
        self._annotations = list(restored)
        html = render_html(
            blocks,
            outer=self._outer_bg,
            accent=self._accent_hex,
            page_setup=docx_page_setup(str(p)),
            hdr_ftr=docx_header_footer(str(p)),
            restored=restored,
        )
        self._view.setHtml(html, QUrl("http://docx-designer.local/"))
        self._name_label.setText(p.name)
        note = f"，恢复 {len(restored)} 条历史标注" if restored else ""
        self._set_status(f"已打开 {p.name}（{len(blocks)} 个块）{note}；「标注」读文档写注释，「发送标注」统一交给模型")
        return True

    # ── 拾取 ──

    def toggle_pick(self):
        self.set_pick_mode(not self._pick_on)

    def set_pick_mode(self, on):
        self._pick_on = bool(on)
        if on:
            self._annotate_on = False
            self._btn_annotate.setDown(False)
            self._view.page().runJavaScript("document.body.classList.remove('annotate');")
        flag = "true" if on else "false"
        self._view.page().runJavaScript(f"document.body.classList.toggle('pick', {flag});")
        self._btn_pick.setDown(on)
        if on:
            self._set_status("拾取模式：点击文档元素回填输入框（Esc 退出）")
        else:
            self._set_status("拾取模式已退出")

    # ── 标注 ──

    def toggle_annotate(self):
        self.set_annotate_mode(not self._annotate_on)

    def set_annotate_mode(self, on):
        self._annotate_on = bool(on)
        if on:
            self._pick_on = False
            self._btn_pick.setDown(False)
            self._view.page().runJavaScript("document.body.classList.remove('pick');")
        flag = "true" if on else "false"
        self._view.page().runJavaScript(f"document.body.classList.toggle('annotate', {flag});")
        self._btn_annotate.setDown(on)
        if on:
            self._set_status("标注模式：点击元素写注释，通读完点「发送标注」统一交给模型（Esc 退出）")
        else:
            self._set_status("标注模式已退出")

    def on_annotation_added(self, anchor, comment, seq, snippet):
        self._annotations.append(
            {"anchor": anchor, "comment": comment, "seq": seq, "snippet": snippet}
        )
        self._save_annotations()
        self._set_status(f"已保存第 {seq} 条标注（共 {len(self._annotations)} 条，Esc 退出）")

    def _annotations_path(self):
        try:
            from app.plugins.sdk import caps_for

            root = Path(str(caps_for("storage.data_dir", plugin="docx-designer", surface="ui")))
        except Exception:
            root = Path.home() / ".drifox"
        key = hashlib.md5(self._current_path.encode("utf-8")).hexdigest()[:12]
        d = root / "plugin_data" / "docx-designer" / "annotations"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{key}.json"

    def _save_annotations(self):
        try:
            self._annotations_path().write_text(
                json.dumps(self._annotations, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except Exception:
            pass

    def _load_annotations(self):
        try:
            f = self._annotations_path()
            if f.is_file():
                return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def _send_annotations(self):
        if not self._annotations:
            self._set_status("没有可发送的标注（先进入「标注」模式写注释）")
            return
        text = format_annotations(self._current_path or "?", self._annotations)
        if write_input(text, count=2):
            self._set_status(f"已发送 {len(self._annotations)} 条标注到输入框")
        else:
            self._set_status("发送失败（能力 input.write 不可用）")

    def on_element_picked(self, anchor, x, y, w, h, preview):
        shot = capture_view_rect(self._view, x, y, w, h)
        self._count += 1
        text = format_pick(
            self._count,
            self._current_path or "?",
            anchor,
            self._lookup_block(anchor),
            preview,
            str(shot) if shot else None,
            include_guide=(self._count == 1),
        )
        if write_input(text, self._count):
            self._set_status(f"已回填第 {self._count} 个元素（Esc 退出）")
        else:
            self._set_status("已拾取，但输入框写入失败（能力 input.write 不可用）")

    def _lookup_block(self, anchor):
        """锚点 → 所在块（单元格锚点返回其表格块）；找不到返回 None。"""
        idx_s = anchor.split(":", 1)[0]
        for b in self._blocks:
            if b["anchor"] == idx_s:
                return b
        return None

    # ── 缩放 ──

    def _zoom(self, delta):
        self._fs = max(11, min(24, self._fs + delta))
        self._view.page().runJavaScript(
            f"document.documentElement.style.setProperty('--doc-fs', '{self._fs}px');"
            " setTimeout(function(){ if (window.paginate) paginate(); }, 30);"
        )
        self._set_status(f"正文字号 {self._fs}px（已重新分页）")

    def _set_status(self, text):
        self._status.setText(text)

    # ── 拖拽 ──

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(".docx"):
                self.open_path(p)
                break
