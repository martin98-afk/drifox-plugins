# -*- coding: utf-8 -*-
"""taskboard 任务卡 widget — 单张任务在列内的展示与操作

- 标题 / 摘要 / 错误行 / 处理中动画
- 操作按钮：开始 / 停止 / 前移 / 后移 / 报告 / 删除
- 支持拖拽（按下空白处拖动，QDrag 携带 task_id）
"""

import time
from typing import Optional

from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QDrag, QEnterEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from qfluentwidgets import FluentIcon as FIF, StrongBodyLabel, TransparentToolButton
from qfluentwidgets.components.widgets.progress_ring import IndeterminateProgressRing

from app.utils.design_tokens import Colors, scale_font_size
from app.utils.utils import get_font_family_css

from taskboard_core.config import COLUMNS, COLUMN_META, next_column, prev_column

FONT_CSS = get_font_family_css()
MIME_TASK_ID = "application/x-taskboard-task-id"


class TaskCardWidget(QFrame):
    """单张任务卡"""

    # 交互请求（由看板卡接线到 controller）
    startRequested = Signal(str)    # task_id
    stopRequested = Signal(str)
    removeRequested = Signal(str)
    moveRequested = Signal(str, str)  # (task_id, 目标列)
    reportRequested = Signal(str)
    detailRequested = Signal(str)

    def __init__(self, task_id: str, parent=None):
        super().__init__(parent)
        self._task_id = task_id
        self._processing = False
        self._drag_start: Optional[QPoint] = None
        self._last_task = None  # 最近一次 refresh 的任务引用（处理中自刷新用）

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(2000)
        self._tick_timer.timeout.connect(self._on_tick)

        self.setObjectName("taskboardTaskCard")
        self.setFrameShape(QFrame.NoFrame)

        # ── 布局 ──
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)

        # 行 1：状态点 + 标题 + 相对时间
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._dot = QFrame()
        self._dot.setFixedSize(8, 8)
        self._dot.setStyleSheet("border-radius: 4px;")
        self._title_label = StrongBodyLabel("")
        self._title_label.setWordWrap(True)
        self._time_label = QLabel("")
        self._busy_ring = IndeterminateProgressRing()
        self._busy_ring.setFixedSize(16, 16)
        self._busy_ring.hide()
        title_row.addWidget(self._dot)
        title_row.addWidget(self._title_label, 1)
        title_row.addWidget(self._busy_ring)
        title_row.addWidget(self._time_label)
        root.addLayout(title_row)

        # 行 2：摘要 / 流式预览（共用 label，处理中显示预览）
        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._summary_label)

        # 行 3：元信息（@agent · 链N · N轮 · 耗时）
        self._meta_label = QLabel("")
        root.addWidget(self._meta_label)

        # 行 4：错误条
        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        root.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)

        def _mkbtn(icon, tip: str) -> TransparentToolButton:
            b = TransparentToolButton(icon)
            b.setToolTip(tip)
            b.setFixedSize(28, 28)
            return b

        self._start_btn = _mkbtn(FIF.PLAY_SOLID, "开始处理（当前列智能体）")
        self._stop_btn = _mkbtn(FIF.PAUSE_BOLD, "停止处理")
        # _prev_btn 在 inprogress/review 列是「打回上一列（重做）」，其他列是「移到上一列」
        self._prev_btn = _mkbtn(FIF.RETURN, "移到上一列")
        self._next_btn = _mkbtn(FIF.RIGHT_ARROW, "移到下一列")
        self._report_btn = _mkbtn(FIF.DOCUMENT, "查看任务报告")
        self._delete_btn = _mkbtn(FIF.DELETE, "删除任务")
        for b in (self._start_btn, self._stop_btn, self._prev_btn, self._next_btn,
                  self._report_btn, self._delete_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        # ── 信号 ──
        self._start_btn.clicked.connect(lambda: self.startRequested.emit(self._task_id))
        self._stop_btn.clicked.connect(lambda: self.stopRequested.emit(self._task_id))
        self._delete_btn.clicked.connect(lambda: self.removeRequested.emit(self._task_id))
        self._report_btn.clicked.connect(lambda: self.reportRequested.emit(self._task_id))
        self._prev_btn.clicked.connect(lambda: self.moveRequested.emit(self._task_id, prev_column(self._status)))
        self._next_btn.clicked.connect(lambda: self.moveRequested.emit(self._task_id, next_column(self._status)))

        self._status = "todo"
        self._accent = COLUMN_META["todo"]["accent"]
        self._refresh_style()

    # ================================================================
    #  数据刷新（看板卡驱动）
    # ================================================================

    @property
    def task_id(self) -> str:
        return self._task_id

    def refresh(self, task, processing: bool) -> None:
        """按最新任务数据刷新展示"""
        self._last_task = task
        self._status = task.status if task.status in COLUMNS else "todo"
        self._accent = COLUMN_META.get(self._status, {}).get("accent", "#8A8F98")
        self._processing = bool(processing)

        self._title_label.setText(task.title)
        self._time_label.setText(_rel_time(task.updated_at))

        if self._processing:
            preview = task.stream_preview or ""
            self._summary_label.setText(preview[-200:] if preview else "正在思考…")
            rounds = task.tool_rounds
            elapsed = int(time.time() - (task.started_at or time.time()))
            mode = COLUMN_META.get(self._status, {}).get("mode", "处理")
            rounds_txt = f"{rounds} 轮工具" if rounds else "评估中"
            meta = (f"@{COLUMN_META[self._status]['agent']} · {mode} · {rounds_txt} · "
                    f"{elapsed // 60}:{elapsed % 60:02d}")
        else:
            self._summary_label.setText(task.last_summary or task.detail or "等待处理")
            chain = len(task.context_log)
            mode = COLUMN_META.get(self._status, {}).get("mode", "")
            meta = f"@{COLUMN_META[self._status]['agent']} · {mode} · 链 {chain}"
        self._meta_label.setText(meta)

        if task.error:
            self._error_label.setText(task.error)
            self._error_label.show()
        else:
            self._error_label.hide()

        # 按钮可见性
        self._start_btn.setVisible(not self._processing)
        self._stop_btn.setVisible(self._processing)
        # inprogress/review 列的「上一列」是真正的"打回重做"，仅这两列显示 prev 按钮
        self._prev_btn.setVisible(self._status in ("inprogress", "review") and not self._processing)
        self._prev_btn.setToolTip("打回上一列（重做）")
        self._next_btn.setEnabled(not self._processing and self._status != COLUMNS[-1])
        has_report = self._status == "done" and bool(task.last_summary)
        self._report_btn.setVisible(has_report)

        self._busy_ring.setVisible(self._processing)
        if self._processing:
            self._tick_timer.start()
        else:
            self._tick_timer.stop()

        self._refresh_style()
        # done 列淡化（用颜色而非 opacity）
        title_color = Colors.TEXT_SECONDARY if self._status == "done" else Colors.TEXT_PRIMARY
        self._title_label.setStyleSheet(
            f"color: {title_color}; {FONT_CSS} font-size: {scale_font_size(13)}px;"
        )

    def _on_tick(self):
        """处理中每 2s 自刷新耗时/轮次/预览 — 仅更新元信息行与预览，避免全量 refresh

        controller 已按信号（task_changed）驱动标题/错误等刷新；这里只做耗时累计，
        消除双路径全量刷新与 _last_task 陈旧引用的整体重绘风险。
        """
        if not (self._processing and self._last_task is not None):
            return
        task = self._last_task
        preview = task.stream_preview or ""
        if preview:
            self._summary_label.setText(preview[-200:])
        elapsed = int(time.time() - (task.started_at or time.time()))
        meta = (f"@{COLUMN_META[self._status]['agent']} · {task.tool_rounds} 轮工具 · "
                f"{elapsed // 60}:{elapsed % 60:02d}")
        self._meta_label.setText(meta)

    # ================================================================
    #  拖拽（按住卡片空白处拖动 → 列间移动）
    # ================================================================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.detailRequested.emit(self._task_id)
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start and not self._processing:
            if (event.pos() - self._drag_start).manhattanLength() > 12:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(MIME_TASK_ID)
                mime.setData(MIME_TASK_ID, self._task_id.encode("utf-8"))
                drag.setMimeData(mime)
                drag.exec(Qt.MoveAction)
                self._drag_start = None
                return
        super().mouseMoveEvent(event)

    def enterEvent(self, event: QEnterEvent):
        self._refresh_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._refresh_style()
        super().leaveEvent(event)

    # ================================================================
    #  样式
    # ================================================================

    def _refresh_style(self, hover: bool = False):
        Colors.refresh()
        accent = self._accent
        if self._processing:
            border = f"1.5px solid {accent}"
        elif hover:
            border = f"1px solid {accent}"
        else:
            border = f"1px solid {Colors.BORDER}"
        # 半透明磨砂：rgba 白底叠加 + 顶到底微渐变，hover 提高透明度，
        # 让卡片透出列底色与主背景，与列容器保持一致的毛玻璃层次
        # （之前用 Colors.CARD_BG_SOLID 实色，卡片挡住列的磨砂效果看起来像白块）
        if hover:
            bg_top, bg_bottom = "rgba(255, 255, 255, 0.08)", "rgba(255, 255, 255, 0.12)"
        else:
            bg_top, bg_bottom = "rgba(255, 255, 255, 0.02)", "rgba(255, 255, 255, 0.06)"
        self.setStyleSheet(f"""
            #taskboardTaskCard {{
                background-color: rgba(255, 255, 255, 0.06);
                background-image: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {bg_top},
                    stop:1 {bg_bottom}
                );
                border: {border};
                border-radius: 8px;
            }}
        """)
        self._title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; {FONT_CSS} font-size: {scale_font_size(13)}px;"
        )
        self._summary_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; {FONT_CSS} font-size: {scale_font_size(11)}px;"
        )
        self._meta_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; {FONT_CSS} font-size: {scale_font_size(10)}px;"
        )
        self._error_label.setStyleSheet(
            f"background: rgba(239, 68, 68, 0.15); color: {Colors.ERROR};"
            f"border-radius: 4px; padding: 4px 6px; {FONT_CSS}"
            f"font-size: {scale_font_size(10)}px;"
        )
        self._dot.setStyleSheet(
            f"background: {accent}; border-radius: 4px; border: none;"
        )
        self._time_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none; {FONT_CSS}"
            f"font-size: {scale_font_size(10)}px;"
        )


def _rel_time(ts: str) -> str:
    """'2026-08-21 18:31:02' → '3m' / '2h' / '5d'；解析失败返回空"""
    try:
        from datetime import datetime

        t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        delta = (datetime.now() - t).total_seconds()
        if delta < 60:
            return "now"
        if delta < 3600:
            return f"{int(delta // 60)}m"
        if delta < 86400:
            return f"{int(delta // 3600)}h"
        return f"{int(delta // 86400)}d"
    except Exception:
        return ""
