# -*- coding: utf-8 -*-
"""cron-tasks 卡片组件 — 任务中心卡（列表 + 编辑 + 运行历史，QStackedWidget 三页）

布局参考 autoloop cards.py（full 覆盖对话区、hide_sidebar、design_tokens 配色）。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ComboBox,
    ElevatedCardWidget,
    FluentIcon,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SimpleCardWidget,
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


def _panel_title_css() -> str:
    """面板标题（16px 主色）"""
    return f"color: {Colors.TEXT_PRIMARY}; {font_size_css(16)} {FONT_CSS}"


def _section_title_css() -> str:
    """分组卡标题（13px 主色）"""
    return f"color: {Colors.TEXT_PRIMARY}; {font_size_css(13)} {FONT_CSS}"


def _field_label_css() -> str:
    """字段小标签（11px 次要色）"""
    return f"color: {Colors.TEXT_SECONDARY}; {font_size_css(11)} {FONT_CSS}; font-weight: 500;"


def _make_scroll_transparent(scroll: QScrollArea) -> None:
    """滚动区 viewport 透明化（默认 autoFillBackground 浅灰白，深色模式下成白块）"""
    vp = scroll.viewport()
    vp.setAutoFillBackground(False)
    vp.setStyleSheet("background: transparent;")


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
    "success": "成功",
    "error": "失败",
    "cancelled": "已取消",
    "timeout": "超时",
    "running": "运行中",
}

# 状态对应颜色（用于 JobRowCard 状态行着色，按设计令牌统一）
_STATUS_COLORS = {
    "success": "SUCCESS",
    "error": "ERROR",
    "timeout": "WARNING",
    "cancelled": "TEXT_SECONDARY",
}

# Chip 设计令牌（5 组件复用）：圆角 10px、字号 11px、内边距 2-8px、半透明背景 + 主色文字
_CHIP_RADIUS = 10
_CHIP_PADDING_V, _CHIP_PADDING_H = 2, 8
_CHIP_BG_NEUTRAL = "rgba(138, 143, 156, 0.12)"
_CHIP_BORDER_NEUTRAL = "rgba(138, 143, 156, 0.25)"


class Chip(QLabel):
    """统一风格 chip：圆角矩形 + 半透明背景 + 文字色，圆角/字号/内边距统一
    用 QLabel 自定义以彻底控制样式（qfluentwidgets PillButton 自带主题色难覆盖）。
    """

    def __init__(
        self,
        text: str,
        *,
        color: str,
        bg: str = "transparent",
        border: Optional[str] = None,
        parent=None,
    ):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        border_css = f"border: 1px solid {border};" if border else "border: none;"
        self.setStyleSheet(
            f"background: {bg}; color: {color}; {border_css} "
            f"border-radius: {_CHIP_RADIUS}px; "
            f"padding: {_CHIP_PADDING_V}px {_CHIP_PADDING_H}px; "
            f"{font_size_css(11)} {FONT_CSS}"
        )
        self.setFixedHeight(22)


def make_status_chip(status: str, label: Optional[str] = None) -> Chip:
    """按 status 生成状态 chip：绿/红/橙/灰/蓝"""
    color = getattr(Colors, _STATUS_COLORS.get(status, "TEXT_SECONDARY"), Colors.TEXT_SECONDARY)
    # 半透明背景：取主色的 rgba（颜色推导为近似 alpha 12%）
    bg_map = {
        "success": "rgba(34, 197, 94, 0.14)",
        "error": "rgba(239, 68, 68, 0.14)",
        "timeout": "rgba(245, 158, 11, 0.14)",
        "cancelled": _CHIP_BG_NEUTRAL,
        "running": "rgba(59, 130, 246, 0.14)",
        "": _CHIP_BG_NEUTRAL,
    }
    bg = bg_map.get(status, _CHIP_BG_NEUTRAL)
    return Chip(label or STATUS_LABELS.get(status, status or "未知"), color=color, bg=bg)


def make_meta_chip(text: str) -> Chip:
    """元信息 chip（agent/model/schedule）：次要色 + 浅边框，视觉弱化"""
    return Chip(text, color=Colors.TEXT_SECONDARY, bg=_CHIP_BG_NEUTRAL, border=_CHIP_BORDER_NEUTRAL)


def make_section_card(margin: int = 14) -> ElevatedCardWidget:
    """分组容器：圆角阴影卡片，统一边距（用于 EditPanel / HistoryPanel 分组）"""
    card = ElevatedCardWidget()
    card.setBorderRadius(12)
    return card

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
    {
        "name": "每日 TODO 检查",
        "label": "TODO 检查",
        "mode": "daily",
        "time": "18:00",
        "prompt": "扫描当前工作目录代码，统计新增/已解决的 TODO 与 FIXME，列出未处理项的优先级。",
    },
    {
        "name": "月度预算汇总",
        "label": "预算汇总",
        "mode": "monthly",
        "time": "09:00",
        "month_day": 1,
        "prompt": "汇总上月开支记录（如果工作目录有记账文件），按类别输出占比与异常项。",
    },
    {
        "name": "行业动态周报",
        "label": "行业周报",
        "mode": "weekly",
        "time": "09:00",
        "weekday": 1,
        "prompt": "搜索本周 AI/科技行业重要动态，汇总 5 条要点（标题 + 一句话说明 + 来源链接）。",
    },
    {
        "name": "月度新闻精选",
        "label": "月度新闻",
        "mode": "monthly",
        "time": "10:00",
        "month_day": 1,
        "prompt": "搜索上月值得关注的新闻（科技/财经/国际），精选 8 条整理成月度回顾。",
    },
    {
        "name": "磁盘空间检查",
        "label": "磁盘检查",
        "mode": "daily",
        "time": "12:00",
        "prompt": "检查系统主分区（Windows 看 C/D 盘，macOS 看 /，Linux 看 /home）剩余空间，低于 10GB 时告警并列出最大目录。",
    },
    {
        "name": "临时文件清理",
        "label": "临时清理",
        "mode": "weekly",
        "time": "14:00",
        "weekday": 6,
        "prompt": "扫描工作目录下超过 30 天未访问的 .log/.tmp/__pycache__，列出可清理项清单（不要直接删除）。",
    },
]


def _fmt_dt(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%m-%d %H:%M:%S")
    except ValueError:
        return iso


# 调度模式 → FluentIcon 映射（顶部 hero + 模板区复用）
_MODE_ICON_MAP = {
    "interval": FluentIcon.SYNC,
    "daily": FluentIcon.CALENDAR,
    "weekly": FluentIcon.DATE_TIME,
    "monthly": FluentIcon.CALENDAR,
    "once": FluentIcon.PLAY,
    "advanced": FluentIcon.SETTING,
}


def _tpl_icon_for_mode(mode: str):
    return _MODE_ICON_MAP.get(mode, FluentIcon.CALENDAR)


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
    """单个任务行：现代化分组卡（圆角 + 左侧状态色条 + chip 元信息 + 图标化操作）"""

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
        self._refresh_meta_chips()
        self._refresh_status()
        self._apply_card_accent()

    def _build_ui(self):
        # QFrame + 自定义样式：圆角 12 + 浅背景 + 1px border + 4px 左侧状态色条（运行时绿色 accent）
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # 启用开关
        self._switch = SwitchButton()
        self._switch.setChecked(self._job.enabled)
        self._switch.checkedChanged.connect(lambda _v: self.toggleRequested.emit(self._job.id))
        layout.addWidget(self._switch, 0, Qt.AlignVCenter)

        # 信息区：三行（标题+状态chip / meta chips / 时间信息），用 widget 包装设 SizePolicy.Maximum 让高度不超内容
        info = QVBoxLayout()
        info.setSpacing(6)

        # Row 1: 标题 + 状态 chip
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self._title_label = StrongBodyLabel(self._job.display_label())
        self._title_label.setWordWrap(True)
        row1.addWidget(self._title_label, 1)
        self._status_chip = Chip("未运行", color=Colors.TEXT_SECONDARY, bg="transparent")
        row1.addWidget(self._status_chip, 0, Qt.AlignVCenter)
        info.addLayout(row1)

        # Row 2: 元信息 chips（schedule / agent / model，动态重建）
        # 用 FlowLayout：chips 左对齐 + 自动换行（长 chip 串不会撑爆换行）
        from qfluentwidgets import FlowLayout
        self._meta_chips_row = FlowLayout(needAni=False)
        self._meta_chips_row.setContentsMargins(0, 0, 0, 0)
        self._meta_chips_row.setSpacing(6)
        self._meta_chip_widgets: List[Chip] = []
        info.addLayout(self._meta_chips_row)

        # Row 3: 时间信息行（上次 / 下次，弱化 CaptionLabel）
        self._time_label = CaptionLabel("")
        self._time_label.setWordWrap(True)
        self._time_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; {font_size_css(11)} {FONT_CSS}"
        )
        info.addWidget(self._time_label)
        info.addStretch()  # 内容靠顶部对齐

        # info 包成 widget 便于设 sizePolicy，强制高度不超过 actions 列
        from PyQt5.QtWidgets import QSizePolicy as _SP
        info_w = QWidget()
        info_w.setLayout(info)
        info_w.setSizePolicy(_SP.Expanding, _SP.Maximum)
        layout.addWidget(info_w, 1)

        # 操作按钮（2x2 网格：节省垂直空间，从 4×32=128px 降到 2×32=68px）
        from PyQt5.QtWidgets import QGridLayout
        actions = QGridLayout()
        actions.setSpacing(4)
        self._run_btn = ToolButton(FluentIcon.PLAY)
        self._run_btn.setToolTip("立即运行")
        self._run_btn.setFixedSize(32, 32)
        self._run_btn.clicked.connect(self._on_run_clicked)
        actions.addWidget(self._run_btn, 0, 0, Qt.AlignCenter)
        btn_edit = ToolButton(FluentIcon.EDIT)
        btn_edit.setToolTip("编辑")
        btn_edit.setFixedSize(32, 32)
        btn_edit.clicked.connect(lambda _c: self.editRequested.emit(self._job.id))
        actions.addWidget(btn_edit, 0, 1, Qt.AlignCenter)
        btn_history = ToolButton(FluentIcon.HISTORY)
        btn_history.setToolTip("运行历史")
        btn_history.setFixedSize(32, 32)
        btn_history.clicked.connect(lambda _c: self.historyRequested.emit(self._job.id))
        actions.addWidget(btn_history, 1, 0, Qt.AlignCenter)
        btn_del = ToolButton(FluentIcon.DELETE)
        btn_del.setToolTip("删除")
        btn_del.setFixedSize(32, 32)
        btn_del.clicked.connect(lambda _c: self.deleteRequested.emit(self._job.id))
        actions.addWidget(btn_del, 1, 1, Qt.AlignCenter)
        layout.addLayout(actions)

    def _refresh_status(self):
        """刷新状态 chip + 时间信息行（按运行态/历史态切换）"""
        bg_map = {
            "success": "rgba(34, 197, 94, 0.14)",
            "error": "rgba(239, 68, 68, 0.14)",
            "timeout": "rgba(245, 158, 11, 0.14)",
            "cancelled": _CHIP_BG_NEUTRAL,
            "running": "rgba(59, 130, 246, 0.14)",
            "": _CHIP_BG_NEUTRAL,
        }
        if self._running:
            color = Colors.REALTIME_SUCCESS
            bg = bg_map["running"]
            text = "运行中"
            elapsed = 0
            if self._job.last_run_at:
                try:
                    elapsed = max(
                        0,
                        int(
                            (
                                datetime.now()
                                - datetime.fromisoformat(self._job.last_run_at)
                            ).total_seconds()
                        ),
                    )
                except Exception:
                    pass
            time_text = f"正在执行 · 已运行 {elapsed}s"
        else:
            status = self._job.last_status
            color_attr = _STATUS_COLORS.get(status, "TEXT_SECONDARY")
            color = getattr(Colors, color_attr, Colors.TEXT_SECONDARY)
            bg = bg_map.get(status, _CHIP_BG_NEUTRAL)
            text = STATUS_LABELS.get(status, status or "未运行")
            parts = []
            if status and self._job.last_run_at:
                parts.append(f"上次 {_fmt_dt(self._job.last_run_at)}")
            elif not status:
                parts.append("尚未运行")
            if self._job.enabled and self._job.next_run_at:
                parts.append(f"下次 {_fmt_dt(self._job.next_run_at)}")
            elif not self._job.enabled:
                parts.append("已禁用")
            time_text = "  ·  ".join(parts) if parts else "—"
        # 状态 chip：保留实例动态改色
        self._status_chip.setText(text)
        self._status_chip.setStyleSheet(
            f"background: {bg}; color: {color}; border: none; "
            f"border-radius: {_CHIP_RADIUS}px; "
            f"padding: {_CHIP_PADDING_V}px {_CHIP_PADDING_H}px; "
            f"{font_size_css(11)} {FONT_CSS}"
        )
        self._time_label.setText(time_text)

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

    def _refresh_meta_chips(self):
        """重建 meta chips（schedule / agent / model）—— refresh 时调用（FlowLayout 天然左对齐+自动换行，无需 addStretch）"""
        for chip in self._meta_chip_widgets:
            self._meta_chips_row.removeWidget(chip)
            chip.setParent(None)
            chip.deleteLater()
        self._meta_chip_widgets.clear()
        job = self._job
        self._add_meta_chip(job.schedule_desc())
        if job.agent:
            self._add_meta_chip(f"agent · {job.agent}")
        if job.model_key:
            model_disp = str(job.model_key).partition("||")[2] or job.model_key
            self._add_meta_chip(f"model · {model_disp}")

    def _add_meta_chip(self, text: str) -> Chip:
        chip = make_meta_chip(text)
        self._meta_chips_row.addWidget(chip)
        self._meta_chip_widgets.append(chip)
        return chip

    def _apply_card_accent(self):
        """按运行态切换左侧色条（绿色 accent）+ 卡片描边"""
        Colors.refresh()
        accent = Colors.REALTIME_SUCCESS if self._running else Colors.BORDER
        border_w = 1
        self.setStyleSheet(f"""
            #cronJobRowCard {{
                background: {Colors.CARD_BG_SOLID};
                border: {border_w}px solid {Colors.BORDER};
                border-left: 4px solid {accent};
                border-radius: 12px;
                {FONT_CSS}
            }}
            #cronJobRowCard:hover {{
                border-color: {Colors.INPUT_FOCUS_BORDER};
            }}
        """)
        self.setProperty("running", "true" if self._running else "false")

    def refresh(self, job: CronJob, running: bool = False):
        self._job = job
        was_running = self._running
        self._running = running
        self._apply_run_state()
        self._refresh_meta_chips()
        self._title_label.setText(job.display_label())
        self._switch.setChecked(job.enabled)
        self._refresh_status()
        if running != was_running:
            self._apply_card_accent()


# ============================================================
#  编辑面板
# ============================================================


class _ResponsiveFormBody(QWidget):
    """编辑表单响应式主体：窄宽度三卡纵排；宽宽度左(任务)右(调度+通知)双列"""

    WIDE_MIN_WIDTH = 720  # 触发双列的容器宽度阈值(px)

    def __init__(self, s_task: QWidget, s_schedule: QWidget, s_notify: QWidget, parent=None):
        super().__init__(parent)
        self._cards = (s_task, s_schedule, s_notify)
        self._wide = False
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(14)
        self._apply(wide=False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        wide = self.width() >= self.WIDE_MIN_WIDTH
        if wide != self._wide:
            self._apply(wide=wide)

    def _apply(self, wide: bool):
        """按宽度切换网格布局（widget 仅移动位置，不销毁重建，编辑内容不丢）"""
        self._wide = wide
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        s1, s2, s3 = self._cards
        if wide:
            # 左列：任务卡（纵跨两行）；右列：调度卡在上、通知卡在下
            self._grid.addWidget(s1, 0, 0, 2, 1)
            self._grid.addWidget(s2, 0, 1)
            self._grid.addWidget(s3, 1, 1)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 1)
            self._grid.setRowStretch(0, 3)  # 任务+调度卡为主伸缩
            self._grid.setRowStretch(1, 1)
        else:
            self._grid.addWidget(s1, 0, 0)
            self._grid.addWidget(s2, 1, 0)
            self._grid.addWidget(s3, 2, 0)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 0)  # 重置宽模式残留的第 1 列拉伸，避免单列右侧空白
            self._grid.setRowStretch(0, 1)  # 任务/调度卡分摊纵向余量，填满面板
            self._grid.setRowStretch(1, 1)
            self._grid.setRowStretch(2, 0)
            self._grid.setRowStretch(3, 0)


class JobEditPanel(QWidget):
    """新建/编辑任务表单"""

    saveRequested = pyqtSignal(object)  # CronJob
    cancelRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job: Optional[CronJob] = None  # None = 新建
        self._draft = ScheduleDraft()
        self._field_labels: List[QLabel] = []            # 主题切换需重刷的字段小标签
        self._section_titles: List[StrongBodyLabel] = []  # 分组卡标题
        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self):
        # 外层：顶部 hero header + 滚动内容
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶部 hero header：图标 + 标题 + 取消/保存
        header_w = QFrame()
        header_w.setObjectName("editHeader")
        h_layout = QHBoxLayout(header_w)
        h_layout.setContentsMargins(20, 14, 16, 14)
        h_layout.setSpacing(8)
        icon_w = ToolButton(FluentIcon.EDIT)
        icon_w.setIconSize(QSize(18, 18))
        icon_w.setFixedSize(24, 24)
        icon_w.setEnabled(False)
        icon_w.setStyleSheet("background: transparent; border: none;")
        h_layout.addWidget(icon_w, 0, Qt.AlignVCenter)
        self._title = StrongBodyLabel("新建任务")
        self._title.setStyleSheet(_panel_title_css())
        h_layout.addWidget(self._title, 1)
        self._cancel_btn = PushButton("取消")
        self._cancel_btn.clicked.connect(self.cancelRequested.emit)
        h_layout.addWidget(self._cancel_btn)
        self._save_btn = PrimaryPushButton(FluentIcon.SAVE, "保存")
        self._save_btn.clicked.connect(self._on_save)
        h_layout.addWidget(self._save_btn)
        outer.addWidget(header_w)

        # 滚动内容区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content_w = QWidget()
        scroll.setWidget(content_w)
        _make_scroll_transparent(scroll)
        self._scroll = scroll  # 主题刷新时重申 viewport 透明
        outer.addWidget(scroll, 1)

        layout = QVBoxLayout(content_w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # 局部助手：纵向 label + 控件（label 11px 次要色 + 控件占满）
        def _labeled(label_text: str, widget: QWidget) -> QVBoxLayout:
            v = QVBoxLayout()
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(4)
            lbl = CaptionLabel(label_text)
            lbl.setStyleSheet(_field_label_css())
            self._field_labels.append(lbl)
            v.addWidget(lbl)
            v.addWidget(widget)
            return v

        # 局部助手：分组卡片（标题 13px + 内层 VBox padding 16/14/16/14）
        def _section(title_text: str):
            card = ElevatedCardWidget()
            card.setBorderRadius(12)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.setSpacing(10)
            hl = StrongBodyLabel(title_text)
            hl.setStyleSheet(_section_title_css())
            self._section_titles.append(hl)
            cl.addWidget(hl)
            return card, cl

        # === Section 1: 任务 ===
        s1, s1l = _section("任务")
        self._label_edit = LineEdit()
        self._label_edit.setPlaceholderText("任务名称（可选，默认取提示词首行）")
        s1l.addLayout(_labeled("名称", self._label_edit))
        self._prompt_edit = TextEdit()
        self._prompt_edit.setPlaceholderText(
            "📝 到期后要执行的提示词（如：检查 D:/work 目录下今日新增文件并汇总）..."
        )
        self._prompt_edit.setMinimumHeight(72)
        # 纵向 Ignored：消除 TextEdit 默认 sizeHint 膨胀（防止面板虚高出滚动条）
        self._prompt_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        # label 与控件分开挂：TextEdit 直接带 stretch=1，确保独占卡片纵向余量
        prompt_lbl = CaptionLabel("提示词")
        prompt_lbl.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; {font_size_css(11)} {FONT_CSS}; font-weight: 500;"
        )
        s1l.addWidget(prompt_lbl)
        s1l.addWidget(self._prompt_edit, 1)

        # === Section 2: 调度与执行 ===
        s2, s2l = _section("调度与执行")
        self._mode_combo = ComboBox()
        self._mode_combo.addItems([SCHEDULE_MODE_LABELS[m] for m in SCHEDULE_MODES])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        s2l.addLayout(_labeled("调度方式", self._mode_combo))

        # 调度详情区（保留 4 行控件供 _on_mode_changed 切换显隐）
        self._schedule_details = QWidget()
        sd_layout = QVBoxLayout(self._schedule_details)
        sd_layout.setContentsMargins(0, 0, 0, 0)
        sd_layout.setSpacing(8)

        # 间隔：数值 + 单位（interval 模式）
        self._interval_row = QWidget()
        irow = QHBoxLayout(self._interval_row)
        irow.setContentsMargins(0, 0, 0, 0)
        irow.setSpacing(6)
        self._interval_spin = SpinBox()
        self._interval_spin.setRange(1, 999)
        # setValue 延后到 signal connect 之后（见本方法末尾）
        self._interval_unit_combo = ComboBox()
        self._interval_unit_combo.addItems(["分钟", "小时", "天"])
        irow.addWidget(self._interval_spin)
        irow.addWidget(self._interval_unit_combo)
        irow.addStretch()
        sd_layout.addWidget(self._interval_row)

        # 时间行：[星期多选(仅每周)] [时间] [几号(仅每月)]
        self._time_row = QWidget()
        trow = QHBoxLayout(self._time_row)
        trow.setContentsMargins(0, 0, 0, 0)
        trow.setSpacing(6)
        self._weekday_checks: List[QCheckBox] = []
        for _lbl, _dow in zip(("一", "二", "三", "四", "五", "六", "日"), (1, 2, 3, 4, 5, 6, 0)):
            cb = CheckBox(_lbl)
            cb.stateChanged.connect(self._refresh_preview)
            self._weekday_checks.append(cb)
            trow.addWidget(cb)
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setStyleSheet(self._datetime_style())
        from PyQt5.QtCore import QTime

        self._time_edit.setTime(QTime(9, 0))
        trow.addWidget(self._time_edit)
        self._monthday_spin = SpinBox()
        self._monthday_spin.setRange(1, 31)
        self._monthday_spin.setValue(1)
        trow.addWidget(self._monthday_spin)
        trow.addStretch()
        sd_layout.addWidget(self._time_row)

        # 单次：日期时间
        from PyQt5.QtWidgets import QDateTimeEdit

        self._once_edit = QDateTimeEdit()
        self._once_edit.setCalendarPopup(True)
        self._once_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._once_edit.setStyleSheet(self._datetime_style())
        self._once_edit.calendarWidget().setStyleSheet(self._calendar_style())
        from PyQt5.QtCore import QDateTime as _QDT

        sd_layout.addWidget(self._once_edit)

        # 高级 cron
        self._cron_edit = LineEdit()
        self._cron_edit.setPlaceholderText("分 时 日 月 周，如 0 9 * * 1-5")
        sd_layout.addWidget(self._cron_edit)
        s2l.addWidget(self._schedule_details)

        # 调度预览 chip（圆角边框 + 浅背景，更现代）
        self._preview_label = BodyLabel("")
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet(self._preview_style())
        s2l.addWidget(self._preview_label)

        # 执行模型 + 智能体（横向两列节省垂直空间）
        self._model_combo = ComboBox()
        self._agent_combo = ComboBox()
        exec_row = QHBoxLayout()
        exec_row.setSpacing(10)
        exec_row.addLayout(_labeled("执行模型", self._model_combo), 1)
        exec_row.addLayout(_labeled("执行智能体", self._agent_combo), 1)
        s2l.addLayout(exec_row)
        s2l.addStretch(1)  # 卡片被拉伸时内部吸收余量

        # === Section 3: 通知与目录 ===
        s3, s3l = _section("通知与目录")
        self._notify_combo = ComboBox()
        self._notify_combo.addItems(["默认弹窗", "系统通知", "Gateway 消息"])
        self._notify_combo.currentIndexChanged.connect(self._on_notify_mode_changed)
        s3l.addLayout(_labeled("完成通知", self._notify_combo))

        # notify_target_row（gateway 模式展开，纵向 label + combo）
        self._notify_target_row = QWidget()
        nrow = QVBoxLayout(self._notify_target_row)
        nrow.setContentsMargins(0, 0, 0, 0)
        nrow.setSpacing(4)
        target_lbl = CaptionLabel("发送目标")
        target_lbl.setStyleSheet(_field_label_css())
        self._field_labels.append(target_lbl)
        nrow.addWidget(target_lbl)
        self._notify_target_combo = ComboBox()
        nrow.addWidget(self._notify_target_combo)
        self._notify_target_row.setVisible(False)
        s3l.addWidget(self._notify_target_row)

        # 工作目录：行内 line + browse 按钮
        self._workdir_edit = LineEdit()
        self._workdir_edit.setPlaceholderText("留空 = 当前工作目录")
        browse_btn = ToolButton(FluentIcon.FOLDER)
        browse_btn.setToolTip("选择目录")
        browse_btn.setFixedSize(32, 32)
        browse_btn.clicked.connect(self._browse_workdir)
        wd_widget = QWidget()
        wd_layout = QHBoxLayout(wd_widget)
        wd_layout.setContentsMargins(0, 0, 0, 0)
        wd_layout.setSpacing(6)
        wd_layout.addWidget(self._workdir_edit, 1)
        wd_layout.addWidget(browse_btn)
        s3l.addLayout(_labeled("工作目录", wd_widget))

        # 响应式主体：窄=单列纵排；宽(≥720px)=左(任务) 右上(调度) 右下(通知) 双列
        body = _ResponsiveFormBody(s1, s2, s3)
        layout.addWidget(body, 1)  # 拉满内容区，消除纵向空白/滚动条

        # 联动预览刷新（signal connect 必须在 setValue 之前）
        self._interval_spin.valueChanged.connect(self._refresh_preview)
        self._interval_unit_combo.currentIndexChanged.connect(self._refresh_preview)
        self._time_edit.timeChanged.connect(self._refresh_preview)
        self._monthday_spin.valueChanged.connect(self._refresh_preview)
        self._once_edit.dateTimeChanged.connect(self._refresh_preview)
        self._cron_edit.textChanged.connect(self._refresh_preview)

        # 默认值统一在所有 signal 连接完成后设置（避免控件未建好就触发 refresh）
        self._interval_spin.setValue(30)
        self._weekday_checks[0].setChecked(True)  # 默认周一
        self._once_edit.setDateTime(_QDT.currentDateTime().addDays(1))
        self._refresh_preview()

    def _preview_style(self) -> str:
        return (
            f"color: {Colors.TEXT_SECONDARY}; {font_size_css(12)} {FONT_CSS}; "
            f"background: {Colors.CARD_BG_SOLID}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 8px; padding: 8px 12px;"
        )

    def _datetime_style(self) -> str:
        """原生时间/日期选择框深浅色适配（QTimeEdit/QDateTimeEdit 默认黑字）"""
        return (
            f"QTimeEdit, QDateTimeEdit {{ background: {Colors.CONTENT_BG}; "
            f"color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 6px; padding: 4px 8px; {font_size_css(13)} {FONT_CSS} }} "
            f"QTimeEdit:focus, QDateTimeEdit:focus {{ border-color: {Colors.INPUT_FOCUS_BORDER}; }} "
            f"QTimeEdit::up-button, QDateTimeEdit::up-button, "
            f"QTimeEdit::down-button, QDateTimeEdit::down-button {{ width: 0px; }}"
        )

    def _calendar_style(self) -> str:
        """日历弹窗深浅色适配（原生 QCalendarWidget 深色下全黑）"""
        return f"""
        QCalendarWidget QWidget {{ alternate-background-color: {Colors.CONTENT_BG}; }}
        QCalendarWidget QAbstractItemView:enabled {{
            color: {Colors.TEXT_PRIMARY};
            background-color: {Colors.CARD_BG_SOLID};
            selection-background-color: {Colors.INPUT_FOCUS_BORDER};
            selection-color: #ffffff;
            outline: 0;
        }}
        QCalendarWidget QAbstractItemView:disabled {{ color: {Colors.TEXT_MUTED}; }}
        QCalendarWidget QToolButton {{
            color: {Colors.TEXT_PRIMARY};
            background-color: transparent;
            border-radius: 6px;
            padding: 4px 8px;
            {font_size_css(13)} {FONT_CSS}
        }}
        QCalendarWidget QToolButton:hover {{ background-color: {Colors.CARD_BG_DIM}; }}
        QCalendarWidget #qt_calendar_navigationbar {{
            background-color: {Colors.CONTENT_BG};
            padding: 6px;
        }}
        QCalendarWidget #qt_calendar_monthbutton::menu-indicator {{ image: none; }}
        QCalendarWidget QSpinBox {{
            background-color: {Colors.CARD_BG_SOLID};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER};
        }}
        QCalendarWidget QMenu {{
            background-color: {Colors.CARD_BG_SOLID};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER};
        }}
        QCalendarWidget QMenu::item {{ padding: 4px 16px; }}
        QCalendarWidget QMenu::item:selected {{ background: {Colors.INPUT_FOCUS_BORDER}; }}
        """

    def refresh_theme(self):
        """主题切换刷新（theme_manager dispatch 回调）"""
        Colors.refresh()
        self._title.setStyleSheet(_panel_title_css())
        for lbl in self._field_labels:
            lbl.setStyleSheet(_field_label_css())
        for lbl in self._section_titles:
            lbl.setStyleSheet(_section_title_css())
        self._preview_label.setStyleSheet(self._preview_style())
        self._time_edit.setStyleSheet(self._datetime_style())
        self._once_edit.setStyleSheet(self._datetime_style())
        self._once_edit.calendarWidget().setStyleSheet(self._calendar_style())

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
            # 去重：同一 platform:chat_id 只保留最近活跃的一条
            seen = set()
            for s in sessions:
                p = getattr(s.platform, "value", s.platform)
                key = f"{p}:{s.chat_id}"
                if key in seen:
                    continue
                seen.add(key)
                combo.addItem(s.display_name, key)
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶部 hero header：图标 + 标题 + 返回按钮
        header_w = QFrame()
        header_w.setObjectName("historyHeader")
        h_layout = QHBoxLayout(header_w)
        h_layout.setContentsMargins(20, 14, 16, 14)
        h_layout.setSpacing(8)
        icon_w = ToolButton(FluentIcon.HISTORY)
        icon_w.setIconSize(QSize(18, 18))
        icon_w.setFixedSize(24, 24)
        icon_w.setEnabled(False)
        icon_w.setStyleSheet("background: transparent; border: none;")
        h_layout.addWidget(icon_w, 0, Qt.AlignVCenter)
        self._title = StrongBodyLabel("运行历史")
        self._title.setStyleSheet(_panel_title_css())
        h_layout.addWidget(self._title, 1)
        back_btn = PushButton("返回")
        back_btn.setIcon(FluentIcon.RETURN)
        back_btn.clicked.connect(self.backRequested.emit)
        h_layout.addWidget(back_btn)
        outer.addWidget(header_w)

        # 内容容器
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 16)
        content_layout.setSpacing(10)

        # 任务上下文摘要（次要色 12px）
        self._ctx_label = BodyLabel("")
        self._ctx_label.setWordWrap(True)
        self._ctx_label.setStyleSheet(self._ctx_style())
        content_layout.addWidget(self._ctx_label)

        # 左右双栏：左侧时间线列表 + 右侧详情卡
        body = QHBoxLayout()
        body.setSpacing(12)

        # 左：时间线列表（圆角卡片样式 + 选中态高亮）
        self._list = QListWidget()
        self._list.setMinimumWidth(240)
        self._list.setMaximumWidth(320)
        self._list.setStyleSheet(self._list_style())
        self._list.itemClicked.connect(self._on_item_clicked)
        body.addWidget(self._list, 3)

        # 右：详情卡（ElevatedCardWidget + 字段网格 + 响应全文）
        self._detail_card = ElevatedCardWidget()
        self._detail_card.setBorderRadius(12)
        detail_layout = QVBoxLayout(self._detail_card)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(10)

        # 详情字段区（运行状态/耗时/智能体/模型/错误 等网格）
        self._fields_layout = QVBoxLayout()
        self._fields_layout.setSpacing(6)
        detail_layout.addLayout(self._fields_layout)

        # 分隔线
        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.HLine)
        self._sep.setStyleSheet(self._sep_style())
        detail_layout.addWidget(self._sep)

        # 响应全文区
        self._resp_hdr = CaptionLabel("响应全文")
        self._resp_hdr.setStyleSheet(_field_label_css())
        detail_layout.addWidget(self._resp_hdr)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setLineWrapMode(QTextEdit.WidgetWidth)
        self._detail.setStyleSheet(self._detail_style())
        detail_layout.addWidget(self._detail, 1)
        body.addWidget(self._detail_card, 5)
        content_layout.addLayout(body, 1)
        outer.addWidget(content, 1)

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

    # ---------- 主题 ----------

    def _ctx_style(self) -> str:
        return f"color: {Colors.TEXT_MUTED}; {font_size_css(12)} {FONT_CSS}"

    def _list_style(self) -> str:
        return (
            f"QListWidget {{ background: {Colors.CARD_BG_SOLID}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 12px; "
            f"padding: 6px; {font_size_css(13)} {FONT_CSS} }} "
            f"QListWidget::item {{ padding: 8px 10px; border-radius: 8px; "
            f"margin: 2px 0; }} "
            f"QListWidget::item:hover {{ background: rgba(125, 211, 252, 0.08); }} "
            f"QListWidget::item:selected {{ background: rgba(125, 211, 252, 0.15); "
            f"color: {Colors.TEXT_PRIMARY}; }}"
        )

    def _sep_style(self) -> str:
        return f"background: {Colors.BORDER}; max-height: 1px; border: none;"

    def _detail_style(self) -> str:
        return (
            f"QTextEdit {{ background: {Colors.CARD_BG_SOLID}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 8px; "
            f"padding: 10px 12px; {font_size_css(13)} {FONT_CSS} }}"
        )

    def refresh_theme(self):
        """主题切换刷新（theme_manager dispatch 回调）"""
        Colors.refresh()
        self._title.setStyleSheet(_panel_title_css())
        self._ctx_label.setStyleSheet(self._ctx_style())
        self._list.setStyleSheet(self._list_style())
        self._sep.setStyleSheet(self._sep_style())
        self._resp_hdr.setStyleSheet(_field_label_css())
        self._detail.setStyleSheet(self._detail_style())


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
        # 主题实时刷新：主程序 theme_manager reload 时回调 refresh_theme()
        try:
            from app.utils.theme_manager import theme_manager

            theme_manager.register_refresh_target(self)
        except Exception:
            pass

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
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        # Hero header：图标 + 大标题 + 实时统计副标题 + 操作按钮
        hero = QHBoxLayout()
        hero.setSpacing(12)
        icon_w = ToolButton(FluentIcon.STOP_WATCH)
        icon_w.setIconSize(QSize(20, 20))
        icon_w.setFixedSize(26, 26)
        icon_w.setEnabled(False)
        icon_w.setStyleSheet("background: transparent; border: none;")
        hero.addWidget(icon_w, 0, Qt.AlignVCenter)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self._title_label = StrongBodyLabel("定时任务")
        self._title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; {font_size_css(18)} {FONT_CSS}"
        )
        title_box.addWidget(self._title_label)
        self._subtitle = CaptionLabel("")  # 实时统计：共 N 个 · X 启用 · Y 运行中
        self._subtitle.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; {font_size_css(12)} {FONT_CSS}"
        )
        title_box.addWidget(self._subtitle)
        hero.addLayout(title_box, 1)

        self._new_btn = PrimaryPushButton(FluentIcon.ADD, "新建任务")
        self._new_btn.clicked.connect(self._on_new)
        hero.addWidget(self._new_btn, 0, Qt.AlignVCenter)

        close_btn = TransparentToolButton(FluentIcon.CLOSE)
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self._on_close)
        hero.addWidget(close_btn, 0, Qt.AlignVCenter)
        layout.addLayout(hero)
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
        _make_scroll_transparent(scroll)
        self._jobs_scroll = scroll  # 主题刷新时重申 viewport 透明
        lp_layout.addWidget(scroll)
        self._list_stack.addWidget(list_page)

        # 页 1 整体：内层栈（空提示/列表）+ 模板区常驻
        page_list_outer = QWidget()
        plo_layout = QVBoxLayout(page_list_outer)
        plo_layout.setContentsMargins(0, 0, 0, 0)
        plo_layout.setSpacing(0)
        plo_layout.addWidget(self._list_stack, 1)

        # 模板区（常驻）：Flow 布局快捷模板按钮（带模式图标）
        from qfluentwidgets import FlowLayout

        tpl_wrap = QWidget()
        tpl_layout = QVBoxLayout(tpl_wrap)
        tpl_layout.setContentsMargins(0, 12, 0, 0)
        tpl_layout.setSpacing(8)
        tpl_header = BodyLabel("常见任务模板 · 点击预填")
        tpl_header.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; {font_size_css(12)} {FONT_CSS}; font-weight: 500;"
        )
        tpl_layout.addWidget(tpl_header)
        self._tpl_flow = FlowLayout(needAni=False)
        self._tpl_flow.setContentsMargins(0, 0, 0, 0)
        for tpl in JOB_TEMPLATES:
            btn = PushButton(tpl["name"])
            btn.setIcon(_tpl_icon_for_mode(tpl.get("mode", "daily")))
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

        # 热重载边界防御：多次 reload 后残留的旧实例可能属性不全，跳过避免崩
        if not hasattr(self, "_jobs_layout"):
            return

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

    def refresh_theme(self):
        """主题切换刷新（theme_manager dispatch 回调）：主卡/编辑/历史面板/行卡统一重取主题色"""
        # 同步 qfluent 全局主题（ElevatedCardWidget 等自绘背景依赖它；主程序个别刷新路径可能未调 setTheme）
        try:
            from qfluentwidgets import Theme, setTheme
            from app.utils.theme_manager import theme_manager as _tm

            setTheme(Theme.LIGHT if _tm.is_light_theme() else Theme.DARK)
        except Exception:
            pass
        # 滚动区 viewport 重申透明
        for sc in (self._jobs_scroll, self._edit_panel._scroll):
            _make_scroll_transparent(sc)
        self._refresh_theme_style()
        self._edit_panel.refresh_theme()
        self._history_panel.refresh_theme()
        try:
            self.refresh_jobs()  # 行卡按新主题重建
        except Exception:
            pass

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
