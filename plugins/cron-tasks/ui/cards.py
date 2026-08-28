# -*- coding: utf-8 -*-
"""cron-tasks 卡片组件 — 任务中心卡（列表 + 编辑 + 运行历史，QStackedWidget 三页）

布局参考 autoloop cards.py（full 覆盖对话区、hide_sidebar、design_tokens 配色）。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    ComboBox,
    FluentIcon,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    StrongBodyLabel,
    SwitchButton,
    TextEdit,
    ToolButton,
    TransparentToolButton,
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

from app.utils.design_tokens import Colors, font_size_css, scale_font_size, apply_font_size_to_widget
from app.utils.utils import get_font_family_css

from crontasks_core.models import CronJob, WEEKDAY_CN

FONT_CSS = get_font_family_css()

# 编辑器模式（对齐 openhanako ScheduleEditor 的 6 模式）
SCHEDULE_MODES = ["interval", "daily", "weekly", "monthly", "once", "advanced"]
SCHEDULE_MODE_LABELS = {
    "interval": "周期间隔",
    "daily": "每天",
    "weekly": "每周",
    "monthly": "每月",
    "once": "单次",
    "advanced": "高级 Cron",
}
STATUS_LABELS = {
    "": "未运行",
    "success": "✅ 成功",
    "error": "❌ 失败",
    "cancelled": "🛑 已取消",
    "timeout": "⏱ 超时",
    "running": "▶ 运行中",
}

# 常见任务模板（点击 → 预填编辑表单，用户改完保存即可）
# mode 取 SCHEDULE_MODES；time/interval/weekday/month_day/cron 按 mode 生效
JOB_TEMPLATES = [
    {
        "name": "每日早报",
        "label": "每日早报",
        "mode": "daily",
        "time": "09:00",
        "prompt": "搜索今日 AI/科技领域重要新闻，输出 5 条要点摘要（标题 + 一句话说明）。",
    },
    {
        "name": "天气播报",
        "label": "天气播报",
        "mode": "daily",
        "time": "08:00",
        "prompt": "查询深圳今日天气与明日预报，用两句话总结，附穿衣建议。",
    },
    {
        "name": "每周周报",
        "label": "每周周报",
        "mode": "weekly",
        "time": "17:30",
        "weekday": 5,
        "prompt": "根据本周 git log 与工作目录变更，帮我生成周报初稿（本周完成/下周计划/风险）。",
    },
    {
        "name": "工作日站会提醒",
        "label": "站会提醒",
        "mode": "advanced",
        "cron": "0 9 * * 1-5",
        "prompt": "提醒：每日站会时间到，请准备昨日进展与今日计划。",
    },
    {
        "name": "每周仓库清理",
        "label": "仓库清理",
        "mode": "weekly",
        "time": "20:00",
        "weekday": 0,
        "prompt": "扫描当前工作目录的临时文件与 __pycache__，列出可清理项清单（不要直接删除）。",
    },
    {
        "name": "项目健康检查",
        "label": "项目健康检查",
        "mode": "interval",
        "interval_value": 12,
        "interval_unit": 1,
        "prompt": "检查当前项目最近 git 提交与 TODO/FIXME 数量，输出一页健康简报。",
    },
]


def _fmt_dt(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%m-%d %H:%M:%S")
    except ValueError:
        return iso


# ============================================================
#  ScheduleDraft：UI 模式 ↔ 存储格式（type + schedule）互转
# ============================================================


class ScheduleDraft:
    """调度编辑草稿（参考 openhanako schedule-draft.ts）"""

    def __init__(self):
        self.mode = "daily"
        self.interval_value = 30
        self.interval_unit = 0  # 0=分钟 1=小时 2=天
        self.time = "09:00"
        self.weekdays = {1}  # cron dow 集合（0=周日 … 6=周六），多选
        self.month_day = 1
        self.date_time = ""
        self.cron = "0 9 * * *"

    UNIT_MINUTES = (1, 60, 1440)

    def from_job(self, job: CronJob) -> "ScheduleDraft":
        if job.type == "every":
            mins = max(1, int(job.schedule))
            if mins % 1440 == 0:
                self.mode, self.interval_value, self.interval_unit = "interval", mins // 1440, 2
            elif mins % 60 == 0:
                self.mode, self.interval_value, self.interval_unit = "interval", mins // 60, 1
            else:
                self.mode, self.interval_value, self.interval_unit = "interval", mins, 0
            return self
        if job.type == "at":
            self.mode = "once"
            try:
                dt = datetime.fromisoformat(str(job.schedule))
                self.date_time = dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                self.date_time = str(job.schedule)
            return self
        # cron
        expr = str(job.schedule)
        parts = expr.split()
        if len(parts) == 5:
            m, h, dom, mon, dow = parts
            if mon == "*" and dom == "*" and dow == "*" and m.isdigit() and h.isdigit():
                self.mode, self.time = "daily", f"{int(h):02d}:{int(m):02d}"
                return self
            if mon == "*" and dom == "*" and dow and m.isdigit() and h.isdigit() and all(p.isdigit() for p in dow.split(",")):
                self.mode, self.weekdays, self.time = (
                    "weekly",
                    {int(d) % 7 for d in dow.split(",")},
                    f"{int(h):02d}:{int(m):02d}",
                )
                return self
            if mon == "*" and dow == "*" and dom.isdigit() and m.isdigit() and h.isdigit():
                self.mode, self.month_day, self.time = "monthly", int(dom), f"{int(h):02d}:{int(m):02d}"
                return self
        self.mode, self.cron = "advanced", expr
        return self

    def to_stored(self):
        """→ (type, schedule)。非法输入抛 ValueError"""
        if self.mode == "interval":
            value = max(1, int(self.interval_value))
            mins = value * self.UNIT_MINUTES[self.interval_unit]
            return "every", mins
        if self.mode == "once":
            dt = datetime.strptime(self.date_time, "%Y-%m-%d %H:%M")
            if dt <= datetime.now():
                raise ValueError("单次任务时间必须在未来")
            return "at", dt.isoformat(timespec="minutes")
        if self.mode == "advanced":
            expr = self.cron.strip()
            if not expr:
                raise ValueError("cron 表达式不能为空")
            return "cron", expr
        hour, minute = (int(x) for x in self.time.split(":")[:2])
        if self.mode == "weekly":
            if not self.weekdays:
                raise ValueError("请至少勾选一个星期")
            dow_list = ",".join(str(d) for d in sorted(self.weekdays))
            return "cron", f"{minute} {hour} * * {dow_list}"
        if self.mode == "monthly":
            return "cron", f"{minute} {hour} {int(self.month_day)} * *"
        return "cron", f"{minute} {hour} * * *"

    def preview(self) -> str:
        try:
            t, s = self.to_stored()
        except ValueError:
            return "—"
        if t == "every":
            if s % 1440 == 0:
                return f"每 {s // 1440} 天"
            if s % 60 == 0:
                return f"每 {s // 60} 小时"
            return f"每 {s} 分钟"
        if t == "at":
            return f"单次 · {s}"
        from crontasks_core.models import cron_to_human

        return cron_to_human(str(s))


# ============================================================
#  任务行卡片
# ============================================================


class JobRowCard(QFrame):
    """单个任务行：启用开关 + 信息区 + 操作按钮（运行中：运行钮变停止钮）"""

    toggleRequested = pyqtSignal(str)  # job_id
    editRequested = pyqtSignal(str)
    historyRequested = pyqtSignal(str)
    deleteRequested = pyqtSignal(str)
    runNowRequested = pyqtSignal(str)
    stopRequested = pyqtSignal(str)

    def __init__(self, job: CronJob, parent=None):
        super().__init__(parent)
        self._job = job
        self._running = False
        self.setObjectName("cronJobRowCard")
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        job = self._job
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # 启用开关
        self._switch = SwitchButton()
        self._switch.setChecked(job.enabled)
        self._switch.checkedChanged.connect(lambda _v: self.toggleRequested.emit(self._job.id))
        layout.addWidget(self._switch)

        # 信息区
        info = QVBoxLayout()
        info.setSpacing(2)
        self._title_label = StrongBodyLabel(job.display_label())
        info.addWidget(self._title_label)

        meta_parts = [f"⏱ {job.schedule_desc()}"]
        if job.agent:
            meta_parts.append(f"🤖 {job.agent}")
        if job.model_key:
            meta_parts.append(f"💠 {job.model_key}")
        self._meta_label = BodyLabel(" · ".join(meta_parts))
        info.addWidget(self._meta_label)

        self._status_label = BodyLabel("")
        info.addWidget(self._status_label)
        layout.addLayout(info, 1)

        # 操作按钮：运行/停止（动态） + 编辑 + 历史 + 删除
        self._run_btn = ToolButton(FluentIcon.PLAY)
        self._run_btn.setToolTip("立即运行")
        self._run_btn.setFixedSize(30, 30)
        self._run_btn.clicked.connect(self._on_run_clicked)
        layout.addWidget(self._run_btn)

        for icon, tip, signal in (
            (FluentIcon.EDIT, "编辑", self.editRequested),
            (FluentIcon.HISTORY, "运行历史", self.historyRequested),
            (FluentIcon.DELETE, "删除", self.deleteRequested),
        ):
            btn = ToolButton(icon)
            btn.setToolTip(tip)
            btn.setFixedSize(30, 30)
            btn.clicked.connect(lambda _c, s=signal: s.emit(self._job.id))
            layout.addWidget(btn)

        # qfluentwidgets 组件字号跟随系统设置（BodyLabel 等自身 QSS 写死不随缩放）
        apply_font_size_to_widget(self)
        self._apply_status_style()

    def _apply_status_style(self):
        """运行状态行样式：运行中高亮醒目，否则次要色"""
        if self._running:
            self._status_label.setStyleSheet(
                f"color: {Colors.REALTIME_SUCCESS}; font-weight: bold; {font_size_css(13)} {FONT_CSS}"
            )
        else:
            self._status_label.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; {font_size_css(12)} {FONT_CSS}"
            )

    def _on_run_clicked(self):
        """运行钮：常态=立即运行；运行中=停止"""
        if self._running:
            self.stopRequested.emit(self._job.id)
        else:
            self.runNowRequested.emit(self._job.id)

    def _apply_run_state(self):
        """按运行状态切换按钮图标/提示"""
        if self._running:
            self._run_btn.setIcon(FluentIcon.PAUSE)
            self._run_btn.setToolTip("停止运行")
        else:
            self._run_btn.setIcon(FluentIcon.PLAY)
            self._run_btn.setToolTip("立即运行")

    def refresh(self, job: CronJob, running: bool = False):
        self._job = job
        was_running = self._running
        self._running = running
        self._apply_run_state()
        if running != was_running:
            # 运行态切换：刷新状态行颜色 + 卡片高亮边框（动态属性 + repolish）
            self._apply_status_style()
            self.setProperty("running", "true" if running else "false")
            self.style().unpolish(self)
            self.style().polish(self)
        self._switch.setChecked(job.enabled)
        self._title_label.setText(job.display_label())
        meta_parts = [f"⏱ {job.schedule_desc()}"]
        if job.agent:
            meta_parts.append(f"🤖 {job.agent}")
        if job.model_key:
            meta_parts.append(f"💠 {job.model_key}")
        self._meta_label.setText(" · ".join(meta_parts))
        if running:
            # 心跳：实时显示已运行秒数（5s 一刷）
            elapsed = 0
            if job.last_run_at:
                try:
                    elapsed = max(0, int((__import__("datetime").datetime.now() - __import__("datetime").datetime.fromisoformat(job.last_run_at)).total_seconds()))
                except Exception:
                    pass
            base = f"▶ 正在执行 · 已运行 {elapsed}s"
            nxt = "—"
        else:
            status = job.last_status
            base = f"上次: {STATUS_LABELS.get(status, status)}"
            if job.last_run_at:
                base += f" · {_fmt_dt(job.last_run_at)}"
            nxt = f"下次: {_fmt_dt(job.next_run_at)}" if job.enabled and job.next_run_at else ("已禁用" if not job.enabled else "—")
        self._status_label.setText(f"{base} ｜ {nxt}")

    def _apply_style(self):
        Colors.refresh()
        self.setStyleSheet(f"""
            #cronJobRowCard {{
                background: {Colors.CARD_BG_SOLID};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
                {FONT_CSS}
            }}
            #cronJobRowCard:hover {{ border: 1px solid {Colors.INPUT_FOCUS_BORDER}; }}
            #cronJobRowCard[running="true"] {{
                border: 1px solid {Colors.REALTIME_SUCCESS};
                border-left: 4px solid {Colors.REALTIME_SUCCESS};
            }}
        """)


# ============================================================
#  编辑面板
# ============================================================


class JobEditPanel(QWidget):
    """新建/编辑任务表单"""

    saveRequested = pyqtSignal(object)  # CronJob
    cancelRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job: Optional[CronJob] = None  # None = 新建
        self._draft = ScheduleDraft()
        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # 顶部行：标题 + 右侧操作（保存/取消与标题同行，符合操作直觉）
        header = QHBoxLayout()
        self._title = StrongBodyLabel("新建任务")
        header.addWidget(self._title)
        header.addStretch()
        self._cancel_btn = PushButton("取消")
        self._cancel_btn.clicked.connect(self.cancelRequested.emit)
        header.addWidget(self._cancel_btn)
        self._save_btn = PrimaryPushButton("保存")
        self._save_btn.clicked.connect(self._on_save)
        header.addWidget(self._save_btn)
        layout.addLayout(header)

        def _field(label_text: str, widget: QWidget, stretch: int = 1) -> QHBoxLayout:
            row = QHBoxLayout()
            lbl = BodyLabel(label_text)
            lbl.setFixedWidth(90)
            row.addWidget(lbl)
            row.addWidget(widget, stretch)
            return row

        # 标签
        self._label_edit = LineEdit()
        self._label_edit.setPlaceholderText("任务名称（可选，默认取提示词首行）")
        layout.addLayout(_field("任务名称", self._label_edit))

        # 提示词
        self._prompt_edit = TextEdit()
        self._prompt_edit.setPlaceholderText("📝 到期后要执行的提示词（如：检查 D:/work 目录下今日新增文件并汇总）...")
        self._prompt_edit.setMinimumHeight(72)
        layout.addWidget(self._prompt_edit)

        # 执行模型（参考 prompt-enhancer：主程序 _valid_configs）
        self._model_combo = ComboBox()
        layout.addLayout(_field("执行模型", self._model_combo))

        # 调度模式
        self._mode_combo = ComboBox()
        self._mode_combo.addItems([SCHEDULE_MODE_LABELS[m] for m in SCHEDULE_MODES])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addLayout(_field("调度方式", self._mode_combo))

        # 调度详情区：时间控件单实例，行内按模式显隐 weekday/monthday
        # （Qt 单 parent 限制：同一控件不能同时挂多个布局）
        self._schedule_details = QWidget()
        sd_layout = QVBoxLayout(self._schedule_details)
        sd_layout.setContentsMargins(0, 0, 0, 0)
        sd_layout.setSpacing(6)

        # 间隔：数值 + 单位（interval 模式）
        self._interval_row = QWidget()
        irow = QHBoxLayout(self._interval_row)
        irow.setContentsMargins(0, 0, 0, 0)
        irow.setSpacing(6)
        self._interval_spin = SpinBox()
        self._interval_spin.setRange(1, 999)
        self._interval_spin.setValue(30)
        self._interval_unit_combo = ComboBox()
        self._interval_unit_combo.addItems(["分钟", "小时", "天"])
        irow.addWidget(self._interval_spin)
        irow.addWidget(self._interval_unit_combo)
        irow.addStretch()
        sd_layout.addWidget(self._interval_row)

        # 时间行：[星期多选(仅每周)] [时间(每天/每周/每月)] [几号(仅每月)]
        self._time_row = QWidget()
        trow = QHBoxLayout(self._time_row)
        trow.setContentsMargins(0, 0, 0, 0)
        trow.setSpacing(6)
        # 每周多选：标签顺序周一..周日 → cron dow [1..6,0]
        self._weekday_checks: List[QCheckBox] = []
        for _lbl, _dow in zip(("一", "二", "三", "四", "五", "六", "日"), (1, 2, 3, 4, 5, 6, 0)):
            cb = CheckBox(_lbl)
            cb.stateChanged.connect(self._refresh_preview)
            self._weekday_checks.append(cb)
            trow.addWidget(cb)
        self._weekday_checks[0].setChecked(True)  # 默认周一
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        from PyQt5.QtCore import QTime

        self._time_edit.setTime(QTime(9, 0))
        trow.addWidget(self._time_edit)
        self._monthday_spin = SpinBox()
        self._monthday_spin.setRange(1, 31)
        self._monthday_spin.setValue(1)
        trow.addWidget(self._monthday_spin)
        trow.addStretch()
        sd_layout.addWidget(self._time_row)

        # 单次：日期时间（once 模式，日历弹窗选择，不再手输）
        from PyQt5.QtWidgets import QDateTimeEdit

        self._once_edit = QDateTimeEdit()
        self._once_edit.setCalendarPopup(True)
        self._once_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        from PyQt5.QtCore import QDateTime as _QDT

        self._once_edit.setDateTime(_QDT.currentDateTime().addDays(1))
        sd_layout.addWidget(self._once_edit)

        # 高级 cron（advanced 模式）
        self._cron_edit = LineEdit()
        self._cron_edit.setPlaceholderText("分 时 日 月 周，如 0 9 * * 1-5")
        sd_layout.addWidget(self._cron_edit)
        layout.addWidget(self._schedule_details)

        # 预览
        self._preview_label = BodyLabel("")
        self._preview_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(self._preview_label)

        # 智能体 + 工作目录
        self._agent_combo = ComboBox()
        layout.addLayout(_field("执行智能体", self._agent_combo))

        # 完成通知方式
        self._notify_combo = ComboBox()
        self._notify_combo.addItems(["默认弹窗", "系统通知", "Gateway 消息"])
        self._notify_combo.currentIndexChanged.connect(self._on_notify_mode_changed)
        layout.addLayout(_field("完成通知", self._notify_combo))
        self._notify_target_row = QWidget()
        nrow = QHBoxLayout(self._notify_target_row)
        nrow.setContentsMargins(0, 0, 0, 0)
        nrow.setSpacing(4)
        nlbl = BodyLabel("发送目标")
        nlbl.setFixedWidth(90)
        nrow.addWidget(nlbl)
        # 直接对接主程序已连接 gateway：下拉列出机器人已知会话，免手填
        self._notify_target_combo = ComboBox()
        nrow.addWidget(self._notify_target_combo, 1)
        self._notify_target_row.setVisible(False)
        layout.addWidget(self._notify_target_row)

        self._workdir_row = QWidget()
        wdrow = QHBoxLayout(self._workdir_row)
        wdrow.setContentsMargins(0, 0, 0, 0)
        wdrow.setSpacing(4)
        self._workdir_edit = LineEdit()
        self._workdir_edit.setPlaceholderText("留空 = 当前工作目录")
        wdrow.addWidget(self._workdir_edit, 1)
        browse_btn = ToolButton(FluentIcon.FOLDER)
        browse_btn.setToolTip("选择目录")
        browse_btn.setFixedSize(28, 28)
        browse_btn.clicked.connect(self._browse_workdir)
        wdrow.addWidget(browse_btn)
        layout.addWidget(self._workdir_row)
        # workdir 行带标签
        wd_field = QHBoxLayout()
        wd_lbl = BodyLabel("工作目录")
        wd_lbl.setFixedWidth(90)
        wd_field.addWidget(wd_lbl)
        wd_field.addWidget(self._workdir_row)
        layout.addLayout(wd_field)

        layout.addStretch()

        # 联动预览刷新
        self._interval_spin.valueChanged.connect(self._refresh_preview)
        self._interval_unit_combo.currentIndexChanged.connect(self._refresh_preview)
        self._time_edit.timeChanged.connect(self._refresh_preview)
        self._monthday_spin.valueChanged.connect(self._refresh_preview)
        self._once_edit.dateTimeChanged.connect(self._refresh_preview)
        self._cron_edit.textChanged.connect(self._refresh_preview)

    def _on_notify_mode_changed(self, index: int):
        # 仅 Gateway 模式需要目标：拉取主程序已连接 gateway 的已知会话
        self._notify_target_row.setVisible(index == 2)
        if index == 2:
            self._load_gateway_sessions()

    def _load_gateway_sessions(self):
        """从主程序 PlatformManager 拉取已知会话（platform:chat_id 免手填）"""
        combo = self._notify_target_combo
        current = combo.currentData()
        combo.clear()
        sessions = []
        try:
            from app.gateway import get_platform_manager

            mgr = get_platform_manager()
            if mgr is not None:
                sessions = mgr.get_sessions() or []
        except Exception as e:
            logger.warning(f"[cron-tasks] 拉取 gateway 会话失败: {e}")
        if not sessions:
            combo.addItem("（暂无会话——先给机器人发条消息）", "")
        else:
            sessions = sorted(sessions, key=lambda s: s.last_active, reverse=True)
            for s in sessions:
                p = getattr(s.platform, "value", s.platform)
                combo.addItem(s.display_name, f"{p}:{s.chat_id}")
        if current:
            cidx = combo.findData(current)
            if cidx >= 0:
                combo.setCurrentIndex(cidx)
            else:
                combo.addItem(f"（原配置）{current}", current)
                combo.setCurrentIndex(combo.count() - 1)

    def _browse_workdir(self):
        from PyQt5.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, "选择工作目录", self._workdir_edit.text() or "")
        if folder:
            self._workdir_edit.setText(folder)

    def _on_mode_changed(self, index: int):
        mode = SCHEDULE_MODES[index] if 0 <= index < len(SCHEDULE_MODES) else "daily"
        self._interval_row.setVisible(mode == "interval")
        self._time_row.setVisible(mode in ("daily", "weekly", "monthly"))
        for _cb in self._weekday_checks:
            _cb.setVisible(mode == "weekly")
        self._monthday_spin.setVisible(mode == "monthly")
        self._once_edit.setVisible(mode == "once")
        self._cron_edit.setVisible(mode == "advanced")
        self._refresh_preview()

    def _refresh_preview(self):
        draft = self._collect_draft()
        self._preview_label.setText(f"调度预览: {draft.preview()}")

    # ---------- 数据进出 ----------

    def load_agents(self, agent_names: List[str]):
        self._agent_combo.clear()
        self._agent_combo.addItem("默认（跟随主程序）", userData="")
        for name in agent_names:
            self._agent_combo.addItem(name, userData=name)

    def load_models(self, model_options: List[Dict[str, str]]):
        """灌入模型选项：[{key: provider配置名, label: 显示名}]，首项为默认"""
        self._model_combo.clear()
        self._model_combo.addItem("默认（跟随当前会话模型）", userData="")
        for opt in model_options:
            self._model_combo.addItem(opt.get("label") or opt.get("key", "?"), userData=opt.get("key", ""))

    def begin_create(self, default_workdir: str = ""):
        self._job = None
        self._title.setText("新建任务")
        self._label_edit.clear()
        self._prompt_edit.clear()
        self._draft = ScheduleDraft()
        self._apply_draft_to_ui(self._draft)
        idx = self._agent_combo.findData("")
        if idx >= 0:
            self._agent_combo.setCurrentIndex(idx)
        midx = self._model_combo.findData("")
        if midx >= 0:
            self._model_combo.setCurrentIndex(midx)
        self._workdir_edit.setText(default_workdir)
        self._refresh_preview()

    def begin_create_with_template(self, tpl: dict, default_workdir: str = ""):
        """从模板新建：预填 label/prompt/调度字段，其余同 begin_create"""
        self.begin_create(default_workdir)
        self._title.setText(f"新建任务 — 模板「{tpl.get('name', '')}」")
        self._label_edit.setText(tpl.get("label", ""))
        self._prompt_edit.setPlainText(tpl.get("prompt", ""))
        # 调度字段覆盖
        d = self._draft
        d.mode = tpl.get("mode", "daily")
        if "time" in tpl:
            d.time = tpl["time"]
        if "interval_value" in tpl:
            d.interval_value = int(tpl["interval_value"])
        if "interval_unit" in tpl:
            d.interval_unit = int(tpl["interval_unit"])
        if "weekday" in tpl:
            d.weekday = int(tpl["weekday"])
        if "month_day" in tpl:
            d.month_day = int(tpl["month_day"])
        if "cron" in tpl:
            d.cron = tpl["cron"]
        self._apply_draft_to_ui(d)
        self._refresh_preview()

    def begin_edit(self, job: CronJob):
        self._job = job
        self._title.setText("编辑任务")
        self._label_edit.setText(job.label)
        self._prompt_edit.setPlainText(job.prompt)
        self._draft = ScheduleDraft().from_job(job)
        self._apply_draft_to_ui(self._draft)
        idx = self._agent_combo.findData(job.agent)
        self._agent_combo.setCurrentIndex(idx if idx >= 0 else 0)
        midx = self._model_combo.findData(job.model_key)
        self._model_combo.setCurrentIndex(midx if midx >= 0 else 0)
        self._workdir_edit.setText(job.workdir or "")
        # 完成通知回填：""=默认 / system / gateway:平台:chat_id
        n = job.notify or ""
        if n.startswith("gateway:"):
            self._notify_combo.setCurrentIndex(2)
            self._notify_target_combo.clear()
            self._notify_target_combo.addItem(
                f"（原配置）{':'.join(n.split(':', 2)[1:])}", ":".join(n.split(':', 2)[1:])
            )
        elif n == "system":
            self._notify_combo.setCurrentIndex(1)
        else:
            self._notify_combo.setCurrentIndex(0)
        self._refresh_preview()

    def _apply_draft_to_ui(self, d: ScheduleDraft):
        self._mode_combo.setCurrentIndex(SCHEDULE_MODES.index(d.mode))
        self._interval_spin.setValue(max(1, int(d.interval_value)))
        self._interval_unit_combo.setCurrentIndex(d.interval_unit)
        h, m = (int(x) for x in d.time.split(":")[:2])
        from PyQt5.QtCore import QTime

        self._time_edit.setTime(QTime(h, m))
        for idx, cb in enumerate(self._weekday_checks):
            cb.setChecked((idx + 1) % 7 in d.weekdays)
        self._monthday_spin.setValue(d.month_day)
        if d.date_time:
            from PyQt5.QtCore import QDateTime

            try:
                self._once_edit.setDateTime(QDateTime.fromString(d.date_time, "yyyy-MM-dd HH:mm"))
            except Exception:
                pass
        self._cron_edit.setText(d.cron)
        # 手动触发行可见性（setCurrentIndex 不触发 currentIndexChanged 时兜底）
        self._on_mode_changed(SCHEDULE_MODES.index(d.mode))

    def _collect_draft(self) -> ScheduleDraft:
        d = ScheduleDraft()
        d.mode = SCHEDULE_MODES[self._mode_combo.currentIndex()]
        d.interval_value = self._interval_spin.value()
        d.interval_unit = self._interval_unit_combo.currentIndex()
        d.time = self._time_edit.time().toString("HH:mm")
        d.weekdays = {
            (idx + 1) % 7 for idx, cb in enumerate(self._weekday_checks) if cb.isChecked()
        }
        d.month_day = self._monthday_spin.value()
        d.date_time = self._once_edit.dateTime().toString("yyyy-MM-dd HH:mm")
        d.cron = self._cron_edit.text().strip()
        return d

    def _on_save(self):
        """组装 CronJob 并发射 saveRequested；校验失败弹提示"""
        prompt = self._prompt_edit.toPlainText().strip()
        if not prompt:
            self._title.setText("编辑任务 — ❗ 提示词不能为空")
            return
        try:
            jtype, schedule = self._collect_draft().to_stored()
        except ValueError as e:
            self._title.setText(f"编辑任务 — ❗ {e}")
            return
        job = self._job or CronJob(id=f"job_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
        job.type = jtype
        job.schedule = schedule
        job.label = self._label_edit.text().strip()
        job.prompt = prompt
        job.agent = self._agent_combo.currentData() or ""
        job.model_key = self._model_combo.currentData() or ""
        job.workdir = self._workdir_edit.text().strip()
        ni = self._notify_combo.currentIndex()
        if ni == 2:
            target = str(self._notify_target_combo.currentData() or "")
            if not target:
                self._title.setText("编辑任务 — ❗ 无可用 Gateway 会话（先给机器人发条消息）")
                return
            job.notify = f"gateway:{target}"
        else:
            job.notify = "system" if ni == 1 else ""
        job.enabled = True
        err = job.validate()
        if err:
            self._title.setText(f"编辑任务 — ❗ {err}")
            return
        self.saveRequested.emit(job)


# ============================================================
#  运行历史面板
# ============================================================


class RunHistoryPanel(QWidget):
    """任务运行历史：左侧记录列表 + 右侧完整详情（响应全文）"""

    backRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: List[dict] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self._title = StrongBodyLabel("运行历史")
        header.addWidget(self._title)
        header.addStretch()
        back_btn = PushButton("← 返回")
        back_btn.clicked.connect(self.backRequested.emit)
        header.addWidget(back_btn)
        layout.addLayout(header)

        # 任务上下文摘要（智能体/模型/调度）
        self._ctx_label = BodyLabel("")
        self._ctx_label.setWordWrap(True)
        layout.addWidget(self._ctx_label)

        body = QHBoxLayout()
        self._list = QListWidget()
        self._list.setMinimumWidth(230)
        self._list.setStyleSheet(f"QListWidget {{ {font_size_css(13)} {FONT_CSS} }}")
        self._list.itemClicked.connect(self._on_item_clicked)
        body.addWidget(self._list, 3)

        detail_wrap = QVBoxLayout()
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setLineWrapMode(QTextEdit.WidgetWidth)
        self._detail.setStyleSheet(f"QTextEdit {{ {font_size_css(13)} {FONT_CSS} }}")
        detail_wrap.addWidget(self._detail, 1)
        body.addLayout(detail_wrap, 5)
        layout.addLayout(body, 1)

        self._ctx_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; {font_size_css(12)} {FONT_CSS}"
        )
        # qfluentwidgets 组件字号跟随系统设置
        apply_font_size_to_widget(self)

    def load(self, job: CronJob, records: List[dict]):
        self._title.setText(f"运行历史 — {job.display_label()}")
        ctx_parts = [f"调度: {job.schedule_desc()}"]
        if job.agent:
            ctx_parts.append(f"智能体: {job.agent}")
        if job.model_key:
            # 复合键 "config||model" 只展示可读后半段
            model_disp = str(job.model_key).partition("||")[2] or job.model_key
            ctx_parts.append(f"模型: {model_disp}")
        ctx_parts.append(f"共 {len(records)} 次记录")
        self._ctx_label.setText(" · ".join(ctx_parts))
        self._records = records
        self._list.clear()
        self._detail.clear()
        for i, rec in enumerate(records):
            status = rec.get("status", "")
            dur = rec.get("durationMs", 0)
            dur_s = f"{dur / 1000:.1f}s" if dur else "—"
            tools = rec.get("toolCalls")
            tool_s = f" · 🛠{tools}" if isinstance(tools, int) and tools > 0 else ""
            item = QListWidgetItem(
                f"{STATUS_LABELS.get(status, status)}\n{rec.get('ts', '')} · {dur_s}{tool_s}"
            )
            item.setData(Qt.UserRole, i)
            self._list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.UserRole)
        if not isinstance(idx, int) or not (0 <= idx < len(self._records)):
            return
        rec = self._records[idx]
        dur = rec.get("durationMs", 0)
        lines = [
            f"时间: {rec.get('ts', '')}",
            f"状态: {STATUS_LABELS.get(rec.get('status', ''), rec.get('status', ''))}",
            f"耗时: {dur / 1000:.1f}s" if dur else "耗时: —",
        ]
        tools = rec.get("toolCalls")
        if isinstance(tools, int) and tools > 0:
            lines.append(f"工具调用: {tools} 次")
        if rec.get("agent"):
            lines.append(f"智能体: {rec['agent']}")
        if rec.get("model"):
            lines.append(f"模型: {str(rec['model']).partition('||')[2] or rec['model']}")
        if rec.get("error"):
            lines.append(f"错误: {rec['error']}")
        lines.append("")
        lines.append("─" * 24 + " 响应全文 " + "─" * 24)
        lines.append(str(rec.get("responseText") or rec.get("responseHead") or "（无响应内容）"))
        self._detail.setPlainText("\n".join(lines))


# ============================================================
#  任务中心卡（主卡片，full 覆盖对话区）
# ============================================================


class CronTasksCard(QFrame):
    """定时任务中心 — 列表 / 编辑 / 历史 三页栈"""

    closed = pyqtSignal()

    PAGE_LIST, PAGE_EDIT, PAGE_HISTORY = 0, 1, 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cronTasksCard")
        self._ctx_provider = None
        self._last_ctx: Dict[str, Any] = {}
        self._rows: Dict[str, JobRowCard] = {}
        self._build_ui()
        # qfluentwidgets 组件字号跟随系统设置
        apply_font_size_to_widget(self)
        self._refresh_theme_style()

    # ── 插件上下文（拉模型）──

    def set_context_provider(self, provider):
        self._ctx_provider = provider

    def showEvent(self, event):
        super().showEvent(event)
        # 1) 先拉上下文并启动 controller（services 注入最关键，任何后续失败不影响调度）
        try:
            if self._ctx_provider is not None:
                self._last_ctx = self._ctx_provider() or {}
        except Exception:
            pass
        from .controller import CronTasksController

        ctrl = CronTasksController.get_instance()
        ctrl.ensure_started(self._last_ctx)
        ctrl.bind_card(self)  # 注册卡片实例，调度器变化时刷新
        self.refresh_jobs()
        # 2) 下拉数据源（每步独立容错，失败仅影响对应下拉）
        try:
            self._load_agents()
        except Exception:
            pass
        try:
            self._load_models()
        except Exception:
            pass

    def _load_agents(self):
        services = self._last_ctx.get("services") or {}
        am_getter = services.get("get_agent_manager")
        names: List[str] = []
        if callable(am_getter):
            am = am_getter()
            try:
                names = [a.name for a in (am.list_agents() or []) if getattr(a, "name", "")]
            except Exception:
                names = []
        self._edit_panel.load_agents(names)

    def _load_models(self):
        """从主程序 _valid_configs 灌入模型选项（参考 prompt-enhancer 先例）

        展开粒度：每个配置 × 其「模型列表」逐项 = 一个选项
        （一个服务商可选它的任意模型，不再只绑当前模型）。
        key 为复合键 "<config_id>||<model>"，执行时覆盖 模型名称。
        双源兜底：ctx main_widget → UIPluginRegistry._main_widget → 任一窗口 main_widget。
        """
        mw = self._last_ctx.get("main_widget")
        if mw is None:
            try:
                from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

                reg = UIPluginRegistry.get_instance()
                mw = reg._main_widget or next(iter(reg._window_main_widgets.values()), None)
            except Exception:
                mw = None
        valid = getattr(mw, "_valid_configs", None)
        current = getattr(mw, "_current_provider_name", None)
        options: List[Dict[str, str]] = []
        if isinstance(valid, dict):
            for key, cfg in valid.items():
                if not isinstance(cfg, dict):
                    continue
                display = str(cfg.get("display_name") or cfg.get("name") or cfg.get("provider_name") or key)
                cur_model = str(cfg.get("模型名称") or "")
                models = [str(m) for m in (cfg.get("模型列表") or []) if str(m).strip()]
                if not models:
                    models = [cur_model] if cur_model else []
                for model in models:
                    label = f"{display} · {model}"
                    if key == current and model == cur_model:
                        label += "（当前）"
                    options.append({"key": f"{key}||{model}", "label": label})
        self._edit_panel.load_models(options)

    # ---------- UI ----------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # 标题栏
        title_layout = QHBoxLayout()
        title_layout.addWidget(self._build_title_icon(26))
        title_layout.addSpacing(4)
        title = StrongBodyLabel("定时任务")
        title_layout.addWidget(title)
        self._subtitle = BodyLabel("")
        title_layout.addWidget(self._subtitle)
        title_layout.addStretch()

        self._new_btn = PrimaryPushButton("新建任务")
        self._new_btn.clicked.connect(self._on_new)
        title_layout.addWidget(self._new_btn)

        close_btn = TransparentToolButton(FluentIcon.CLOSE)
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self._on_close)
        title_layout.addWidget(close_btn)
        layout.addLayout(title_layout)
        layout.addWidget(CardSeparator())

        # 三页栈
        self._stack = QStackedWidget()

        # 页 1：任务列表（内层栈：0=空提示文字，1=任务列表 scroll）
        # 模板区在两层栈之外常驻——列表空/非空都能看到模板
        self._list_stack = QStackedWidget()

        # 空提示页（纯文字居中，不用 icon——IconWidget 在流式布局里渲染成孤立小图标）
        empty_page = QWidget()
        ep_layout = QVBoxLayout(empty_page)
        ep_layout.addStretch()
        self._empty_label = BodyLabel("暂无定时任务")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_hint = BodyLabel("从下方模板快速开始，或点击右上角「新建任务」")
        self._empty_hint.setAlignment(Qt.AlignCenter)
        ep_layout.addWidget(self._empty_label)
        ep_layout.addWidget(self._empty_hint)
        ep_layout.addStretch()
        self._list_stack.addWidget(empty_page)

        # 列表页
        list_page = QWidget()
        lp_layout = QVBoxLayout(list_page)
        lp_layout.setContentsMargins(0, 0, 0, 0)
        self._jobs_container = QWidget()
        self._jobs_layout = QVBoxLayout(self._jobs_container)
        self._jobs_layout.setContentsMargins(0, 0, 0, 0)
        self._jobs_layout.setSpacing(6)
        self._jobs_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._jobs_container)
        scroll.setFrameShape(QFrame.NoFrame)
        lp_layout.addWidget(scroll)
        self._list_stack.addWidget(list_page)

        # 页 1 整体：内层栈（空提示/列表）+ 模板区常驻
        page_list_outer = QWidget()
        plo_layout = QVBoxLayout(page_list_outer)
        plo_layout.setContentsMargins(0, 0, 0, 0)
        plo_layout.setSpacing(0)
        plo_layout.addWidget(self._list_stack, 1)

        # 模板区（常驻）：Flow 布局快捷模板按钮
        from qfluentwidgets import FlowLayout

        tpl_wrap = QWidget()
        tpl_layout = QVBoxLayout(tpl_wrap)
        tpl_layout.setContentsMargins(0, 8, 0, 0)
        tpl_layout.setSpacing(6)
        tpl_header = BodyLabel("常见任务模板")
        tpl_header.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; {font_size_css(12)}")
        tpl_layout.addWidget(tpl_header)
        self._tpl_flow = FlowLayout(needAni=False)
        self._tpl_flow.setContentsMargins(0, 0, 0, 0)
        for tpl in JOB_TEMPLATES:
            btn = PushButton(tpl["name"])
            btn.clicked.connect(lambda _c, t=tpl: self._on_template_clicked(t))
            self._tpl_flow.addWidget(btn)
        tpl_layout.addLayout(self._tpl_flow)
        plo_layout.addWidget(tpl_wrap)

        self._stack.addWidget(page_list_outer)

        # 页 2：编辑
        self._edit_panel = JobEditPanel()
        self._edit_panel.saveRequested.connect(self._on_save_job)
        self._edit_panel.cancelRequested.connect(lambda: self._stack.setCurrentIndex(self.PAGE_LIST))
        self._stack.addWidget(self._edit_panel)

        # 页 3：历史
        self._history_panel = RunHistoryPanel()
        self._history_panel.backRequested.connect(lambda: self._stack.setCurrentIndex(self.PAGE_LIST))
        self._stack.addWidget(self._history_panel)

        layout.addWidget(self._stack, 1)

    def _build_title_icon(self, size: int):
        from PyQt5.QtGui import QPixmap

        from pathlib import Path

        icon_dir = Path(__file__).parent.parent / "icons"
        theme = "light" if self._last_ctx.get("is_dark", False) else "dark"
        # manifest: light 键为浅色主题图标（深色线条）；此处按主题取反
        path = icon_dir / ("clock.svg" if theme == "dark" else "clock_light.svg")
        label = QLabel()
        if path.exists():
            pix = QPixmap(str(path))
            label.setPixmap(pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        label.setFixedSize(size, size)
        return label

    # ---------- 事件 ----------

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def _on_new(self):
        self._load_models()  # 懒刷新（打开时再拉，避开 showEvent 时序）
        default_wd = ""
        services = self._last_ctx.get("services") or {}
        get_wd = services.get("get_workdir")
        if callable(get_wd):
            try:
                default_wd = get_wd() or ""
            except Exception:
                default_wd = ""
        self._edit_panel.begin_create(default_wd)
        self._stack.setCurrentIndex(self.PAGE_EDIT)

    def _on_template_clicked(self, tpl: dict):
        """模板点击 → 打开编辑表单（预填模板内容）"""
        self._load_models()
        default_wd = ""
        services = self._last_ctx.get("services") or {}
        get_wd = services.get("get_workdir")
        if callable(get_wd):
            try:
                default_wd = get_wd() or ""
            except Exception:
                default_wd = ""
        self._edit_panel.begin_create_with_template(tpl, default_wd)
        self._stack.setCurrentIndex(self.PAGE_EDIT)

    def _on_edit(self, job_id: str):
        from .controller import CronTasksController

        job = CronTasksController.get_instance().get_job(job_id)
        if job is not None:
            self._load_models()  # 懒刷新
            self._edit_panel.begin_edit(job)
            self._stack.setCurrentIndex(self.PAGE_EDIT)

    def _on_history(self, job_id: str):
        from .controller import CronTasksController

        ctrl = CronTasksController.get_instance()
        job = ctrl.get_job(job_id)
        if job is not None:
            self._history_panel.load(job, ctrl.scheduler.load_runs(job_id))
            self._stack.setCurrentIndex(self.PAGE_HISTORY)

    def _on_save_job(self, job: CronJob):
        from .controller import CronTasksController

        ctrl = CronTasksController.get_instance()
        err = ctrl.save_job(job)
        if err:
            self._edit_panel._title.setText(f"编辑任务 — ❗ {err}")
            return
        self._stack.setCurrentIndex(self.PAGE_LIST)
        self.refresh_jobs()

    # ---------- 刷新 ----------

    def refresh_jobs(self):
        """从 controller 拉最新任务列表重建行卡片"""
        from .controller import CronTasksController

        ctrl = CronTasksController.get_instance()
        jobs = ctrl.scheduler.get_jobs()
        running_id = ctrl.scheduler.is_running_job() and ctrl.scheduler._executor._job.id or ""

        # 重建（任务数量小，简单粗暴即可）
        while self._jobs_layout.count() > 1:
            item = self._jobs_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rows.clear()

        for job in jobs:
            row = JobRowCard(job)
            row.toggleRequested.connect(ctrl.toggle_job)
            row.editRequested.connect(self._on_edit)
            row.historyRequested.connect(self._on_history)
            row.deleteRequested.connect(ctrl.delete_job)
            row.runNowRequested.connect(ctrl.run_now)
            row.stopRequested.connect(ctrl.stop_job)
            row.refresh(job, running=(job.id == running_id))
            self._jobs_layout.insertWidget(self._jobs_layout.count() - 1, row)
            self._rows[job.id] = row

        enabled_cnt = sum(1 for j in jobs if j.enabled)
        self._subtitle.setText(f"· {len(jobs)} 个任务 / {enabled_cnt} 启用" + (" · 任务执行中…" if running_id else ""))
        self._list_stack.setCurrentIndex(0 if not jobs else 1)

    def update_running_row_elapsed(self):
        """心跳专用：仅更新运行中那一行的秒数文字，不重建整表

        行为：
        - 没有运行中任务 → 啥也不做（jobs_changed/jobs_finished 已处理状态切换）
        - 行不存在（用户首次进入列表页等边缘场景）→ 全量 refresh_jobs 兜底
        - 行存在 → 只 refresh 那一个 row（重画 title/meta/status 等），不重 setChecked
          （不闪烁开关、不重新 connect signals）
        """
        from .controller import CronTasksController

        ctrl = CronTasksController.get_instance()
        if not ctrl.scheduler.is_running_job():
            return
        ex = ctrl.scheduler._executor
        if not ex or not ex._job:
            return
        job_id = ex._job.id
        row = self._rows.get(job_id)
        if row is None:
            self.refresh_jobs()  # 行尚未建（边缘情况）→ 全量
            return
        job = next((j for j in ctrl.scheduler.get_jobs() if j.id == job_id), None)
        if job is None:
            return
        row.refresh(job, running=True)

    def _refresh_theme_style(self):
        Colors.refresh()
        self.setStyleSheet(f"""
            #cronTasksCard {{
                background: {Colors.CARD_BG_SOLID};
                border: 1px solid {Colors.BORDER};
                border-radius: 12px;
                {FONT_CSS}
            }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
        """)
        self._subtitle.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; {font_size_css(12)}")
        self._empty_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; {font_size_css(14)}; background: transparent;"
        )
        self._empty_hint.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; {font_size_css(12)}; background: transparent;"
        )
