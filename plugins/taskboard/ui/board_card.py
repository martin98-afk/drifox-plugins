# -*- coding: utf-8 -*-
"""taskboard 看板主卡 — 四列任务看板（todo/inprogress/review/done）

container="right" 停靠（与浏览器卡同容器互斥：打开看板即替换浏览器插槽）。
订阅 TaskBoardController 广播信号实时刷新；任务卡支持按钮与拖拽移动。
"""

from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    FluentIcon as FIF,
    IconWidget,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SwitchButton,
    TextEdit,
    TransparentToolButton,
)

from app.utils.design_tokens import Colors, scale_font_size
from app.utils.utils import get_font_family_css

from taskboard_core.config import COLUMNS, COLUMN_META
from taskboard_core.models import Task

from .task_card import MIME_TASK_ID, TaskCardWidget

FONT_CSS = get_font_family_css()


# ============================================================
#  发布任务对话框
# ============================================================


class TaskDialog(QDialog):
    """发布新任务（标题 + 描述）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("发布任务")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(BodyLabel("任务标题（必填，将进入待办列）"))
        self.title_edit = LineEdit(self)
        self.title_edit.setPlaceholderText("例如：为用户模块添加登录限流")
        layout.addWidget(self.title_edit)

        layout.addWidget(BodyLabel("任务描述（可选，供智能体理解任务）"))
        self.detail_edit = TextEdit(self)
        self.detail_edit.setPlaceholderText("背景、验收标准、涉及文件……")
        self.detail_edit.setFixedHeight(120)
        layout.addWidget(self.detail_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = PushButton("取消", self)
        ok_btn = PrimaryPushButton("发布", self)
        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        self._refresh_style()
        self.title_edit.setFocus()

    def _on_ok(self):
        if self.title_edit.text().strip():
            self.accept()

    def get_task(self):
        return self.title_edit.text().strip(), self.detail_edit.toPlainText().strip()

    def _refresh_style(self):
        Colors.refresh()
        self.setStyleSheet(f"""
            QDialog {{ background: {Colors.CONTENT_BG}; {FONT_CSS} }}
            BodyLabel {{ color: {Colors.TEXT_SECONDARY}; {FONT_CSS}
                         font-size: {scale_font_size(12)}px; }}
        """)


# ============================================================
#  报告查看对话框
# ============================================================


class ReportDialog(QDialog):
    """查看 done 任务报告（只读）"""

    def __init__(self, title: str, report: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"任务报告 — {title}")
        self.setModal(True)
        self.resize(560, 480)

        layout = QVBoxLayout(self)
        self.view = QTextEdit(self)
        self.view.setReadOnly(True)
        self.view.setPlainText(report or "（暂无报告：任务尚未经完成列智能体归档）")
        layout.addWidget(self.view)

        close_btn = PrimaryPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

        Colors.refresh()
        self.setStyleSheet(f"""
            QDialog {{ background: {Colors.CONTENT_BG}; }}
            QTextEdit {{ background: {Colors.CARD_BG_SOLID}; color: {Colors.TEXT_PRIMARY};
                         border: 1px solid {Colors.BORDER}; border-radius: 8px;
                         padding: 10px; {FONT_CSS} font-size: {scale_font_size(12)}px; }}
        """)


# ============================================================
#  任务详情对话框
# ============================================================


class TaskDetailDialog(QDialog):
    """任务详情 — 描述 / 上下文链 / 流转历史 / 错误 / 报告"""

    def __init__(self, task, report: str, processing: bool, preview: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"任务详情 — {task.title}")
        self.setModal(True)
        self.resize(600, 520)

        layout = QVBoxLayout(self)
        self.view = QTextEdit(self)
        self.view.setReadOnly(True)
        self.view.setPlainText(self._render(task, report, processing, preview))
        layout.addWidget(self.view)

        close_btn = PrimaryPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

        Colors.refresh()
        self.setStyleSheet(f"""
            QDialog {{ background: {Colors.CONTENT_BG}; }}
            QTextEdit {{ background: {Colors.CARD_BG_SOLID}; color: {Colors.TEXT_PRIMARY};
                         border: 1px solid {Colors.BORDER}; border-radius: 8px;
                         padding: 10px; {FONT_CSS} font-size: {scale_font_size(12)}px; }}
        """)

    @staticmethod
    def _render(task, report: str, processing: bool, preview: str) -> str:
        from taskboard_core.config import COLUMN_META

        parts = [f"# {task.title}", ""]
        parts += [f"状态：{COLUMN_META.get(task.status, {}).get('title', task.status)}"
                  f"　|　创建：{task.created_at}　|　更新：{task.updated_at}", ""]
        if processing:
            parts += ["## 处理中（实时预览）", preview or "正在思考…", ""]
        if task.detail:
            parts += ["## 任务描述", task.detail, ""]
        if task.context_log:
            parts += ["## 处理链（各列智能体结论）"]
            for rec in task.context_log:
                col = COLUMN_META.get(rec.get("column", ""), {}).get("title", rec.get("column", ""))
                parts.append(f"- [{col} / @{rec.get('agent', '')}]（{rec.get('at', '')}）")
                parts.append(f"  {rec.get('summary', '')}")
            parts.append("")
        if task.history:
            parts += ["## 流转历史"]
            for h in task.history:
                src = COLUMN_META.get(h.get("from", ""), {}).get("title", h.get("from") or "—")
                dst = COLUMN_META.get(h.get("to", ""), {}).get("title", h.get("to", ""))
                parts.append(f"- {src} → {dst}（{h.get('at', '')}，by {h.get('by', '')}）")
            parts.append("")
        if task.error:
            parts += ["## 错误", task.error, ""]
        if report:
            parts += ["## 归档报告", report]
        return "\n".join(parts)


# ============================================================
#  看板列
# ============================================================


class BoardColumn(QFrame):
    """看板单列 — 列头 + 竖向滚动任务列表 + 拖拽接收区"""

    dropRequested = pyqtSignal(str, str)  # (task_id, 本列状态)

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self._status = status
        meta = COLUMN_META[status]
        self._accent = meta["accent"]
        self.setObjectName(f"taskboardColumn_{status}")
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 8, 6, 8)
        root.setSpacing(6)

        # 列头：色点 + 标题 + 计数 + 智能体名
        head = QHBoxLayout()
        head.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {self._accent}; font-size: {scale_font_size(11)}px; border: none;")
        self._title_label = StrongBodyLabel(meta["title"])
        self._count_label = QLabel("0")
        self._count_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none; {FONT_CSS} font-size: {scale_font_size(11)}px;"
        )
        head.addWidget(dot)
        head.addWidget(self._title_label)
        head.addStretch(1)
        head.addWidget(self._count_label)
        root.addLayout(head)

        self._agent_label = QLabel(f"@{meta['agent']}")
        self._agent_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none; {FONT_CSS} font-size: {scale_font_size(10)}px;"
        )
        root.addWidget(self._agent_label)

        # 任务滚动区
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._host = QWidget()
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(6)
        self._list.addStretch(1)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, 1)

        self._refresh_style()

    @property
    def status(self) -> str:
        return self._status

    def clear_cards(self) -> None:
        while self._list.count() > 1:  # 保留末尾 stretch
            item = self._list.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def add_card(self, card: TaskCardWidget) -> None:
        self._list.insertWidget(self._list.count() - 1, card)

    def set_count(self, n: int, processing: int = 0) -> None:
        text = str(n)
        if processing:
            text += f"（{processing} 处理中）"
        self._count_label.setText(text)

    # ── 拖拽接收 ──

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat(MIME_TASK_ID):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_TASK_ID):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        task_id = bytes(event.mimeData().data(MIME_TASK_ID)).decode("utf-8", errors="ignore")
        if task_id:
            self.dropRequested.emit(task_id, self._status)
            event.acceptProposedAction()

    def _refresh_style(self):
        Colors.refresh()
        self.setStyleSheet(f"""
            #{self.objectName()} {{
                background: {Colors.CARD_BG_DIM};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
            }}
            QScrollArea {{ background: transparent; border: none; }}
            QWidget#taskboardColumnHost {{ background: transparent; }}
        """)
        self._title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none; {FONT_CSS} font-size: {scale_font_size(12)}px;"
        )


# ============================================================
#  看板主卡
# ============================================================


class TaskBoardCard(QFrame):
    """任务看板主卡 — 注册为 right 容器浮动卡（替换插槽）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("taskboardCard")
        self._ctx_provider = None
        self._last_ctx: Dict[str, Any] = {}
        self._columns: Dict[str, BoardColumn] = {}
        self._cards: Dict[str, TaskCardWidget] = {}
        self._bound = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        title_icon = IconWidget(FIF.VIEW)
        toolbar.addWidget(title_icon)
        title = StrongBodyLabel("任务看板")
        toolbar.addWidget(title)

        self._auto_switch = SwitchButton()
        self._auto_switch.setOnText("自动流转")
        self._auto_switch.setOffText("手动触发")
        self._auto_switch.setToolTip(
            "自动：任务状态变化后立即由该列智能体处理\n手动：全部由用户点击 ▶ 决定开始"
        )
        toolbar.addWidget(self._auto_switch)
        toolbar.addStretch(1)

        self._add_btn = PrimaryPushButton(FIF.ADD, "发布任务")
        self._add_btn.setToolTip("发布新任务到待办列")
        toolbar.addWidget(self._add_btn)

        self._clear_btn = TransparentToolButton()
        self._clear_btn.setIcon(FIF.BROOM.qicon())
        self._clear_btn.setToolTip("清空完成列")
        self._clear_btn.setFixedSize(30, 30)
        toolbar.addWidget(self._clear_btn)
        root.addLayout(toolbar)

        # ── 环境信息栏（模型 · 工作路径）──
        env_row = QHBoxLayout()
        env_row.setSpacing(8)
        self._model_label = QLabel("")
        self._model_label.setToolTip("任务处理使用的模型（跟随当前窗口模型选择）")
        self._workdir_label = QLabel("")
        self._workdir_label.setToolTip("看板数据目录（board.json / reports / logs 所在工作目录）")
        env_row.addWidget(self._model_label)
        env_row.addStretch(1)
        env_row.addWidget(self._workdir_label)
        root.addLayout(env_row)

        hint = QLabel("拖拽或 ←→ 移动任务 · ▶ 触发处理 · 智能体结论决定去留")
        hint.setWordWrap(True)
        self._hint_label = hint
        root.addWidget(hint)

        # ── 四列 ──
        columns_row = QHBoxLayout()
        columns_row.setSpacing(8)
        for status in COLUMNS:
            col = BoardColumn(status, self)
            self._columns[status] = col
            col.dropRequested.connect(self._on_move_request)
            columns_row.addWidget(col, 1)
        root.addLayout(columns_row, 1)

        # ── 接线（controller 单例）──
        from .controller import TaskBoardController

        self._controller = TaskBoardController.get_instance()
        self._auto_switch.checkedChanged.connect(self._on_auto_switch)
        self._add_btn.clicked.connect(self._on_add_task)
        self._clear_btn.clicked.connect(self._on_clear_done)

        self._sig_connections = []
        for sig, slot in (
            (self._controller.board_reset, self._rebuild_all),
            (self._controller.tasks_changed, self._rebuild_all),
            (self._controller.task_changed, self._on_task_changed),
            (self._controller.auto_mode_changed, self._on_auto_mode),
        ):
            conn = sig.connect(slot, Qt.QueuedConnection)
            self._sig_connections.append((sig, conn))

        self._refresh_style()
        self._sync_auto_switch()

    # ── 插件上下文（拉模型，showEvent 时取最新）──

    def set_context_provider(self, provider):
        self._ctx_provider = provider

    def showEvent(self, event):
        super().showEvent(event)
        if self._ctx_provider is not None:
            try:
                self._last_ctx = self._ctx_provider() or {}
            except Exception:
                self._last_ctx = {}
        self._controller.bind(self._last_ctx)
        self._sync_auto_switch()
        self._rebuild_all()
        self._refresh_env()

    def refresh_font_size(self):
        self._refresh_style()
        self._rebuild_all()

    # ================================================================
    #  交互
    # ================================================================

    def _on_add_task(self):
        dlg = TaskDialog(self.window())
        if dlg.exec_() == QDialog.Accepted:
            title, detail = dlg.get_task()
            if title:
                self._controller.add_task(title, detail)

    def _on_clear_done(self):
        n = self._controller.clear_done()
        if n:
            self._notify("已清空", f"移除 {n} 个已完成任务")

    def _on_auto_switch(self, checked: bool):
        self._controller.set_auto_mode(bool(checked))

    def _on_auto_mode(self, auto: bool):
        self._sync_auto_switch()

    def _sync_auto_switch(self):
        # 阻塞信号：程序化同步不回写 controller（避免幂等 persist 抖动）
        self._auto_switch.blockSignals(True)
        self._auto_switch.setChecked(self._controller.auto_mode)
        self._auto_switch.blockSignals(False)

    def _on_move_request(self, task_id: str, new_status: str):
        self._controller.move_task(task_id, new_status, by="user")

    def _notify(self, title: str, message: str):
        services = (self._last_ctx or {}).get("services") or {}
        notify = services.get("notify")
        if notify:
            try:
                notify(title, message)
            except Exception:
                pass

    def _refresh_env(self):
        """刷新头部环境信息栏（模型 / 工作路径）"""
        env = self._controller.get_env_info()
        Colors.refresh()
        self._model_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; {FONT_CSS} font-size: {scale_font_size(11)}px;"
        )
        self._workdir_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; {FONT_CSS} font-size: {scale_font_size(10)}px;"
        )
        self._model_label.setText(env["model"])
        wd = env["workdir"]
        self._workdir_label.setText(f"{wd}" if wd and len(wd) < 48 else (f"…{wd[-45:]}" if wd else ""))

    def _show_report(self, task_id: str):
        task = self._controller.get_task(task_id)
        if task is None:
            return
        report = self._controller.get_report(task_id)
        ReportDialog(task.title, report, self.window()).exec_()

    def _show_detail(self, task_id: str):
        """打开任务详情（双击卡片；done 卡报告按钮仍直连报告）"""
        task = self._controller.get_task(task_id)
        if task is None:
            return
        report = self._controller.get_report(task_id) if task.status == "done" else ""
        TaskDetailDialog(
            task,
            report,
            processing=self._controller.is_processing(task_id),
            preview=getattr(task, "_stream_preview", ""),
            parent=self.window(),
        ).exec_()

    # ================================================================
    #  渲染
    # ================================================================

    def _rebuild_all(self):
        """全量重建四列任务卡"""
        self._refresh_env()
        for col in self._columns.values():
            col.clear_cards()
        self._cards.clear()

        tasks = self._controller.get_tasks()
        counts = {s: 0 for s in COLUMNS}
        processing = {s: 0 for s in COLUMNS}
        for task in tasks:
            status = task.status if task.status in COLUMNS else "todo"
            card = TaskCardWidget(task.id, self)
            card.refresh(task, self._controller.is_processing(task.id))
            # 接线任务卡交互
            card.startRequested.connect(self._controller.start_task)
            card.stopRequested.connect(self._controller.stop_task)
            card.removeRequested.connect(self._controller.remove_task)
            card.moveRequested.connect(self._on_move_request)
            card.reportRequested.connect(self._show_report)
            card.detailRequested.connect(self._show_detail)
            self._columns[status].add_card(card)
            self._cards[task.id] = card
            counts[status] += 1
            if self._controller.is_processing(task.id):
                processing[status] += 1

        for status, col in self._columns.items():
            col.set_count(counts[status], processing[status])

    def _on_task_changed(self, task_id: str):
        """单任务增量刷新"""
        card = self._cards.get(task_id)
        if card is None:
            self._rebuild_all()
            return
        task = self._controller.get_task(task_id)
        if task is None:
            self._rebuild_all()  # 已被删除
            return
        card.refresh(task, self._controller.is_processing(task_id))

    # ================================================================
    #  样式
    # ================================================================

    def _refresh_style(self):
        Colors.refresh()
        self.setStyleSheet(f"""
            #taskboardCard {{ background: transparent; border: none; }}
            StrongBodyLabel {{ color: {Colors.TEXT_PRIMARY}; {FONT_CSS}
                               font-size: {scale_font_size(14)}px; }}
        """)
        self._hint_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; {FONT_CSS} font-size: {scale_font_size(10)}px;"
        )
        self._add_btn.setStyleSheet(f"""
            PrimaryPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Colors.SEND_BTN_START}, stop:1 {Colors.SEND_BTN_END});
                color: {Colors.BUTTON_TEXT_ON_ACCENT};
                border: none; border-radius: {Colors.SEND_BTN_RADIUS}px;
                padding: 4px 14px; {FONT_CSS} font-size: {scale_font_size(12)}px;
                font-weight: bold;
            }}
        """)
        for col in self._columns.values():
            col._refresh_style()
