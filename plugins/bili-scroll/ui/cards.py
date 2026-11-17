# -*- coding: utf-8 -*-
"""B站值班工作台：状态摘要、日报阅读、近期视频与折叠诊断。"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
import traceback
from html import escape
from typing import Any, Callable, Optional

from PyQt5.QtCore import QObject, QThread, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from loguru import logger
from qfluentwidgets import (
    FluentIcon,
    PrimaryPushButton,
    TransparentToolButton,
    isDarkTheme,
)


class _Reader(QTextBrowser):
    """只读内容；链接交给系统浏览器，不自动读取日报里的外部资源。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.anchorClicked.connect(self._open_link)

    def loadResource(self, resource_type, url):
        return None

    def _open_link(self, url: QUrl):
        if url.scheme().lower() in {"http", "https"}:
            QDesktopServices.openUrl(url)


class _Worker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            self.finished.emit(self._fn(*self._args))
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")


class BiliScrollCard(QWidget):
    """保留原值班能力的原生 Qt 工作台。"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._round_running = False
        self._seen_rows: list[dict] = []
        self._summary_columns = 0
        self._setup_ui()

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider
        self._apply_theme()

    def show_card(self):
        """宿主藏卡后重新打开时，显式恢复可见性。"""
        self._apply_theme()
        self._async_load()
        self.setVisible(True)

    def refresh_style(self):
        self._apply_theme()

    def _apply_theme(self):
        ctx = (self._context_provider() or {}) if self._context_provider else {}
        dark = ctx.get("is_dark", isDarkTheme())
        colors = ctx.get("colors") or {}
        text = colors.get("text_primary") or ("#ececf0" if dark else "#23252c")
        secondary = colors.get("text_secondary") or ("#a6a8b3" if dark else "#717582")
        accent = colors.get("accent") or ("#9b92f8" if dark else "#6554c0")
        border = colors.get("border") or ("rgba(255,255,255,0.10)" if dark else "rgba(0,0,0,0.09)")
        surface = "rgba(255,255,255,0.035)" if dark else "rgba(255,255,255,0.65)"
        soft = "rgba(255,255,255,0.045)" if dark else "rgba(0,0,0,0.025)"
        base = max(12, int(ctx.get("font_size", 14)))
        font = QFont(ctx.get("font_family") or self.font().family())
        font.setPixelSize(base)
        self.setFont(font)
        self._secondary_color = secondary
        self._accent_color = accent
        self._border_color = border
        self.setObjectName("biliDutyCard")
        self.setStyleSheet(f"""
            QWidget#biliDutyCard {{ background: transparent; color: {text}; }}
            QWidget#biliDutyPage, QScrollArea#biliDutyScroll {{ background: transparent; border: none; }}
            QWidget#biliDutyPage QLabel {{ color: {text}; background: transparent; border: none; }}
            QWidget#biliDutyPage QLabel[role="muted"] {{ color: {secondary}; font-size: {base - 2}px; }}
            QWidget#biliDutyPage QLabel[role="title"] {{ font-size: {base + 8}px; font-weight: 650; }}
            QWidget#biliDutyPage QLabel[role="section"] {{ font-size: {base + 1}px; font-weight: 600; }}
            QWidget#biliDutyPage QLabel[role="value"] {{ font-size: {base + 4}px; font-weight: 600; }}
            QWidget#biliDutyPage QLabel[role="empty-title"] {{ font-size: {base + 1}px; font-weight: 600; }}
            QFrame[role="metric"] {{ background: {soft}; border: 1px solid {border}; border-radius: 10px; }}
            QFrame[role="panel"] {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
            QTextBrowser {{ color: {text}; background: transparent; border: none; padding: 0; selection-background-color: {accent}; }}
            QToolButton#biliDetails {{ color: {secondary}; background: transparent; border: none; padding: 6px 0; text-align: left; }}
            QToolButton#biliDetails:hover {{ color: {accent}; }}
            QTextBrowser#biliDiagnostics {{ background: {soft}; border: 1px solid {border}; border-radius: 8px; padding: 10px; font-size: {base - 2}px; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {border}; border-radius: 3px; min-height: 24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        for reader in (self._report_view, self._seen_view, self._diagnostics):
            reader.setFont(font)
            reader.document().setDefaultFont(font)
            reader.document().setDefaultStyleSheet(
                f"body {{ color: {text}; line-height: 1.6; }} "
                f"a {{ color: {accent}; text-decoration: none; }} "
                f"p {{ margin-top: 6px; margin-bottom: 10px; }} "
                f"h1 {{ font-size: {base + 7}px; }} h2 {{ font-size: {base + 4}px; }} "
                f"h3 {{ font-size: {base + 2}px; margin-top: 18px; }} "
                f"blockquote {{ color: {secondary}; }}"
            )
        self._render_seen()

    def _label(self, text: str, role: str = "", parent=None) -> QLabel:
        lb = QLabel(text, parent or self._page)
        lb.setTextFormat(Qt.PlainText)
        lb.setProperty("role", role)
        lb.setMinimumWidth(0)
        lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        return lb

    def _empty_state(self, title: str, description: str, parent) -> QWidget:
        empty = QWidget(parent)
        layout = QVBoxLayout(empty)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        layout.addStretch()
        for text, role in ((title, "empty-title"), (description, "muted")):
            lb = self._label(text, role, empty)
            lb.setAlignment(Qt.AlignCenter)
            lb.setWordWrap(True)
            layout.addWidget(lb)
        layout.addStretch()
        return empty

    def _panel(self, title: str, subtitle: str, empty_title: str, empty_hint: str):
        panel = QFrame(self._page)
        panel.setProperty("role", "panel")
        panel.setMinimumWidth(0)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(self._label(title, "section", panel), 1)
        meta = self._label(subtitle, "muted", panel)
        meta.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        heading.addWidget(meta)
        layout.addLayout(heading)
        stack = QStackedWidget(panel)
        stack.setMinimumWidth(0)
        stack.setMinimumHeight(160)
        stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        stack.addWidget(self._empty_state(empty_title, empty_hint, stack))
        reader = _Reader(stack)
        stack.addWidget(reader)
        layout.addWidget(stack, 1)
        return panel, stack, reader, meta

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._page_scroll = QScrollArea(self)
        self._page_scroll.setObjectName("biliDutyScroll")
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._page = QWidget(self._page_scroll)
        self._page.setObjectName("biliDutyPage")
        self._page_scroll.setWidget(self._page)
        root.addWidget(self._page_scroll)
        lay = QVBoxLayout(self._page)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self._title_lb = self._label("B站值班", "title")
        titles.addWidget(self._title_lb)
        titles.addWidget(self._label("替你筛选值得看的内容", "muted"))
        header.addLayout(titles, 1)
        self._run_btn = PrimaryPushButton("跑一轮", self._page)
        self._run_btn.setMinimumWidth(96)
        self._run_btn.setFixedHeight(36)
        self._run_btn.setToolTip("后台搜视频、读字幕、写日报，约 5–20 分钟；评论仍受原有授权控制")
        self._run_btn.clicked.connect(self._on_run_round)
        header.addWidget(self._run_btn)
        self._refresh_btn = TransparentToolButton(FluentIcon.SYNC, self._page)
        self._refresh_btn.setToolTip("刷新状态与日报")
        self._refresh_btn.clicked.connect(self._async_load)
        header.addWidget(self._refresh_btn)
        self._close_btn = TransparentToolButton(FluentIcon.CLOSE, self._page)
        self._close_btn.setToolTip("关闭值班卡片")
        self._close_btn.clicked.connect(self._on_close)
        header.addWidget(self._close_btn)
        lay.addLayout(header)

        self._summary_grid = QGridLayout()
        self._summary_grid.setSpacing(10)
        self._metric_cards = []
        self._metric_values = {}
        for key, title, hint in (
            ("quota", "今日精选", "已挑选 / 每日配额"),
            ("credential", "登录凭证", "仅检查本地凭证"),
            ("schedule", "自动值班", "按已配置时段运行"),
            ("comment", "自动评论", "由你在设置中授权"),
        ):
            box = QFrame(self._page)
            box.setProperty("role", "metric")
            column = QVBoxLayout(box)
            column.setContentsMargins(14, 12, 14, 12)
            column.setSpacing(5)
            column.addWidget(self._label(title, "muted", box))
            value = self._label("—", "value", box)
            column.addWidget(value)
            column.addWidget(self._label(hint, "muted", box))
            self._metric_cards.append(box)
            self._metric_values[key] = value
        lay.addLayout(self._summary_grid)

        self._body_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self._body_layout.setSpacing(14)
        self._report_panel, self._report_stack, self._report_view, self._report_meta = self._panel(
            "今日日报", dt.date.today().strftime("%m 月 %d 日"),
            "今天的精选，正在等你", "点击「跑一轮」，完成后在这里查看日报",
        )
        self._seen_panel, self._seen_stack, self._seen_view, self._seen_meta = self._panel(
            "最近看过", "0 条记录", "还没有浏览记录", "处理过的视频会在这里留下记录，避免重复筛选",
        )
        self._body_layout.addWidget(self._report_panel, 3)
        self._body_layout.addWidget(self._seen_panel, 2)
        lay.addLayout(self._body_layout, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._hint_lb = self._label("关键词、时段与评论授权可在插件设置中调整", "muted")
        self._hint_lb.setWordWrap(True)
        self._hint_lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        footer.addWidget(self._hint_lb, 1)
        self._open_btn = TransparentToolButton(FluentIcon.FOLDER, self._page)
        self._open_btn.setToolTip("打开值班数据目录：日报、判重表、归档")
        self._open_btn.clicked.connect(self._open_data_dir)
        footer.addWidget(self._open_btn)
        lay.addLayout(footer)

        self._details_btn = QToolButton(self._page)
        self._details_btn.setObjectName("biliDetails")
        self._details_btn.setText("环境检查")
        self._details_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._details_btn.setArrowType(Qt.RightArrow)
        self._details_btn.setCheckable(True)
        self._details_btn.toggled.connect(self._toggle_details)
        lay.addWidget(self._details_btn, 0, Qt.AlignLeft)
        self._diagnostics = _Reader(self._page)
        self._diagnostics.setObjectName("biliDiagnostics")
        self._diagnostics.setFixedHeight(144)
        self._diagnostics.hide()
        lay.addWidget(self._diagnostics)
        self._update_layout(self.width())
        self._apply_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_layout(event.size().width())

    def _update_layout(self, width: int):
        columns = 2 if width < 680 else 4
        if columns != self._summary_columns:
            while self._summary_grid.count():
                self._summary_grid.takeAt(0)
            for column in range(4):
                self._summary_grid.setColumnStretch(column, 0)
            for index, box in enumerate(self._metric_cards):
                self._summary_grid.addWidget(box, index // columns, index % columns)
            for column in range(columns):
                self._summary_grid.setColumnStretch(column, 1)
            self._summary_columns = columns
        narrow = width < 900
        self._body_layout.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
        self._report_panel.setMinimumHeight(260 if narrow else 330)
        self._seen_panel.setMinimumHeight(230 if narrow else 330)

    def _toggle_details(self, checked: bool):
        self._diagnostics.setVisible(checked)
        self._details_btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    # ── 数据加载 ────────────────────────────────────────

    def _async_load(self):
        if self._thread is not None or self._round_running:
            return
        self._refresh_btn.setEnabled(False)
        self._run_btn.setEnabled(False)
        self._hint_lb.setText("正在刷新状态与日报…")
        self._start_worker(self._load_snapshot)

    def _load_snapshot(self) -> dict:
        from biliscroll_core.diagnostics import collect_status
        from biliscroll_core.store import DutyStore

        status = collect_status()
        report = ""
        store = DutyStore()
        path = store.report_path()
        if path.is_file():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            report = "\n".join(lines[-80:])
        return {"status": status, "report": report, "report_path": str(path),
                "seen_rows": store.seen_recent(limit=12)}

    def _render_snapshot(self, snap: dict):
        status: dict = snap.get("status", {})
        credential = str(status.get("扫码凭证", ""))
        if credential.startswith("已存在"):
            credential_text = "已保存"
        elif credential.startswith("不存在"):
            credential_text = "未登录"
        elif credential:
            credential_text = "需重新登录"
        else:
            credential_text = "未知"
        comment = str(status.get("自动评论", ""))
        schedule = str(status.get("自动跑", ""))
        values = {
            "quota": str(status.get("今日已挑/配额", "—")),
            "credential": credential_text,
            "schedule": "仅手动" if schedule.startswith("关") else schedule.replace(" ", " · ") or "—",
            "comment": "已开启" if comment.startswith("开") else "已关闭" if comment == "关" else "—",
        }
        for key, text in values.items():
            self._metric_values[key].setText(text)
            self._metric_values[key].setToolTip(text)
        self._metric_values["credential"].setToolTip(f"{credential or '未读取到凭证信息'}；未校验登录有效性")
        self._metric_values["comment"].setToolTip(comment or "未读取到评论设置")
        report = snap.get("report") or ""
        self._report_view.setMarkdown(report)
        self._report_stack.setCurrentIndex(1 if report.strip() else 0)
        self._seen_rows = snap.get("seen_rows") or []
        self._render_seen()
        self._diagnostics.setPlainText("\n\n".join(
            f"{key}：{value}" for key, value in status.items() if key != "最近判重"
        ) or "暂未读取到环境信息")
        self._hint_lb.setText(f"{dt.datetime.now():%H:%M} 已更新 · 设置：插件 → bili-scroll")
        self._refresh_btn.setEnabled(True)
        self._run_btn.setEnabled(not self._round_running)

    def _render_seen(self):
        rows = []
        for row in self._seen_rows:
            title = escape(str(row.get("title") or "未命名视频"))
            bvid = str(row.get("bvid") or "")
            if re.fullmatch(r"BV[A-Za-z0-9]+", bvid):
                title = f'<a href="https://www.bilibili.com/video/{bvid}">{title}</a>'
            meta = " · ".join(str(row.get(k) or "") for k in ("up", "date") if row.get(k))
            state = escape(str(row.get("status") or "已处理"))
            rows.append(
                f'<p style="margin-top:14px; margin-bottom:5px; font-weight:600;">{title}</p>'
                f'<p style="font-size:12px; color:{self._secondary_color};">'
                f'{state} &nbsp;·&nbsp; {escape(meta)}<br>{escape(bvid)}</p>'
            )
        self._seen_view.setHtml("".join(rows))
        self._seen_stack.setCurrentIndex(1 if rows else 0)
        self._seen_meta.setText(f"{len(rows)} 条记录")

    # ── 业务动作保持原入口 ──────────────────────────────

    def _on_run_round(self):
        if self._round_running or self._thread is not None:
            return
        self._round_running = True
        self._run_btn.setText("值班中…")
        self._run_btn.setEnabled(False)
        self._refresh_btn.setEnabled(False)
        self._hint_lb.setText("正在搜视频、读字幕并整理日报，约 5–20 分钟，完成后会通知你")
        self._start_worker(self._run_round, self._render_round)

    def _run_round(self) -> dict:
        from biliscroll_core.round_runner import run_duty_round

        try:
            return {"round": run_duty_round()}
        except Exception as e:
            return {"round": {"status": "error", "error": f"{type(e).__name__}: {e}", "text": ""}}

    def _render_round(self, snap: dict):
        self._round_running = False
        self._run_btn.setText("跑一轮")
        self._run_btn.setEnabled(True)
        self._refresh_btn.setEnabled(True)
        result = snap.get("round", {})
        status = result.get("status")
        if status == "success":
            self._async_load()
        elif status == "busy":
            self._hint_lb.setText("已有一轮值班在运行，完成后会通知你；可稍后刷新查看日报")
        else:
            self._hint_lb.setText(f"值班轮未完成：{result.get('error') or status}")

    def _open_data_dir(self):
        try:
            from biliscroll_core.paths import plugin_data_root

            root = plugin_data_root()
            if root is None:
                return
            if sys.platform == "win32":
                os_startfile = __import__("os").startfile  # noqa: S310 - 用户主动点开自己的数据目录
                os_startfile(str(root))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(root)])
            else:
                subprocess.Popen(["xdg-open", str(root)])
        except Exception as e:
            logger.warning(f"[bili-scroll] 打开数据目录失败: {e}")

    def _on_close(self):
        self.closed.emit()

    # ── 线程基建（模板协议） ────────────────────────────

    def _start_worker(self, fn: Callable, render: Callable = None):
        self._worker = _Worker(fn)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._pending_render = render
        self._thread.start()

    def _on_worker_done(self, result: Any):
        render = getattr(self, "_pending_render", None) or self._render_snapshot
        self._cleanup_worker()
        try:
            render(result)
        except Exception as e:
            logger.exception(f"[bili-scroll] 渲染失败: {e}")
            self._on_worker_error(f"内容显示失败：{e}")

    def _on_worker_error(self, err: str):
        logger.error(f"[bili-scroll] 卡片加载失败: {err}")
        self._refresh_btn.setEnabled(True)
        self._round_running = False
        self._run_btn.setText("跑一轮")
        self._run_btn.setEnabled(True)
        self._hint_lb.setText(f"读取或执行失败：{err.splitlines()[0] if err else '未知错误'}")
        self._cleanup_worker()

    def _cleanup_worker(self):
        if self._thread is not None:
            try:
                self._thread.quit()
                self._thread.wait(500)
            except RuntimeError:
                pass
            self._thread = None
        self._worker = None

    def deleteLater(self):
        self._cleanup_worker()
        super().deleteLater()
