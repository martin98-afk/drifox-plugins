# -*- coding: utf-8 -*-
"""CronChat 主卡 — 任务列表 / 编辑页 / 运行记录（QStackedWidget 三页编排）

布局参考「自动化任务」设计稿：
- 列表页：胶囊 Tab（定时任务/运行记录）+ 空状态引导 + 任务卡列表 + 模板网格
- 编辑页：面包屑 + 名称/提示词/执行频率（周期·按间隔·单次）/生效区间/开关
- 记录页：运行记录流（状态/耗时/结果摘要，点击展开全文）
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QTime, QDate, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    ComboBox,
    LineEdit,
    PushButton,
    PrimaryPushButton,
    SwitchButton,
    ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from app.utils.design_tokens import Colors, font_size_css, scale_font_size
from app.utils.utils import get_font_family_css

from cron_core.models import (
    WEEKDAY_LABELS,
    CronTask,
    RunRecord,
)
from cron_core.store import CronStore

FONT_CSS = get_font_family_css()


def _card_bg(alpha: int) -> str:
    """Cards.card(alpha) 替身 — Colors.CARD_BG 是带 {alpha} 占位符的模板字符串"""
    Colors.refresh()
    return Colors.CARD_BG.format(alpha=alpha)


def _configure_switch(switch):
    """SwitchStyles.configure(switch) 替身 — 关掉文字标签 + 固定宽度"""
    switch.setOnText("")
    switch.setOffText("")
    switch.setFixedWidth(50)

# ── 内置任务模板（标题 / 描述 / 预填提示词 / 预设调度）──────────────

TEMPLATES = [
    {
        "icon": "📰", "title": "每日 AI 新闻推送",
        "desc": "关注当天 AI 领域的重要动态，侧重 AI coding 与具身智能…",
        "prompt": "关注当天 AI 领域的重要动态，侧重 AI coding 与具身智能方向。筛选 3-5 条有价值的信息，简要说明事件内容及值得关注的原因。",
        "schedule": {"schedule_type": "daily", "time_hhmm": "09:00"},
    },
    {
        "icon": "🔤", "title": "每日 5 个英语单词",
        "desc": "每天推荐 5 个高频实用英语单词，包含音标、例句…",
        "prompt": "每天推荐 5 个高频实用英语单词，包含音标、词性、英文例句与中文翻译，并给每个单词配一条记忆技巧。",
        "schedule": {"schedule_type": "daily", "time_hhmm": "08:00"},
    },
    {
        "icon": "🌙", "title": "每日儿童睡前故事",
        "desc": "生成 3-5 分钟可读的温和睡前故事，结尾有温暖道理…",
        "prompt": "生成一个 3-5 分钟可读的温和儿童睡前故事，主角是一只小狐狸和它的朋友，情节温馨不刺激，结尾自然引出一个简单的成长道理。",
        "schedule": {"schedule_type": "daily", "time_hhmm": "20:30"},
    },
    {
        "icon": "📋", "title": "每周工作周报",
        "desc": "每周五汇总本周仓库 PR 与 Issue 进展，输出结构化周报…",
        "prompt": "汇总本周当前工作目录仓库的 PR 与 Issue 进展（使用 git 与文件工具查看），输出结构化周报：本周完成 / 进行中 / 下周计划 / 风险点。若无法获取仓库信息则输出通用周报模板并说明原因。",
        "schedule": {"schedule_type": "weekly", "weekdays": [4], "time_hhmm": "17:00"},
    },
    {
        "icon": "🎬", "title": "经典电影推荐",
        "desc": "推荐一部高分经典电影，介绍剧情与推荐理由，不剧透…",
        "prompt": "推荐一部高分经典电影，简要介绍剧情背景与推荐理由（不剧透关键转折），并说明适合的观看心情与人群。",
        "schedule": {"schedule_type": "weekly", "weekdays": [5], "time_hhmm": "20:00"},
    },
    {
        "icon": "📅", "title": "历史上的今天",
        "desc": "从科技、电影、音乐等领域挑选一件历史上的今天大事…",
        "prompt": "从科技、电影、音乐等领域挑选一件历史上今天（以执行日期为准）发生的重要事件，讲述事件经过与它带来的深远影响。",
        "schedule": {"schedule_type": "daily", "time_hhmm": "12:00"},
    },
    {
        "icon": "💡", "title": "每日一个为什么",
        "desc": "每天抛出一个有趣的科学问题，先提问再通俗解答…",
        "prompt": "每天抛出一个有趣的科学问题（领域随机轮换：物理/生物/天文/心理…），先用一句话提问引起好奇，再给出 200 字以内的通俗解答。",
        "schedule": {"schedule_type": "daily", "time_hhmm": "10:00"},
    },
    {
        "icon": "☎️", "title": "父母联系提醒",
        "desc": "每周日 10:00 提醒你给家人打电话，附聊天话题建议…",
        "prompt": "提醒我给父母打电话或视频。附上：1) 一句温暖的问候语建议；2) 两个本周可以聊的话题（如家乡近况、健康、家庭安排）。",
        "schedule": {"schedule_type": "weekly", "weekdays": [6], "time_hhmm": "10:00"},
    },
    {
        "icon": "🏥", "title": "体检预约提醒",
        "desc": "提醒确认体检预约与注意事项（空腹、带证件等）…",
        "prompt": "提醒我确认体检预约。列出体检前注意事项清单：是否需要空腹、携带证件、穿着建议、常规检查项目说明。",
        "schedule": {"schedule_type": "once", "once_datetime": "", "time_hhmm": "07:00"},
    },
    {
        "icon": "💼", "title": "面试准备提醒",
        "desc": "工作日每 2 小时提醒复习大模型面试要点，每次一个主题…",
        "prompt": "面试准备时间到。从大模型面试题库中挑一个主题（Transformer/注意力机制/RAG/微调/推理优化/Agent 等轮换），给出核心要点复习卡（3-5 条）。",
        "schedule": {"schedule_type": "interval", "interval_minutes": 120},
    },
    {
        "icon": "📝", "title": "会议前准备",
        "desc": "提醒整理议题、目标与预期产出，带着方案进会议室…",
        "prompt": "提醒我整理会议准备：列出 1) 本次会议议题清单模板；2) 目标与预期产出描述框架；3) 三条提高会议效率的建议。",
        "schedule": {"schedule_type": "daily", "time_hhmm": "09:30"},
    },
    {
        "icon": "🖼️", "title": "可爱萌宠手机壁纸",
        "desc": "随机从 7 种风格中挑一种，描述一张萌宠壁纸画面…",
        "prompt": "随机从 7 种风格（水彩/像素/扁平插画/油画/赛博朋克/极简/吉卜力）中挑选一种，为一张竖屏手机壁纸描述完整画面：主体萌宠、配色、构图、氛围细节，可直接用于文生图。",
        "schedule": {"schedule_type": "daily", "time_hhmm": "08:30"},
    },
]


def _fmt_time(iso_text: str) -> str:
    """ISO 时间 → 人类可读（MM-DD HH:MM）"""
    text = str(iso_text or "").strip()
    if not text:
        return "—"
    try:
        dt = datetime.fromisoformat(text)
        return dt.strftime("%m-%d %H:%M")
    except ValueError:
        return text[:16]


# ============================================================
#  胶囊 Tab
# ============================================================


class _PillTab(QFrame):
    """顶部胶囊切换（定时任务 / 运行记录）"""

    changed = pyqtSignal(int)

    def __init__(self, tabs: List[str], parent=None):
        super().__init__(parent)
        self._labels = tabs
        self._index = 0
        self._btn_group = QButtonGroup(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for index, label in enumerate(tabs):
            btn = PushButton(f"⏰ {label}" if index == 0 else f"🕘 {label}")
            btn.setCheckable(True)
            btn.setChecked(index == 0)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=index: self.set_index(i))
            self._btn_group.addButton(btn, index)
            layout.addWidget(btn)
        self._refresh_style()

    def set_index(self, index: int):
        if index == self._index:
            return
        self._index = index
        self._refresh_style()
        self.changed.emit(index)

    def _refresh_style(self):
        for btn in self._btn_group.buttons():
            index = self._btn_group.id(btn)
            checked = index == self._index
            bg = Colors.TAB_ACTIVE_BG if checked else "transparent"
            fg = Colors.TEXT_PRIMARY if checked else Colors.TEXT_SECONDARY
            border = Colors.BORDER if checked else "transparent"
            btn.setStyleSheet(
                f"""
                PushButton {{
                    background: {bg}; color: {fg};
                    border: 1px solid {border}; border-radius: {scale_font_size(8)}px;
                    padding: {scale_font_size(6)}px {scale_font_size(16)}px;
                    {FONT_CSS} font-size: {font_size_css(scale_font_size(13))};
                }}
                PushButton:hover {{ background: {Colors.HOVER_BG}; }}
                """
            )


# ============================================================
#  列表页
# ============================================================


class TaskListPage(QWidget):
    """任务列表 + 空状态 + 模板网格"""

    editRequested = pyqtSignal(object)  # CronTask（编辑已有）
    createRequested = pyqtSignal(object)  # dict 模板（新建预填）
    runNowRequested = pyqtSignal(object)  # CronTask
    deleteRequested = pyqtSignal(object)  # CronTask
    toggleRequested = pyqtSignal(object, bool)  # CronTask, enabled

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_cards: List[QFrame] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(scale_font_size(12))

        # 滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        root.addWidget(scroll, 1)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        scroll.setWidget(body)
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(scale_font_size(4), scale_font_size(4), scale_font_size(8), scale_font_size(8))
        self._body_layout.setSpacing(scale_font_size(10))

        # 空状态
        self._empty_box = QWidget()
        empty_layout = QVBoxLayout(self._empty_box)
        empty_layout.setContentsMargins(0, scale_font_size(40), 0, scale_font_size(24))
        empty_layout.setSpacing(scale_font_size(14))
        icon_label = QLabel("⏰")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(f"font-size: {font_size_css(scale_font_size(52))}; background: transparent;")
        title_label = QLabel("开启你的第一个自动化任务吧")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {font_size_css(scale_font_size(15))}; background: transparent;"
        )
        add_btn = PrimaryPushButton("＋ 添加自动化")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedWidth(scale_font_size(150))
        add_btn.clicked.connect(lambda: self.createRequested.emit(None))
        btn_box = QHBoxLayout()
        btn_box.addStretch(1)
        btn_box.addWidget(add_btn)
        btn_box.addStretch(1)
        empty_layout.addWidget(icon_label)
        empty_layout.addWidget(title_label)
        empty_layout.addLayout(btn_box)
        self._body_layout.addWidget(self._empty_box)

        # 任务卡容器
        self._task_box = QVBoxLayout()
        self._task_box.setSpacing(scale_font_size(8))
        self._body_layout.addLayout(self._task_box)

        # 模板区标题
        self._tpl_title = QLabel("自动化任务模板")
        self._tpl_title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: 600; font-size: {font_size_css(scale_font_size(15))};"
            f"background: transparent; margin-top: {scale_font_size(10)}px;"
        )
        self._body_layout.addWidget(self._tpl_title)

        # 模板网格（2 列）
        grid_host = QWidget()
        grid_host.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(scale_font_size(10))
        grid.setVerticalSpacing(scale_font_size(10))
        for index, template in enumerate(TEMPLATES):
            card = self._make_template_card(template)
            grid.addWidget(card, index // 2, index % 2)
        grid.setRowStretch(len(TEMPLATES) // 2 + 1, 1)
        self._body_layout.addWidget(grid_host)
        self._body_layout.addStretch(1)

    # ── 模板卡 ──

    def _make_template_card(self, template: Dict[str, Any]) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {_card_bg(160)}; border: 1px solid {Colors.BORDER};
                border-radius: {scale_font_size(10)}px;
            }}
            QFrame:hover {{ border: 1px solid {Colors.SYSTEM_ACCENT}; background: {_card_bg(220)}; }}
            """
        )
        layout = QHBoxLayout(card)
        layout.setContentsMargins(scale_font_size(12), scale_font_size(10), scale_font_size(12), scale_font_size(10))
        layout.setSpacing(scale_font_size(10))
        icon = QLabel(template["icon"])
        icon.setStyleSheet(
            f"font-size: {font_size_css(scale_font_size(20))}; background: transparent; border: none;"
        )
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel(template["title"])
        title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: 600; font-size: {font_size_css(scale_font_size(13))};"
            f"background: transparent; border: none;"
        )
        desc = QLabel(template["desc"])
        desc.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {font_size_css(scale_font_size(11))};"
            f"background: transparent; border: none;"
        )
        desc.setWordWrap(True)
        text_col.addWidget(title)
        text_col.addWidget(desc)
        layout.addWidget(icon)
        layout.addLayout(text_col, 1)
        card.setToolTip(template["prompt"])
        card.mousePressEvent = lambda event: self.createRequested.emit(template)
        return card

    # ── 任务卡 ──

    def _make_task_card(self, task: CronTask) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{ background: {_card_bg(180)}; border: 1px solid {Colors.BORDER};
                      border-radius: {scale_font_size(10)}px; }}
            """
        )
        layout = QHBoxLayout(card)
        layout.setContentsMargins(scale_font_size(12), scale_font_size(10), scale_font_size(10), scale_font_size(10))
        layout.setSpacing(scale_font_size(10))

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_label = QLabel(task.name or "未命名任务")
        name_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: 600; font-size: {font_size_css(scale_font_size(13))};"
            f"background: transparent; border: none;"
        )
        running = CronChatControllerHolder.get_instance().is_task_running(task.task_id)
        if running:
            schedule_text = "● 执行中…"
            schedule_color = Colors.REALTIME_ACCENT
        else:
            schedule_text = task.schedule_summary()
            if task.enabled and task.next_run_at:
                schedule_text += f" · 下次 {_fmt_time(task.next_run_at)}"
            elif not task.enabled:
                schedule_text += " · 已停用"
            schedule_color = Colors.TEXT_SECONDARY
        schedule_label = QLabel(schedule_text)
        schedule_label.setStyleSheet(
            f"color: {schedule_color}; font-size: {font_size_css(scale_font_size(11))};"
            f"background: transparent; border: none;"
        )
        prompt_preview = (task.prompt or "").replace("\n", " ")
        if len(prompt_preview) > 40:
            prompt_preview = prompt_preview[:40] + "…"
        preview_label = QLabel(prompt_preview)
        preview_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {font_size_css(scale_font_size(11))};"
            f"background: transparent; border: none;"
        )
        text_col.addWidget(name_label)
        text_col.addWidget(schedule_label)
        text_col.addWidget(preview_label)
        layout.addLayout(text_col, 1)

        # 启用开关
        switch = SwitchButton()
        switch.setChecked(task.enabled)
        _configure_switch(switch)
        switch.checkedChanged.connect(lambda on, t=task: self.toggleRequested.emit(t, bool(on)))
        layout.addWidget(switch)

        # 操作按钮
        run_btn = ToolButton(FIF.PLAY)
        run_btn.setToolTip("立即运行")
        run_btn.setCursor(Qt.PointingHandCursor)
        edit_btn = ToolButton(FIF.EDIT)
        edit_btn.setToolTip("编辑")
        del_btn = ToolButton(FIF.DELETE)
        del_btn.setToolTip("删除")
        action_btn_style = (
            f"ToolButton {{ background: transparent; border: none; border-radius: 4px; padding: 4px; color: {Colors.TEXT_SECONDARY}; }}"
            f" ToolButton:hover {{ background: {Colors.HOVER_BG}; color: {Colors.TEXT_PRIMARY}; }}"
        )
        for btn in (run_btn, edit_btn, del_btn):
            btn.setStyleSheet(action_btn_style)
        run_btn.clicked.connect(lambda: self.runNowRequested.emit(task))
        edit_btn.clicked.connect(lambda: self.editRequested.emit(task))
        del_btn.clicked.connect(lambda: self.deleteRequested.emit(task))
        for btn in (run_btn, edit_btn, del_btn):
            layout.addWidget(btn)
        return card

    # ── 刷新 ──

    def refresh(self):
        # 清空旧任务卡
        for card in self._task_cards:
            card.setParent(None)
            card.deleteLater()
        self._task_cards.clear()

        tasks = CronStore.get_instance().load_tasks()
        tasks.sort(key=lambda t: (not t.enabled, t.next_run_at or "9999"))
        self._empty_box.setVisible(not tasks)
        for task in tasks:
            card = self._make_task_card(task)
            self._task_cards.append(card)
            self._task_box.addWidget(card)


# 延迟持有 controller 引用（避免 cards ↔ controller 循环导入）
class CronChatControllerHolder:
    @staticmethod
    def get_instance():
        from .controller import CronChatController

        return CronChatController.get_instance()


# ============================================================
#  编辑页
# ============================================================


class TaskEditPage(QWidget):
    """任务编辑表单"""

    saveRequested = pyqtSignal(object)  # CronTask
    cancelRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task: Optional[CronTask] = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(scale_font_size(12))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        root.addWidget(scroll, 1)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        scroll.setWidget(body)
        form = QVBoxLayout(body)
        form.setContentsMargins(scale_font_size(4), 0, scale_font_size(8), scale_font_size(8))
        form.setSpacing(scale_font_size(12))

        # ── 提示条 ──
        tip = QFrame()
        tip.setStyleSheet(
            f"QFrame {{ background: rgba(102, 198, 255, 30); border: 1px solid rgba(102, 198, 255, 90);"
            f"border-radius: {scale_font_size(8)}px; }}"
        )
        tip_layout = QHBoxLayout(tip)
        tip_layout.setContentsMargins(scale_font_size(12), scale_font_size(8), scale_font_size(12), scale_font_size(8))
        tip_label = QLabel("ⓘ 定时任务执行时，请保持 DriFox 客户端处于运行状态，否则任务将无法正常执行")
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet(
            f"color: {Colors.SYSTEM_ACCENT}; font-size: {font_size_css(scale_font_size(12))}; background: transparent; border: none;"
        )
        tip_layout.addWidget(tip_label)
        form.addWidget(tip)

        # ── 名称 ──
        form.addWidget(self._field_label("名称"))
        self._name_edit = LineEdit()
        self._name_edit.setPlaceholderText("例如：每日 AI 新闻推送")
        self._name_edit.setStyleSheet(self._input_style())
        form.addWidget(self._name_edit)

        # ── 提示词 ──
        form.addWidget(self._field_label("提示词"))
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setPlaceholderText("任务执行时发送给智能体的完整指令…")
        self._prompt_edit.setFixedHeight(scale_font_size(110))
        self._prompt_edit.setStyleSheet(self._input_style())
        form.addWidget(self._prompt_edit)

        # ── 执行频率 ──
        freq_label = self._field_label("执行频率")
        freq_hint = QLabel("（建议避开整点高峰，非高峰执行更准时）")
        freq_hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {font_size_css(scale_font_size(11))}; background: transparent;"
        )
        freq_row = QHBoxLayout()
        freq_row.addWidget(freq_label)
        freq_row.addWidget(freq_hint)
        freq_row.addStretch(1)
        form.addLayout(freq_row)

        # 三选胶囊
        type_row = QHBoxLayout()
        self._type_group = QButtonGroup(self)
        for index, (label, value) in enumerate([("周期", "cycle"), ("按间隔", "interval"), ("单次", "once")]):
            btn = PushButton(label)
            btn.setCheckable(True)
            btn.setChecked(index == 0)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, v=value: self._on_type_changed(v))
            self._type_group.addButton(btn)
            type_row.addWidget(btn)
        type_row.addStretch(1)
        form.addLayout(type_row)
        self._schedule_type = "cycle"  # UI 层：cycle（daily/weekly 合并）/ interval / once

        # 周期子面板：每天/每周 + 星期 + 时间
        cycle_panel = QFrame()
        cycle_panel.setStyleSheet("background: transparent;")
        cycle_layout = QHBoxLayout(cycle_panel)
        cycle_layout.setContentsMargins(0, 0, 0, 0)
        cycle_layout.setSpacing(scale_font_size(8))
        self._cycle_mode = ComboBox()
        self._cycle_mode.addItems(["每天", "每周"])
        self._cycle_mode.currentIndexChanged.connect(lambda i: self._on_cycle_mode(i == 1))
        cycle_layout.addWidget(self._cycle_mode)

        # 星期按钮组（每周模式显示）
        self._weekday_box = QWidget()
        weekday_layout = QHBoxLayout(self._weekday_box)
        weekday_layout.setContentsMargins(0, 0, 0, 0)
        weekday_layout.setSpacing(scale_font_size(2))
        self._weekday_group = QButtonGroup(self)
        for wd, label in enumerate(WEEKDAY_LABELS):
            btn = PushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self._weekday_group.addButton(btn, wd)
            weekday_layout.addWidget(btn)
        self._weekday_box.setVisible(False)
        cycle_layout.addWidget(self._weekday_box)

        cycle_layout.addStretch(1)
        self._time_edit = _make_time_edit()
        cycle_layout.addWidget(self._time_edit)
        form.addWidget(cycle_panel)

        # 间隔子面板
        interval_panel = QFrame()
        interval_panel.setStyleSheet("background: transparent;")
        interval_layout = QHBoxLayout(interval_panel)
        interval_layout.setContentsMargins(0, 0, 0, 0)
        from PyQt5.QtWidgets import QSpinBox

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(5, 10080)
        self._interval_spin.setValue(60)
        self._interval_spin.setSuffix(" 分钟")
        self._interval_spin.setStyleSheet(self._input_style())
        interval_layout.addWidget(QLabel("每隔"))
        interval_layout.addWidget(self._interval_spin)
        interval_layout.addWidget(QLabel("执行一次"))
        interval_layout.addStretch(1)
        for w in interval_layout.itemAt(0).widget(), interval_layout.itemAt(2).widget():
            w.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;")
        self._interval_panel = interval_panel
        interval_panel.setVisible(False)
        form.addWidget(interval_panel)

        # 单次子面板
        once_panel = QFrame()
        once_panel.setStyleSheet("background: transparent;")
        once_layout = QHBoxLayout(once_panel)
        once_layout.setContentsMargins(0, 0, 0, 0)
        from PyQt5.QtWidgets import QDateTimeEdit

        self._once_edit = QDateTimeEdit()
        self._once_edit.setCalendarPopup(True)
        self._once_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._once_edit.setDateTime(datetime.now().replace(minute=0).replace(second=0, microsecond=0))
        self._once_edit.setStyleSheet(self._input_style())
        once_layout.addWidget(QLabel("执行时刻"))
        once_layout.addWidget(self._once_edit)
        once_layout.addStretch(1)
        once_layout.itemAt(0).widget().setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;"
        )
        self._once_panel = once_panel
        once_panel.setVisible(False)
        form.addWidget(once_panel)

        # ── 生效日期区间 ──
        range_label = self._field_label("生效日期区间")
        range_hint = QLabel("（可选，留空表示始终生效）")
        range_hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {font_size_css(scale_font_size(11))}; background: transparent;"
        )
        range_row = QHBoxLayout()
        range_row.addWidget(range_label)
        range_row.addWidget(range_hint)
        range_row.addStretch(1)
        form.addLayout(range_row)

        range_panel = QFrame()
        range_panel.setStyleSheet("background: transparent;")
        range_layout = QHBoxLayout(range_panel)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setSpacing(scale_font_size(8))
        self._range_from_check = PushButton("从")
        self._range_from_check.setCheckable(True)
        self._range_to_check = PushButton("至")
        self._range_to_check.setCheckable(True)
        self._range_from_edit = _make_date_edit()
        self._range_to_edit = _make_date_edit()
        for widget in (self._range_from_check, self._range_from_edit, self._range_to_check, self._range_to_edit):
            range_layout.addWidget(widget)
        range_layout.addStretch(1)
        self._range_from_check.toggled.connect(self._range_from_edit.setVisible)
        self._range_to_check.toggled.connect(self._range_to_edit.setVisible)
        self._range_from_edit.setVisible(False)
        self._range_to_edit.setVisible(False)
        form.addWidget(range_panel)

        # ── 开关行 ──
        switch_row = QHBoxLayout()
        self._tools_switch = SwitchButton("允许使用工具")
        self._tools_switch.setChecked(True)
        _configure_switch(self._tools_switch)
        self._enable_switch = SwitchButton("启用任务")
        self._enable_switch.setChecked(True)
        _configure_switch(self._enable_switch)
        switch_row.addWidget(self._tools_switch)
        switch_row.addStretch(1)
        switch_row.addWidget(self._enable_switch)
        form.addLayout(switch_row)

        form.addStretch(1)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = PushButton("取消")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.cancelRequested.emit)
        save_btn = PrimaryPushButton("保存")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    # ── 小部件工具 ──

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: 600; font-size: {font_size_css(scale_font_size(13))};"
            f"background: transparent;"
        )
        return label

    @staticmethod
    def _input_style() -> str:
        return f"""
        LineEdit, QTextEdit, QSpinBox, QDateTimeEdit, QTimeEdit, QDateEdit, ComboBox {{
            background: {_card_bg(140)}; color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER}; border-radius: {scale_font_size(8)}px;
            padding: {scale_font_size(6)}px {scale_font_size(10)}px;
            font-size: {font_size_css(scale_font_size(13))}; {FONT_CSS}
        }}
        LineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateTimeEdit:focus, ComboBox:focus {{
            border: 1px solid {Colors.SYSTEM_ACCENT};
        }}
        QSpinBox::up-button, QSpinBox::down-button, QDateTimeEdit::up-button, QDateTimeEdit::down-button {{
            background: {Colors.HOVER_BG}; border: none; width: 16px;
        }}
        """

    # ── 频率类型切换 ──

    def _on_type_changed(self, value: str):
        self._schedule_type = value
        self._set_checked_type(value)
        self._apply_panel_visibility()

    def _set_checked_type(self, value: str):
        mapping = {"cycle": 0, "interval": 1, "once": 2}
        buttons = self._type_group.buttons()
        for index, btn in enumerate(buttons):
            btn.setChecked(mapping.get(value, 0) == index)

    def _on_cycle_mode(self, weekly: bool):
        self._weekday_box.setVisible(weekly)
        if weekly and not any(btn.isChecked() for btn in self._weekday_group.buttons()):
            self._weekday_group.buttons()[0].setChecked(True)  # 默认周一

    def _apply_panel_visibility(self):
        # cycle_panel 是 _cycle_mode 的父级；interval/once 面板独立
        cycle_panel = self._cycle_mode.parentWidget()
        cycle_panel.setVisible(self._schedule_type == "cycle")
        self._interval_panel.setVisible(self._schedule_type == "interval")
        self._once_panel.setVisible(self._schedule_type == "once")

    # ── 装载 / 收集 ──

    def load_task(self, task: Optional[CronTask], template: Optional[Dict[str, Any]] = None):
        """编辑已有任务 或 从模板新建"""
        if task is not None:
            self._task = task
            self._name_edit.setText(task.name)
            self._prompt_edit.setPlainText(task.prompt)
            self._tools_switch.setChecked(task.use_tools)
            self._enable_switch.setChecked(task.enabled)
            stype = task.schedule_type
            if stype in ("daily", "weekly"):
                self._schedule_type = "cycle"
                self._cycle_mode.setCurrentIndex(1 if stype == "weekly" else 0)
                self._weekday_box.setVisible(stype == "weekly")
                if stype == "weekly":
                    for btn in self._weekday_group.buttons():
                        btn.setChecked(self._weekday_group.id(btn) in (task.weekdays or []))
                else:
                    self._weekday_group.buttons()[0].setChecked(True)
                h, m = (task.time_hhmm or "09:00").split(":")[:2]
                self._time_edit.setTime(QTime(int(h), int(m)))
            elif stype == "interval":
                self._schedule_type = "interval"
                self._interval_spin.setValue(int(task.interval_minutes or 60))
            else:
                self._schedule_type = "once"
                if task.once_datetime:
                    try:
                        dt = datetime.fromisoformat(task.once_datetime)
                        self._once_edit.setDateTime(dt)
                    except ValueError:
                        pass
            self._set_checked_type(self._schedule_type)
            # 生效区间
            if task.active_from:
                self._range_from_check.setChecked(True)
                self._range_from_edit.setDate(QDate.fromString(task.active_from, "yyyy-MM-dd"))
            else:
                self._range_from_check.setChecked(False)
            if task.active_to:
                self._range_to_check.setChecked(True)
                self._range_to_edit.setDate(QDate.fromString(task.active_to, "yyyy-MM-dd"))
            else:
                self._range_to_check.setChecked(False)
        else:
            self._task = None
            self._name_edit.clear()
            self._prompt_edit.clear()
            self._tools_switch.setChecked(True)
            self._enable_switch.setChecked(True)
            self._schedule_type = "cycle"
            self._cycle_mode.setCurrentIndex(0)
            self._weekday_box.setVisible(False)
            self._weekday_group.buttons()[0].setChecked(True)
            self._time_edit.setTime(QTime(9, 0))
            self._interval_spin.setValue(60)
            self._range_from_check.setChecked(False)
            self._range_to_check.setChecked(False)
            if template:
                self._name_edit.setText(template.get("title", ""))
                self._prompt_edit.setPlainText(template.get("prompt", ""))
                sched = template.get("schedule") or {}
                stype = sched.get("schedule_type", "daily")
                if stype in ("daily", "weekly"):
                    self._schedule_type = "cycle"
                    weekly = stype == "weekly"
                    self._cycle_mode.setCurrentIndex(1 if weekly else 0)
                    self._weekday_box.setVisible(weekly)
                    if weekly:
                        weekdays = sched.get("weekdays") or [0]
                        for btn in self._weekday_group.buttons():
                            btn.setChecked(self._weekday_group.id(btn) in weekdays)
                    h, m = (sched.get("time_hhmm") or "09:00").split(":")[:2]
                    self._time_edit.setTime(QTime(int(h), int(m)))
                elif stype == "interval":
                    self._schedule_type = "interval"
                    self._interval_spin.setValue(int(sched.get("interval_minutes") or 60))
                else:
                    self._schedule_type = "once"
                self._set_checked_type(self._schedule_type)
        self._apply_panel_visibility()

    def _collect_task(self) -> CronTask:
        task = self._task or CronTask()
        task.name = self._name_edit.text().strip() or "未命名任务"
        task.prompt = self._prompt_edit.toPlainText().strip()
        task.use_tools = bool(self._tools_switch.isChecked())
        task.enabled = bool(self._enable_switch.isChecked())

        hhmm = self._time_edit.time().toString("HH:mm")
        task.time_hhmm = hhmm
        if self._schedule_type == "cycle":
            if self._cycle_mode.currentIndex() == 1:
                task.schedule_type = "weekly"
                task.weekdays = [self._weekday_group.id(b) for b in self._weekday_group.buttons() if b.isChecked()]
                if not task.weekdays:
                    task.weekdays = [0]
            else:
                task.schedule_type = "daily"
        elif self._schedule_type == "interval":
            task.schedule_type = "interval"
            task.interval_minutes = int(self._interval_spin.value())
        else:
            task.schedule_type = "once"
            task.once_datetime = self._once_edit.dateTime().toString("yyyy-MM-dd HH:mm")

        task.active_from = self._range_from_edit.date().toString("yyyy-MM-dd") if self._range_from_check.isChecked() else ""
        task.active_to = self._range_to_edit.date().toString("yyyy-MM-dd") if self._range_to_check.isChecked() else ""
        return task

    def _on_save(self):
        if not self._prompt_edit.toPlainText().strip():
            self._prompt_edit.setFocus()
            return
        self.saveRequested.emit(self._collect_task())


def _make_time_edit():
    from PyQt5.QtWidgets import QTimeEdit

    edit = QTimeEdit()
    edit.setDisplayFormat("HH:mm")
    edit.setCurrentSection(QTimeEdit.MinuteSection)
    return edit


def _make_date_edit():
    from PyQt5.QtWidgets import QDateEdit

    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("yyyy-MM-dd")
    edit.setDate(QDate.currentDate())
    return edit


# ============================================================
#  运行记录页
# ============================================================


class RunLogPage(QWidget):
    """运行记录流（点击行展开结果全文）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[QFrame] = []
        self._detail: Optional[QTextEdit] = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(scale_font_size(8))

        # 顶部操作行
        top_row = QHBoxLayout()
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {font_size_css(scale_font_size(12))}; background: transparent;"
        )
        clear_btn = PushButton("清空全部记录")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._on_clear)
        top_row.addWidget(self._count_label)
        top_row.addStretch(1)
        top_row.addWidget(clear_btn)
        root.addLayout(top_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        root.addWidget(scroll, 1)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        scroll.setWidget(body)
        self._list_layout = QVBoxLayout(body)
        self._list_layout.setContentsMargins(scale_font_size(4), 0, scale_font_size(8), scale_font_size(8))
        self._list_layout.setSpacing(scale_font_size(6))

        self._empty_label = QLabel("暂无运行记录")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {font_size_css(scale_font_size(13))};"
            f"background: transparent; padding: {scale_font_size(40)}px 0;"
        )
        self._list_layout.addWidget(self._empty_label)
        self._list_layout.addStretch(1)

    STATUS_COLORS = {
        "running": "#66c6ff",
        "success": "#34d399",
        "error": "#f87171",
        "timeout": "#fbbf24",
        "cancelled": "#888888",
    }

    def refresh(self):
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        self._hide_detail()

        records = CronStore.get_instance().load_runs()
        self._empty_label.setVisible(not records)
        self._count_label.setText(f"共 {len(records)} 条记录")
        for record in records[:100]:
            row = self._make_row(record)
            self._rows.append(row)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def _make_row(self, record: RunRecord) -> QFrame:
        row = QFrame()
        row.setCursor(Qt.PointingHandCursor)
        color = self.STATUS_COLORS.get(record.status, "#888")
        row.setStyleSheet(
            f"""
            QFrame {{ background: {_card_bg(160)}; border: 1px solid {Colors.BORDER};
                      border-left: 3px solid {color}; border-radius: {scale_font_size(8)}px; }}
            QFrame:hover {{ background: {_card_bg(220)}; }}
            """
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(scale_font_size(10), scale_font_size(8), scale_font_size(10), scale_font_size(8))
        layout.setSpacing(scale_font_size(10))

        status_label = QLabel("●" if record.status != "running" else "◐")
        status_label.setStyleSheet(f"color: {color}; font-size: {font_size_css(scale_font_size(13))}; background: transparent; border: none;")
        name_label = QLabel(record.task_name or "未知任务")
        name_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: 600; font-size: {font_size_css(scale_font_size(12))};"
            f"background: transparent; border: none;"
        )
        status_text = QLabel(record.status_label)
        status_text.setStyleSheet(f"color: {color}; font-size: {font_size_css(scale_font_size(11))}; background: transparent; border: none;")
        time_label = QLabel(_fmt_time(record.started_at))
        time_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {font_size_css(scale_font_size(11))}; background: transparent; border: none;"
        )
        duration_label = QLabel(f"{record.duration_seconds}s" if record.duration_seconds else "")
        duration_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {font_size_css(scale_font_size(11))}; background: transparent; border: none;"
        )
        layout.addWidget(status_label)
        layout.addWidget(name_label, 1)
        layout.addWidget(status_text)
        layout.addWidget(time_label)
        layout.addWidget(duration_label)
        row.mousePressEvent = lambda event: self._show_detail(record)
        return row

    def _show_detail(self, record: RunRecord):
        """展开结果全文（复用单实例 detail 面板，插入到列表顶部）"""
        self._hide_detail()
        detail = QTextEdit()
        detail.setReadOnly(True)
        if record.status == "success":
            text = record.result_text or "（无输出）"
        else:
            text = f"状态：{record.status_label}\n错误：{record.error or '—'}\n\n{record.result_text}".strip()
        detail.setPlainText(text)
        detail.setFixedHeight(scale_font_size(220))
        detail.setStyleSheet(
            f"""
            QTextEdit {{
                background: {_card_bg(120)}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; border-radius: {scale_font_size(8)}px;
                padding: {scale_font_size(8)}px; font-size: {font_size_css(scale_font_size(12))}; {FONT_CSS}
            }}
            """
        )
        self._detail = detail
        self._list_layout.insertWidget(1, detail)

    def _hide_detail(self):
        if self._detail is not None:
            self._detail.setParent(None)
            self._detail.deleteLater()
            self._detail = None

    def _on_clear(self):
        store = CronStore.get_instance()
        for task in store.load_tasks():
            store.delete_runs(task.task_id)
        self.refresh()


