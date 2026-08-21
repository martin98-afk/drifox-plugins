# -*- coding: utf-8 -*-
"""taskboard 任务卡 widget — 单张任务在列内的展示与操作

- 标题 / 摘要 / 错误行 / 处理中动画
- 操作按钮：开始 / 停止 / 前移 / 后移 / 报告 / 删除
- 支持拖拽（按下空白处拖动，QDrag 携带 task_id）
"""

from typing import Optional

from PyQt5.QtCore import QMimeData, QPoint, Qt, pyqtSignal
from PyQt5.QtGui import QDrag, QEnterEvent
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

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
    startRequested = pyqtSignal(str)    # task_id
    stopRequested = pyqtSignal(str)
    removeRequested = pyqtSignal(str)
    moveRequested = pyqtSignal(str, str)  # (task_id, 目标列)
    reportRequested = pyqtSignal(str)

    def __init__(self, task_id: str, parent=None):
        super().__init__(parent)
        self._task_id = task_id
        self._processing = False
        self._drag_start: Optional[QPoint] = None

        self.setObjectName("taskboardTaskCard")
        self.setFrameShape(QFrame.NoFrame)

        # ── 布局 ──
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._busy_ring = IndeterminateProgressRing()
        self._busy_ring.setFixedSize(16, 16)
        self._busy_ring.hide()
        self._title_label = StrongBodyLabel("")
        self._title_label.setWordWrap(True)
        title_row.addWidget(self._busy_ring)
        title_row.addWidget(self._title_label, 1)
        root.addLayout(title_row)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        root.addWidget(self._summary_label)

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
        self._status = task.status if task.status in COLUMNS else "todo"
        self._accent = COLUMN_META.get(self._status, {}).get("accent", "#8A8F98")
        self._processing = bool(processing)

        self._title_label.setText(task.title)
        if self._processing:
            stream = getattr(task, "_stream_preview", "") or ""
            summary = f"⏳ {stream}" if stream else (task.last_summary or "处理中…")
        else:
            summary = task.last_summary or task.detail or "等待处理"
        self._summary_label.setText(summary if len(summary) <= 140 else summary[:140] + "…")

        if task.error:
            self._error_label.setText(f"⚠ {task.error}")
            self._error_label.show()
        else:
            self._error_label.hide()

        # 按钮可见性
        self._start_btn.setVisible(not self._processing)
        self._stop_btn.setVisible(self._processing)
        self._prev_btn.setEnabled(not self._processing and self._status != COLUMNS[0])
        self._next_btn.setEnabled(not self._processing and self._status != COLUMNS[-1])
        has_report = self._status == "done" and bool(task.last_summary)
        self._report_btn.setVisible(has_report)

        self._busy_ring.setVisible(self._processing)

        self._refresh_style()

    # ================================================================
    #  拖拽（按住卡片空白处拖动 → 列间移动）
    # ================================================================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start and not self._processing:
            if (event.pos() - self._drag_start).manhattanLength() > 12:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(MIME_TASK_ID)
                mime.setData(MIME_TASK_ID, self._task_id.encode("utf-8"))
                drag.setMimeData(mime)
                drag.exec_(Qt.MoveAction)
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
        else:
            border = f"1px solid {Colors.BORDER}"
        bg = Colors.CARD_BG_SOLID if not hover else "rgba(60, 60, 68, 250)"
        self.setStyleSheet(f"""
            #taskboardTaskCard {{
                background: {bg};
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
        self._error_label.setStyleSheet(
            f"color: {Colors.ERROR}; {FONT_CSS} font-size: {scale_font_size(11)}px;"
        )
