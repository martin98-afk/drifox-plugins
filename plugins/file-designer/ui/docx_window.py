# -*- coding: utf-8 -*-
"""文件设计窗口：工具栏（打开/拾取/标注/发送标注/缩放）+ 分页预览 + 状态栏。

拾取：页面内 JS 点击监听回传锚点与矩形，Python 裁剪截图并回填。
标注：标注态点击元素弹注释框，角标编号；「发送标注」把全部注释一次性回填。
分页：sectPr 页面尺寸 + JS 装箱分页，页眉页脚随页重复。
"""

import hashlib
import json
from pathlib import Path

from PyQt5.QtCore import QFile, QEvent, QUrl
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

from .docx_parser import docx_header_footer, docx_page_setup, parse_document
from .external_open import open_in_system
from .formats import spec_for, suffix_label
from .html_renderer import render_html
from .picker import DocxBridge, capture_view_rect, write_input
from .pick_format import format_annotations, format_pick
from .theme import theme_colors

_CURRENT_CARD = None


def _get_current_card():
    return _CURRENT_CARD


class DocxWindowCard(QWidget):
    """文件设计浮动卡片。widget 契约：__init__(parent=None) + show_card + set_context_provider。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        global _CURRENT_CARD
        _CURRENT_CARD = self

        self._context_provider = None
        self._blocks = []
        self._pptx_model = None
        self._generic_model = None
        self._generic_mode = ""
        self._mode = "docx"
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
        self._btn_more = QPushButton("≡")
        more_menu = QMenu(self._btn_more)
        self._more_menu = more_menu
        more_menu.addAction("发送标注", self._send_annotations)
        more_menu.addAction("清空标注", self._clear_annotations)
        more_menu.addAction("重新加载文档", self._reload_document)
        more_menu.addAction("用系统程序打开", self._open_external)
        more_menu.addSeparator()
        more_menu.addAction("增大字号", lambda: self._zoom(1))
        more_menu.addAction("减小字号", lambda: self._zoom(-1))
        self._btn_more.setMenu(more_menu)
        for b in (self._btn_open, self._btn_pick, self._btn_annotate, self._btn_more):
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
        self._view.loadFinished.connect(self._ensure_drop_filter)
        self._ensure_drop_filter()

    def _ensure_drop_filter(self, *args):
        """把拖拽过滤器幂等装到 WebEngine 内部 delegate（focusProxy）上。

        预览区被 QWebEngineView 铺满，拖拽事件的第一接收者是内部 delegate
        （RenderWidgetHostViewQtDelegateWidget，即 focusProxy），落在父窗口的
        dragEnterEvent/dropEvent 永远收不到。delegate 在页面加载/显示后才就绪
        且可能重建，按宿主 card_viewers 同款模式在 loadFinished/showEvent 补装
        （不能用 ChildAdded，delegate 构造期直挂不发该事件）。
        """
        try:
            fp = self._view.focusProxy()
        except RuntimeError:
            return
        if fp is None or fp is getattr(self, "_drop_filter_target", None):
            return
        fp.installEventFilter(self)
        self._drop_filter_target = fp

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_drop_filter()

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "_drop_filter_target", None):
            t = ev.type()
            if t in (QEvent.DragEnter, QEvent.DragMove):
                if ev.mimeData().hasUrls():
                    ev.acceptProposedAction()
                    return True
                ev.ignore()
                return True
            if t == QEvent.Drop:
                if ev.mimeData().hasUrls():
                    self.dropEvent(ev)
                    ev.acceptProposedAction()
                    return True
                ev.ignore()
                return True
        return super().eventFilter(obj, ev)

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
            f"QPushButton::menu-indicator {{ image: none; width: 0px; }}"
            f"QMenu {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};"
            f" font-family: '{c['ff']}'; font-size: {c['fs']}px; }}"
            f"QMenu::item {{ padding: 6px 24px; font-family: '{c['ff']}'; font-size: {c['fs']}px; }}"
            f"QMenu::item:selected {{ background: {c['hover']}; }}"
        )
        self._outer_bg = c["raised"]
        self._more_menu.setFont(QFont(c["ff"], c["fs"]))

    # ── 打开文档 ──

    def _on_open_clicked(self):
        from .formats import SUPPORTED_SUFFIXES

        patterns = " ".join("*" + s for s in SUPPORTED_SUFFIXES)
        path, _ = QFileDialog.getOpenFileName(
            self, "打开文件", "", f"支持的文件 ({patterns})"
        )
        if path:
            self.open_path(path)

    def open_path(self, path):
        """解析并渲染受支持格式。供工具侧调用；返回是否成功。"""
        p = Path(path)
        if not p.is_file():
            self._set_status(f"文件不存在: {path}")
            return False
        suffix = p.suffix.lower()
        spec = spec_for(suffix)
        if spec is None:
            self._set_status(f"仅支持 {suffix_label()} 文件")
            return False
        if spec["generic"]:
            return self._open_generic(p, spec)
        if suffix == ".pptx":
            return self._open_pptx(p)
        try:
            blocks = parse_document(str(p))
        except Exception as e:
            self._set_status(f"解析失败: {e}")
            return False
        self._reset_state("docx")
        self._blocks = blocks
        self._current_path = str(p)
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
        self._load_html(html)
        self._name_label.setText(p.name)
        note = f"，恢复 {len(restored)} 条历史标注" if restored else ""
        self._set_status(f"已打开 {p.name}（{len(blocks)} 个块）{note}；「标注」读文档写注释，「发送标注」统一交给模型")
        return True

    def _open_generic(self, p, spec):
        """xmind / xlsx / csv / mermaid：注册表 parse → render → 复用拾取/标注桥。"""
        try:
            model = spec["parse"](str(p))
        except ImportError as e:
            self._set_status(f"格式支持不可用（缺依赖）: {e}")
            return False
        except Exception as e:
            self._set_status(f"解析失败: {e}")
            return False
        self._reset_state(spec["mode"])
        self._generic_model = model
        self._generic_mode = spec["mode"]
        self._current_path = str(p)
        restored = self._load_annotations()
        self._annotations = list(restored)
        try:
            html = spec["render"](
                model, outer=self._outer_bg, accent=self._accent_hex, restored=restored
            )
        except Exception as e:
            self._set_status(f"渲染失败: {e}")
            return False
        self._load_html(html)
        self._name_label.setText(p.name)
        note = f"，恢复 {len(restored)} 条历史标注" if restored else ""
        warn = "（内容超上限已截断）" if model.get("truncated") else ""
        self._set_status(
            f"已打开 {p.name}（{spec['status']}）{note}{warn}；「拾取」取元素，「标注」写注释"
        )
        return True

    def _reset_state(self, mode):
        self._mode = mode
        self._blocks = []
        self._pptx_model = None
        self._generic_model = None
        self._generic_mode = "" if mode in ("docx", "pptx") else mode
        self._current_path = ""
        self._count = 0
        self._pick_on = False
        self._annotate_on = False
        self._btn_pick.setDown(False)
        self._btn_annotate.setDown(False)

    def _preview_file(self):
        """大 HTML 落盘文件（两个名字轮换，避免同 URL 缓存）。"""
        try:
            from app.plugins.sdk import caps_for

            # 必须 resolve：开发宿主 get_app_data_dir() 返回相对路径 .drifox，
            # 相对路径进 QUrl.fromLocalFile 生成 file:.drifox/... 畸形 URL → ERR_FILE_NOT_FOUND
            root = Path(str(caps_for("storage.data_dir", plugin="file-designer", surface="ui"))).resolve()
        except Exception:
            root = Path.home() / ".drifox"
        d = root / "plugin_data" / "file-designer"
        d.mkdir(parents=True, exist_ok=True)
        self._pv_flip = not getattr(self, "_pv_flip", False)
        return d / ("preview_a.html" if self._pv_flip else "preview_b.html")

    def _inline_qwebchannel(self, html):
        """qwebchannel.js 内联（QFile 读 qrc 资源）：file:// 加载路径下拾取/标注桥照常可用。"""
        tag = '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'
        if tag not in html:
            return html
        try:
            f = QFile(":/qtwebchannel/qwebchannel.js")
            if not f.open(QFile.ReadOnly):
                return html
            data = bytes(f.readAll()).decode("utf-8", "replace")
            f.close()
            return html.replace(tag, f"<script>{data}</script>", 1)
        except Exception:
            return html

    def _load_html(self, html):
        """>1.5MB 走本地文件加载：setHtml 超 ~2MB 静默不渲染（售前 PPT 39MB HTML
        表现为状态栏「已打开」但内容不刷新）。"""
        payload = self._inline_qwebchannel(html)
        try:
            size = len(payload.encode("utf-8"))
        except Exception:
            size = len(payload)
        if size <= 1_500_000:
            self._view.setHtml(payload, QUrl("http://file-designer.local/"))
            return
        f = self._preview_file()
        try:
            f.write_text(payload, encoding="utf-8")
        except Exception:
            self._view.setHtml(payload, QUrl("http://file-designer.local/"))
            return
        self._view.load(QUrl.fromLocalFile(str(f)))

    def _open_pptx(self, p):
        """pptx：固定画布绝对定位渲染，拾取/标注复用同一套桥。"""
        try:
            from .pptx_parser import parse_presentation
            from .pptx_renderer import render_pptx_html
        except Exception as e:
            self._set_status(f"pptx 支持不可用: {e}")
            return False
        try:
            model = parse_presentation(str(p))
        except Exception as e:
            self._set_status(f"解析失败: {e}")
            return False
        self._reset_state("pptx")
        self._pptx_model = model
        self._current_path = str(p)
        restored = self._load_annotations()
        self._annotations = list(restored)
        html = render_pptx_html(
            model, outer=self._outer_bg, accent=self._accent_hex, restored=restored
        )
        self._load_html(html)
        self._name_label.setText(p.name)
        note = f"，恢复 {len(restored)} 条历史标注" if restored else ""
        self._set_status(
            f"已打开 {p.name}（{len(model['slides'])} 页）{note}；「拾取」取元素，「标注」写注释"
        )
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

    def on_annotation_added(self, anchor, comment, seq, snippet, x, y, w, h):
        shot = capture_view_rect(self._view, x, y, w, h)
        self._annotations.append(
            {"anchor": anchor, "comment": comment, "seq": seq, "snippet": snippet,
             "shot": str(shot) if shot else None}
        )
        self._save_annotations()
        self._set_status(f"已保存第 {seq} 条标注（共 {len(self._annotations)} 条，Esc 退出）")

    def on_annotation_updated(self, anchor, comment):
        for a in self._annotations:
            if a["anchor"] == anchor:
                a["comment"] = comment
        self._save_annotations()
        self._set_status(f"标注 [{anchor}] 已更新")

    def on_annotation_deleted(self, anchor):
        before = len(self._annotations)
        self._annotations = [a for a in self._annotations if a.get("anchor") != anchor]
        if len(self._annotations) == before:
            return
        for i, a in enumerate(self._annotations, 1):
            a["seq"] = i
        self._save_annotations()
        self._set_status(f"已删除标注，剩余 {len(self._annotations)} 条")

    def _confirm_clear(self, count):
        """宿主统一 ConfirmDialog（MaskDialogBase 风格）；不可用时回退 QMessageBox。"""
        try:
            from app.widgets.common_dialogs import ConfirmDialog

            dialog = ConfirmDialog(
                title="清空标注",
                content=f"确定删除全部 {count} 条标注？删除后不可恢复。",
                confirm_text="清空",
                cancel_text="取消",
                parent=self.window(),
            )
            picked = {"ok": False}
            dialog.confirmed.connect(lambda: picked.update(ok=True))
            dialog.exec_()
            return picked["ok"]
        except Exception:
            ans = QMessageBox.question(
                self, "清空标注", f"确定删除全部 {count} 条标注？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            return ans == QMessageBox.Yes

    def _clear_annotations(self):
        if not self._annotations:
            self._set_status("当前没有标注")
            return
        if not self._confirm_clear(len(self._annotations)):
            return
        self._annotations = []
        self._save_annotations()
        self._view.page().runJavaScript(
            "window.__clearAnnotations && window.__clearAnnotations();"
        )
        self._set_status("已清空全部标注")

    def _reload_document(self):
        """重新解析当前文档（外部修改后刷新预览，保留拾取计数与标注）。"""
        if not self._current_path:
            self._set_status("尚未打开文档")
            return
        count = self._count
        if self.open_path(self._current_path):
            self._count = count
            self._set_status(f"已重新加载 {Path(self._current_path).name}")

    def _open_external(self):
        """用系统默认程序打开当前文档（绕过拦截）"""
        if not self._current_path:
            self._set_status("尚未打开文档")
            return
        try:
            open_in_system(self._current_path)
            self._set_status(f"已用系统默认程序打开: {Path(self._current_path).name}")
        except Exception as e:
            self._set_status(f"系统打开失败: {e}")

    def _annotations_path(self):
        try:
            from app.plugins.sdk import caps_for

            root = Path(str(caps_for("storage.data_dir", plugin="file-designer", surface="ui")))
        except Exception:
            root = Path.home() / ".drifox"
        key = hashlib.md5(self._current_path.encode("utf-8")).hexdigest()[:12]
        d = root / "plugin_data" / "file-designer" / "annotations"
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
        text = format_annotations(
            self._current_path or "?", self._annotations, mode=self._mode
        )
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
            mode=self._mode,
        )
        if write_input(text, self._count):
            self._set_status(f"已回填第 {self._count} 个元素（Esc 退出）")
        else:
            self._set_status("已拾取，但输入框写入失败（能力 input.write 不可用）")

    def _lookup_block(self, anchor):
        """锚点 → 所在块（单元格锚点返回其表格块）；找不到返回 None。"""
        if self._mode == "pptx":
            return self._lookup_pptx_shape(anchor)
        if self._generic_model is not None:
            try:
                return self._generic_model["lookup"](anchor)
            except Exception:
                return None
        idx_s = anchor.split(":", 1)[0]
        for b in self._blocks:
            if b["anchor"] == idx_s:
                return b
        return None

    def _lookup_pptx_shape(self, anchor):
        try:
            si, idx = (int(x) for x in anchor.split(":", 1))
            sh = self._pptx_model["slides"][si]["shapes"][idx]
        except Exception:
            return None
        kind = sh.get("kind")
        if kind == "table":
            rows = [[{"text": c.get("text") or ""} for c in row] for row in sh.get("rows") or []]
            return {"kind": "table", "style": "表格", "rows": rows, "text": ""}
        if kind == "text":
            text = "\n".join(
                "".join(r.get("text") or "" for r in p.get("runs") or [])
                for p in sh.get("paras") or []
            )
            return {"kind": "text", "style": "文本框", "text": text}
        if kind == "image":
            return {"kind": "image", "style": "图片", "text": ""}
        return {"kind": kind or "shape", "style": "形状", "text": ""}

    # ── 缩放 ──

    def _zoom(self, delta):
        self._fs = max(11, min(24, self._fs + delta))
        if self._generic_model is not None:
            zoom = round(self._fs / 15.0, 2)
            self._view.page().runJavaScript(
                f"document.body.style.zoom='{zoom}';"
            )
            self._set_status(f"缩放 {int(zoom * 100)}%")
            return
        if self._mode == "pptx":
            zoom = round(self._fs / 15.0, 2)
            self._view.page().runJavaScript(
                f"var d=document.getElementById('deck'); if(d) d.style.zoom='{zoom}';"
            )
            self._set_status(f"幻灯片缩放 {int(zoom * 100)}%")
            return
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
        from .formats import SUPPORTED_SUFFIXES

        opened = False
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(tuple(SUPPORTED_SUFFIXES)):
                self.open_path(p)
                opened = True
                break
        if not opened:
            self._set_status(f"仅支持 {suffix_label()} 文件")
