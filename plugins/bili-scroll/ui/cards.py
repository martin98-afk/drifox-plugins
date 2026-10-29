# -*- coding: utf-8 -*-
"""B站值班 浮动卡（container=full）：状态 / 跑一轮 / 日报预览 / 最近判重。

magpie 坑清单遵守：show_card 自带 setVisible(True)；纯 Qt 控件无 Chromium
懒构造问题；UI 注册期 preheat dispatcher（见 ui/__init__.py）。
"""
from __future__ import annotations

import subprocess
import sys
import traceback
from typing import Any, Callable, Optional

from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from loguru import logger
from qfluentwidgets import (
    FluentIcon,
    PrimaryPushButton,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
)


def _text_color(secondary: bool = False) -> str:
    if isDarkTheme():
        return "rgba(255,255,255,0.55)" if secondary else "rgba(255,255,255,0.9)"
    return "rgba(0,0,0,0.45)" if secondary else "rgba(0,0,0,0.85)"


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
    """B站值班 卡片。"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._round_running = False
        self._setup_ui()

    # ── 上下文与生命周期 ────────────────────────────────

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        """容器统一藏卡，显示必须自带 setVisible(True)（magpie 教训）。"""
        self._apply_theme()
        self._async_load()
        self.setVisible(True)

    def _apply_theme(self):
        tc = _text_color()
        tcs = _text_color(secondary=True)
        self.setFont(QFont("Microsoft YaHei", 14))
        self._title_lb.setStyleSheet(f"color: {tc}; font-size: 18px; font-weight: 600;")
        for lb in self._status_lb, self._report_title:
            lb.setStyleSheet(f"color: {tc};")
        self._hint_lb.setStyleSheet(f"color: {tcs}; font-size: 12px;")
        border = "rgba(255,255,255,0.12)" if isDarkTheme() else "rgba(0,0,0,0.10)"
        for edit in self._report_view, self._seen_view:
            edit.setStyleSheet(
                f"QPlainTextEdit {{ background: transparent; color: {tc}; border: 1px solid {border};"
                f" border-radius: 6px; padding: 6px; }}"
            )

    # ── UI 构建 ─────────────────────────────────────────

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(10)

        header = QHBoxLayout()
        self._title_lb = StrongBodyLabel("B站值班", self)
        self._title_lb.setStyleSheet("font-size: 18px; font-weight: 600;")
        header.addWidget(self._title_lb)
        header.addStretch(1)
        self._refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self._refresh_btn.setToolTip("刷新状态与日报")
        self._refresh_btn.clicked.connect(self._async_load)
        header.addWidget(self._refresh_btn)
        self._close_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        self._close_btn.clicked.connect(self._on_close)
        header.addWidget(self._close_btn)
        lay.addLayout(header)

        self._status_lb = QLabel("读取中…", self)
        self._status_lb.setTextFormat(Qt.RichText)
        self._status_lb.setWordWrap(True)
        self._status_lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self._status_lb)

        btn_row = QHBoxLayout()
        self._run_btn = PrimaryPushButton("▶ 跑一轮", self)
        self._run_btn.setToolTip("后台跑一轮值班：搜视频→读字幕→写日报（约 5-20 分钟）")
        self._run_btn.clicked.connect(self._on_run_round)
        btn_row.addWidget(self._run_btn)
        self._open_btn = TransparentToolButton(FluentIcon.FOLDER, self)
        self._open_btn.setToolTip("打开值班数据目录（日报/判重表/归档）")
        self._open_btn.clicked.connect(self._open_data_dir)
        btn_row.addWidget(self._open_btn)
        btn_row.addStretch(1)
        self._hint_lb = QLabel("设置（关键词/峰谷/评论）在 设置→插件→bili-scroll 的配置卡里改", self)
        self._hint_lb.setWordWrap(True)
        btn_row.addWidget(self._hint_lb)
        lay.addLayout(btn_row)

        sep1 = QFrame(self)
        sep1.setFrameShape(QFrame.HLine)
        lay.addWidget(sep1)

        self._report_title = StrongBodyLabel("今日日报", self)
        lay.addWidget(self._report_title)
        self._report_view = QPlainTextEdit(self)
        self._report_view.setReadOnly(True)
        self._report_view.setMinimumHeight(180)
        lay.addWidget(self._report_view, 3)

        self._seen_title = StrongBodyLabel("它刷过的视频（最近判重）", self)
        lay.addWidget(self._seen_title)
        self._seen_view = QPlainTextEdit(self)
        self._seen_view.setReadOnly(True)
        self._seen_view.setMinimumHeight(120)
        lay.addWidget(self._seen_view, 2)

        self._apply_theme()

    # ── 数据加载 ────────────────────────────────────────

    def _async_load(self):
        if self._thread is not None:
            return
        self._refresh_btn.setEnabled(False)
        self._status_lb.setText("读取中…")
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
        seen_rows = store.seen_recent(limit=12)
        return {"status": status, "report": report, "report_path": str(path),
                "seen_rows": seen_rows}

    def _render_snapshot(self, snap: dict):
        status: dict = snap.get("status", {})
        rows = "".join(
            f"<div style='margin:2px 0;'>• <b>{k}</b>：{v}</div>" for k, v in status.items()
        )
        self._status_lb.setText(rows or "（无）")
        report = snap.get("report") or "今天还没有日报 —— 点「▶ 跑一轮」开一轮，或在对话里喊 bili_duty_run。"
        self._report_view.setPlainText(report)
        seen_lines = []
        for r in snap.get("seen_rows", []):
            seen_lines.append(
                f"{r.get('date', '')}  [{r.get('status', '')}]  {r.get('title', '')}（{r.get('up', '')}）{r.get('bvid', '')}"
            )
        self._seen_view.setPlainText("\n".join(seen_lines) or "（判重表还是空的）")
        self._refresh_btn.setEnabled(True)

    # ── 跑一轮 ──────────────────────────────────────────

    def _on_run_round(self):
        if self._round_running:
            return
        self._round_running = True
        self._run_btn.setText("值班中…（约 5-20 分钟，完成弹通知）")
        self._run_btn.setEnabled(False)
        self._start_worker(self._run_round)

    def _run_round(self) -> dict:
        from biliscroll_core.round_runner import run_duty_round

        try:
            return {"round": run_duty_round()}
        except Exception as e:
            return {"round": {"status": "error", "error": f"{type(e).__name__}: {e}", "text": ""}}

    def _render_round(self, snap: dict):
        self._round_running = False
        self._run_btn.setText("▶ 跑一轮")
        self._run_btn.setEnabled(True)
        result = snap.get("round", {})
        status = result.get("status")
        if status == "busy":
            self._hint_lb.setText("已有一轮值班在跑（工具或另一张卡触发的），完成会弹通知")
        elif status != "success":
            self._hint_lb.setText(f"值班轮未完成：{result.get('error') or status}")
        else:
            self._hint_lb.setText("上一轮已完成 ✓")
        self._async_load()

    # ── 其他动作 ────────────────────────────────────────

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
        self._thread.start()
        self._pending_render = render

    def _on_worker_done(self, result: Any):
        render = getattr(self, "_pending_render", None) or self._render_snapshot
        self._cleanup_worker()
        try:
            render(result)
        except Exception as e:
            logger.exception(f"[bili-scroll] 渲染失败: {e}")

    def _on_worker_error(self, err: str):
        logger.error(f"[bili-scroll] 卡片加载失败: {err}")
        self._refresh_btn.setEnabled(True)
        self._round_running = False
        self._run_btn.setText("▶ 跑一轮")
        self._run_btn.setEnabled(True)
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