# ============================================================
#  主卡
# ============================================================


class CronChatCard(QFrame):
    """CronChat 主卡 — full 覆盖对话区，内部三页编排"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cronChatCard")
        self._ctx_provider = None
        self._last_ctx: Dict[str, Any] = {}
        self._build_ui()
        self._refresh_theme_style()

    # ── 上下文（拉模型）──

    def set_context_provider(self, provider):
        self._ctx_provider = provider

    def showEvent(self, event):
        super().showEvent(event)
        if self._ctx_provider is not None:
            try:
                self._last_ctx = self._ctx_provider() or {}
            except Exception:
                self._last_ctx = {}
        # 绑定控制器（缓存 ctx + 首次启动调度器）
        CronChatControllerHolder.get_instance().bind_card(self, self._last_ctx)
        self.refresh_all()

    def refresh_all(self):
        """刷新当前页数据（controller 执行结束/开始时也会调用）"""
        try:
            index = self._stack.currentIndex()
            if index == 0:
                self._list_page.refresh()
            elif index == 2:
                self._log_page.refresh()
        except RuntimeError:
            pass

    # ── UI 构建 ──

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(scale_font_size(20), scale_font_size(14), scale_font_size(20), scale_font_size(14))
        root.setSpacing(scale_font_size(10))

        # 顶栏：胶囊 Tab + 关闭
        top_row = QHBoxLayout()
        self._pill_tab = _PillTab(["定时任务", "运行记录"])
        self._pill_tab.changed.connect(self._on_tab_changed)
        top_row.addWidget(self._pill_tab)
        top_row.addStretch(1)
        close_btn = ToolButton(FIF.CLOSE)
        close_btn.setToolTip("关闭")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            f"ToolButton {{ background: transparent; border: none; border-radius: 4px; padding: 4px; color: {Colors.TEXT_SECONDARY}; }}"
            f" ToolButton:hover {{ background: {Colors.HOVER_BG}; color: {Colors.TEXT_PRIMARY}; }}"
        )
        close_btn.clicked.connect(self._on_close)
        top_row.addWidget(close_btn)
        root.addLayout(top_row)

        # 三页堆叠：0 列表 / 1 编辑 / 2 运行记录
        self._stack = QStackedWidget()
        self._list_page = TaskListPage()
        self._edit_page = TaskEditPage()
        self._log_page = RunLogPage()
        self._stack.addWidget(self._list_page)
        self._stack.addWidget(self._edit_page)
        self._stack.addWidget(self._log_page)
        root.addWidget(self._stack, 1)

        # 信号接线
        self._list_page.createRequested.connect(self._on_create)
        self._list_page.editRequested.connect(self._on_edit)
        self._list_page.runNowRequested.connect(self._on_run_now)
        self._list_page.deleteRequested.connect(self._on_delete)
        self._list_page.toggleRequested.connect(self._on_toggle)
        self._edit_page.saveRequested.connect(self._on_save)
        self._edit_page.cancelRequested.connect(lambda: self._switch_page(0))

    # ── 页面切换 ──

    def _switch_page(self, index: int):
        self._stack.setCurrentIndex(index)
        self.refresh_all()

    def _on_tab_changed(self, index: int):
        # Tab: 0=任务列表 1=运行记录 → stack: 0 / 2
        self._stack.setCurrentIndex(0 if index == 0 else 2)
        self.refresh_all()

    def _on_close(self):
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        registry = UIPluginRegistry.get_instance()
        if not registry.hide_floating_card_globally("main"):
            services = self._last_ctx.get("services") or {}
            services.get("hide_card", lambda _c: None)("main")
        self.hide()

    # ── 列表页动作 ──

    def _on_create(self, template):
        self._edit_page.load_task(None, template)
        self._stack.setCurrentIndex(1)

    def _on_edit(self, task):
        self._edit_page.load_task(task)
        self._stack.setCurrentIndex(1)

    def _on_run_now(self, task):
        CronChatControllerHolder.get_instance().run_now(task)
        self._list_page.refresh()

    def _on_delete(self, task):
        CronStore.get_instance().delete_task(task.task_id)
        self._reschedule_all()
        self._list_page.refresh()

    def _on_toggle(self, task, enabled: bool):
        task.enabled = bool(enabled)
        CronStore.get_instance().upsert_task(task)
        self._reschedule_all()
        self._list_page.refresh()

    def _on_save(self, task):
        CronStore.get_instance().upsert_task(task)
        self._reschedule_all()
        self._switch_page(0)

    def _reschedule_all(self):
        controller = CronChatControllerHolder.get_instance()
        if controller._scheduler is not None:
            controller._scheduler.recompute_all()

    # ── 主题 ──

    def refresh_font_size(self):
        self._refresh_theme_style()

    def _refresh_theme_style(self):
        Colors.refresh()
        self.setStyleSheet(
            f"""
            QFrame#cronChatCard {{
                background: {Colors.CONTENT_BG}; border: 1px solid {Colors.BORDER};
                border-radius: {scale_font_size(12)}px; {FONT_CSS}
            }}
            QLabel {{ background: transparent; }}
            """
        )
