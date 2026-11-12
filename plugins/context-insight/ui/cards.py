# -*- coding: utf-8 -*-
"""Context 面板内的各类卡片 —— 统计、组成、计时、当前上下文、事件、文件、命令。"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .analyzer import CATEGORY_COLORS, CATEGORY_LABELS, CATEGORY_ORDER, SessionAnalysis
from .charts import DonutChart, RingProgress, StackedBar
from .fmt import fmt_cost, fmt_duration, fmt_int, fmt_k, fmt_pct, fmt_ts
from .theme import Palette, parse_color
from .widgets import BarRow, EmptyState, FlowLayout, LegendList, Pill, SectionCard, css, make_label


def _category_rows(comp: Dict[str, int]) -> List[Tuple[str, str, int, QColor]]:
    rows = []
    for key in CATEGORY_ORDER:
        value = int(comp.get(key, 0) or 0)
        if value <= 0:
            continue
        rows.append((key, CATEGORY_LABELS.get(key, key), value, parse_color(CATEGORY_COLORS.get(key, "#888888"))))
    rows.sort(key=lambda r: -r[2])
    return rows


def _chip(text: str, palette: Palette, color: Optional[QColor] = None) -> Pill:
    pill = Pill(text)
    pill.set_palette_obj(palette)
    if color is not None:
        pill.set_color(color)
    return pill


class StatsCard(SectionCard):
    def __init__(self, parent=None):
        super().__init__("会话统计", parent)
        self._palette = Palette()
        self._analysis: Optional[SessionAnalysis] = None
        self._grid_host = QWidget(self)
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        self._body_layout.addWidget(self._grid_host)

    def set_palette_obj(self, palette: Palette) -> None:
        super().set_palette_obj(palette)
        self._palette = palette
        self._rebuild()

    def set_analysis(self, analysis: SessionAnalysis) -> None:
        self._analysis = analysis
        self._rebuild()

    def _cell(self, label: str, value: str, sub: str = "", accent: bool = False) -> QWidget:
        p = self._palette
        box = QFrame(self)
        box.setObjectName("ciStatCell")
        box.setStyleSheet(
            f"#ciStatCell {{ background: {css(p.alpha(p.border, 28))}; border-radius: 8px; }}"
            f"#ciStatCell QLabel {{ background: transparent; }}"
        )
        layout = QVBoxLayout(box)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(1)
        lab = QLabel(label, box)
        lab.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-3)}px;")
        val = QLabel(value, box)
        val.setStyleSheet(
            f"color: {css(p.accent if accent else p.text_primary)}; font-size: {p.fs(0)}px; font-weight: 600;"
        )
        layout.addWidget(lab)
        layout.addWidget(val)
        if sub:
            sublab = QLabel(sub, box)
            sublab.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-3)}px;")
            layout.addWidget(sublab)
        return box

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        analysis = self._analysis
        if analysis is None:
            self._grid.addWidget(EmptyState("等待会话数据", self), 0, 0)
            return
        p = self._palette
        usage = analysis.usage
        cache = analysis.cache_hit_rate
        model = analysis.models[0] if analysis.models else "未知"
        cells = [
            ("轮次", fmt_int(usage.get("turns", 0)), f"{fmt_int(usage.get('steps', 0))} 个请求"),
            ("用户输入", fmt_int(len([t for t in analysis.turns if t.user_text])), ""),
            ("工具调用", fmt_int(sum(analysis.tool_counts.values())), f"{len(analysis.tool_counts)} 种工具"),
            ("成本", fmt_cost(analysis.cost_usd, analysis.cost_known), "按 models.dev 标价"),
            ("缓存命中", fmt_pct(cache * 100) if cache is not None else "—", "仅活跃会话可读"),
            ("模型", model, f"预算 {fmt_k(analysis.budget_tokens)}" if analysis.budget_tokens else "上限未知"),
        ]
        for i, (label, value, sub) in enumerate(cells):
            self._grid.addWidget(self._cell(label, value, sub, accent=(i == 0)), i // 3, i % 3)
        for i in range(3):
            self._grid.setColumnStretch(i, 1)


class CompositionCard(SectionCard):
    def __init__(self, title: str = "Token 组成", show_donut: bool = True, parent=None):
        super().__init__(title, parent)
        self._palette = Palette()
        self._analysis: Optional[SessionAnalysis] = None
        self._show_donut = show_donut
        self._host = QWidget(self)
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(0, 0, 0, 0)
        self._host_layout.setSpacing(8)
        self._body_layout.addWidget(self._host)
        self._donut: Optional[DonutChart] = None
        self._bar: Optional[StackedBar] = None
        self._legend: Optional[LegendList] = None

    def set_palette_obj(self, palette: Palette) -> None:
        super().set_palette_obj(palette)
        self._palette = palette
        self._rebuild()

    def set_analysis(self, analysis: SessionAnalysis) -> None:
        self._analysis = analysis
        self._rebuild()

    def _clear_host(self) -> None:
        while self._host_layout.count():
            item = self._host_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()

    def _rebuild(self) -> None:
        self._clear_host()
        analysis = self._analysis
        if analysis is None:
            self._host_layout.addWidget(EmptyState("等待会话数据", self))
            return
        p = self._palette
        rows = _category_rows(analysis.context_latest or analysis.context_total)
        total = sum(r[2] for r in rows)
        self.set_subtitle(f"{fmt_int(total)} tokens · {fmt_cost(analysis.cost_usd, analysis.cost_known)}")
        if self._show_donut:
            top = QHBoxLayout()
            top.setContentsMargins(0, 0, 0, 0)
            top.setSpacing(10)
            donut = DonutChart(self)
            donut.set_palette_obj(p)
            donut.set_data(rows, fmt_k(total), "计费组成")
            donut.setMinimumSize(280, 150)
            donut.setMaximumSize(340, 180)
            top.addWidget(donut, 0)
            top.addWidget(self._legend_widget(rows, total), 1)
            self._host_layout.addLayout(top)
        bar = StackedBar(self)
        bar.set_palette_obj(p)
        bar.set_data(rows)
        self._host_layout.addWidget(bar)
        if not self._show_donut:
            self._host_layout.addWidget(self._legend_widget(rows, total))
        note = make_label(
            "工具定义：活跃会话用冻结 schema，历史会话按当前工具集近似；其余分类按消息内容估算，总量锚定 API prompt_tokens。",
            p,
            -3,
            secondary=True,
        )
        note.setWordWrap(True)
        self._host_layout.addWidget(note)

    def _legend_widget(self, rows, total) -> QWidget:
        legend = LegendList(self)
        legend.set_palette_obj(self._palette)
        legend.set_data(rows, total)
        return legend


class CurrentContextCard(SectionCard):
    def __init__(self, parent=None):
        super().__init__("当前上下文", parent)
        self._palette = Palette()
        self._analysis: Optional[SessionAnalysis] = None
        self._host = QWidget(self)
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._body_layout.addWidget(self._host)

    def set_palette_obj(self, palette: Palette) -> None:
        super().set_palette_obj(palette)
        self._palette = palette
        self._rebuild()

    def set_analysis(self, analysis: SessionAnalysis) -> None:
        self._analysis = analysis
        self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        analysis = self._analysis
        if analysis is None:
            self._layout.addWidget(EmptyState("等待会话数据", self))
            return
        p = self._palette
        rows = _category_rows(analysis.context_latest)
        used = analysis.used_tokens
        budget = analysis.budget_tokens
        self.set_subtitle(
            f"{fmt_int(used)} / {fmt_int(budget)} · {analysis.percent}%"
            if budget > 0
            else f"{fmt_int(used)} · 上限未知"
        )
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        ring = RingProgress(self)
        ring.set_palette_obj(p)
        if budget > 0:
            ring.set_value(analysis.percent, f"{analysis.percent}%", f"{fmt_k(used)} / {fmt_k(budget)}")
        else:
            ring.set_value(0, "—", f"{fmt_k(used)} / 未知")
        ring.setFixedSize(86, 86)
        head.addWidget(ring)
        head.addWidget(self._legend_widget(rows, sum(r[2] for r in rows)), 1)
        self._layout.addLayout(head)
        bar = StackedBar(self)
        bar.set_palette_obj(p)
        reserved = []
        if budget > used > 0:
            reserved.append(("自动压缩/输出预留", budget - used, QColor("#f59e0b")))
        bar.set_data(rows, reserved)
        self._layout.addWidget(bar)
        if reserved:
            note = make_label(
                f"斜线段 = 距窗口上限的余量 {fmt_int(budget - used)} tokens（含自动压缩与输出预留）",
                p,
                -3,
                secondary=True,
            )
            note.setWordWrap(True)
            self._layout.addWidget(note)

    def _legend_widget(self, rows, total) -> QWidget:
        legend = LegendList(self)
        legend.set_palette_obj(self._palette)
        legend.set_data(rows, total)
        return legend


class TimingCard(SectionCard):
    def __init__(self, parent=None):
        super().__init__("耗时分布", parent)
        self._palette = Palette()
        self._analysis: Optional[SessionAnalysis] = None
        self._host = QWidget(self)
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._body_layout.addWidget(self._host)

    def set_palette_obj(self, palette: Palette) -> None:
        super().set_palette_obj(palette)
        self._palette = palette
        self._rebuild()

    def set_analysis(self, analysis: SessionAnalysis) -> None:
        self._analysis = analysis
        self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        analysis = self._analysis
        if analysis is None:
            self._layout.addWidget(EmptyState("等待会话数据", self))
            return
        p = self._palette
        timing = analysis.timing
        model_ms = float(timing.get("model_ms", 0))
        tool_ms = float(timing.get("tool_ms", 0))
        total_ms = max(model_ms + tool_ms, float(timing.get("total_ms", 0)))
        self.set_subtitle(f"活跃 {fmt_duration(total_ms)}")
        bar = StackedBar(self)
        bar.set_palette_obj(p)
        bar.set_data(
            [
                ("model", "模型调用", int(model_ms), p.accent),
                ("tool", "工具执行", int(tool_ms), QColor("#a78bfa")),
                ("idle", "其他开销", int(max(0, total_ms - model_ms - tool_ms)), p.alpha(p.border, 200)),
            ]
        )
        self._layout.addWidget(bar)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        avg_ttft = (timing.get("ttft_ms", 0) / timing.get("steps", 1)) if timing.get("steps") else 0
        rows = [
            ("模型调用", fmt_duration(model_ms), f"{model_ms / total_ms * 100:.0f}%" if total_ms else "0%"),
            ("工具执行", fmt_duration(tool_ms), f"{tool_ms / total_ms * 100:.0f}%" if total_ms else "0%"),
            ("平均首字", fmt_duration(avg_ttft), f"{int(timing.get('steps', 0))} 次调用"),
        ]
        for i, (label, value, sub) in enumerate(rows):
            grid.addWidget(make_label(label, p, -2, secondary=True), i, 0)
            grid.addWidget(make_label(value, p, 0, True), i, 1)
            grid.addWidget(make_label(sub, p, -2, secondary=True), i, 2)
        grid.setColumnStretch(0, 1)
        self._layout.addLayout(grid)


class EventsCard(SectionCard):
    def __init__(self, parent=None):
        super().__init__("上下文事件", parent)
        self._palette = Palette()
        self._analysis: Optional[SessionAnalysis] = None
        self._host = QWidget(self)
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)
        self._body_layout.addWidget(self._host)

    def set_palette_obj(self, palette: Palette) -> None:
        super().set_palette_obj(palette)
        self._palette = palette
        self._rebuild()

    def set_analysis(self, analysis: SessionAnalysis) -> None:
        self._analysis = analysis
        self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        analysis = self._analysis
        if analysis is None:
            self._layout.addWidget(EmptyState("等待会话数据", self))
            return
        p = self._palette
        events = analysis.events
        self.set_subtitle(f"{len(events)} 个事件" if events else "")
        if not events:
            self._layout.addWidget(EmptyState("没有压缩、剪枝或明显回落事件", self))
            return
        for event in events[:30]:
            row = QFrame(self)
            row.setObjectName("ciEventRow")
            row.setStyleSheet(
                f"#ciEventRow {{ background: {css(p.alpha(p.border, 26))}; border-radius: 7px; }}"
            )
            layout = QHBoxLayout(row)
            layout.setContentsMargins(9, 6, 9, 6)
            layout.setSpacing(8)
            color = {
                "compaction": QColor("#f59e0b"),
                "prune": QColor("#a78bfa"),
                "drop": QColor("#f87171"),
                "jump": QColor("#34d399"),
            }.get(event.kind, p.accent)
            dot = QLabel(row)
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {css(color)}; border-radius: 4px;")
            title = make_label(event.title, p, -1, True)
            detail = make_label(event.detail, p, -2, secondary=True)
            detail.setWordWrap(True)
            ts = make_label(fmt_ts(event.ts), p, -3, secondary=True)
            layout.addWidget(dot)
            layout.addWidget(title)
            layout.addWidget(detail, 1)
            layout.addWidget(ts)
            self._layout.addWidget(row)


class FilesCard(SectionCard):
    def __init__(self, parent=None):
        super().__init__("文件活动", parent)
        self._palette = Palette()
        self._analysis: Optional[SessionAnalysis] = None
        self._filter = "all"
        self._host = QWidget(self)
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)
        self._body_layout.addWidget(self._host)
        self._chips_host = QWidget(self)
        self._chips_layout = FlowLayout(self._chips_host, 0, 6, 4)
        self._body_layout.insertWidget(0, self._chips_host)

    def set_palette_obj(self, palette: Palette) -> None:
        super().set_palette_obj(palette)
        self._palette = palette
        self._rebuild()

    def set_analysis(self, analysis: SessionAnalysis) -> None:
        self._analysis = analysis
        self._rebuild()

    def _rebuild(self) -> None:
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        analysis = self._analysis
        p = self._palette
        if analysis is None:
            self._layout.addWidget(EmptyState("等待会话数据", self))
            return
        counts = {"all": len(analysis.file_ops), "read": 0, "write": 0, "search": 0}
        for activity in analysis.file_ops.values():
            for action in activity.actions:
                counts[action] = counts.get(action, 0) + 1
        self.set_subtitle(f"{len(analysis.file_ops)} 个路径")
        for key, label in (("all", "全部"), ("read", "读取"), ("write", "写入"), ("search", "搜索")):
            btn = QPushButton(f"{label} {counts.get(key, 0)}", self._chips_host)
            btn.setCheckable(True)
            btn.setChecked(self._filter == key)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {css(p.text_secondary)};"
                f" border: 1px solid {css(p.alpha(p.border, 120))}; border-radius: 8px; padding: 2px 8px;"
                f" font-size: {p.fs(-2)}px; }}"
                f"QPushButton:checked {{ color: {css(p.text_primary)}; background: {css(p.alpha(p.accent, 40))};"
                f" border-color: {css(p.alpha(p.accent, 140))}; }}"
            )
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self._chips_layout.addWidget(btn)
        items = [
            a
            for a in analysis.file_ops.values()
            if self._filter == "all" or self._filter in a.actions
        ]
        items.sort(key=lambda a: (-a.count, a.path))
        if not items:
            self._layout.addWidget(EmptyState("没有文件活动", self))
            return
        for activity in items[:40]:
            row = QFrame(self)
            row.setObjectName("ciFileRow")
            row.setStyleSheet(
                f"#ciFileRow {{ background: {css(p.alpha(p.border, 26))}; border-radius: 7px; }}"
            )
            layout = QHBoxLayout(row)
            layout.setContentsMargins(9, 6, 9, 6)
            layout.setSpacing(6)
            actions = " ".join(
                {"read": "读", "write": "写", "search": "搜"}.get(a, a) for a in sorted(activity.actions)
            )
            action_label = make_label(actions, p, -2, True)
            action_label.setStyleSheet(f"color: {css(p.accent)}; font-size: 9px; background: transparent;")
            path = make_label(activity.path, p, -2)
            path.setToolTip(activity.path)
            count = make_label(f"{activity.count} 次", p, -3, secondary=True)
            layout.addWidget(action_label)
            layout.addWidget(path, 1)
            layout.addWidget(count)
            self._layout.addWidget(row)

    def _set_filter(self, key: str) -> None:
        self._filter = key
        self._rebuild()


class CommandsCard(SectionCard):
    def __init__(self, parent=None):
        super().__init__("命令执行", parent)
        self._palette = Palette()
        self._analysis: Optional[SessionAnalysis] = None
        self._host = QWidget(self)
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)
        self._body_layout.addWidget(self._host)

    def set_palette_obj(self, palette: Palette) -> None:
        super().set_palette_obj(palette)
        self._palette = palette
        self._rebuild()

    def set_analysis(self, analysis: SessionAnalysis) -> None:
        self._analysis = analysis
        self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        analysis = self._analysis
        p = self._palette
        if analysis is None:
            self._layout.addWidget(EmptyState("等待会话数据", self))
            return
        total = sum(analysis.command_counts.values())
        self.set_subtitle(f"{fmt_int(total)} 次 · {len(analysis.command_counts)} 个程序")
        if not analysis.command_counts:
            self._layout.addWidget(EmptyState("没有 shell 命令执行记录", self))
            return
        max_count = max(analysis.command_counts.values() or [1])
        for program, count in analysis.command_counts.most_common(20):
            ok, fail = analysis.command_status.get(program, (0, 0))
            row = QFrame(self)
            row.setObjectName("ciCmdRow")
            row.setStyleSheet(
                f"#ciCmdRow {{ background: {css(p.alpha(p.border, 26))}; border-radius: 7px; }}"
            )
            layout = QHBoxLayout(row)
            layout.setContentsMargins(9, 6, 9, 6)
            layout.setSpacing(7)
            bar = BarRow(row)
            bar.set_data(program, count, max_count, p.accent, p)
            bar.setMinimumHeight(16)
            status = make_label(
                f"✓{ok}" + (f" ✗{fail}" if fail else ""),
                p,
                -3,
                secondary=True,
            )
            layout.addWidget(bar, 1)
            layout.addWidget(status)
            self._layout.addWidget(row)


class LedgerCard(SectionCard):
    """通用台账卡（工具 / 技能）。"""

    rowClicked = pyqtSignal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._palette = Palette()
        self._counter: Dict[str, int] = {}
        self._host = QWidget(self)
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)
        self._body_layout.addWidget(self._host)

    def set_palette_obj(self, palette: Palette) -> None:
        super().set_palette_obj(palette)
        self._palette = palette
        self._rebuild()

    def set_data(self, counter: Dict[str, int], limit: int = 10) -> None:
        self._counter = dict(counter or {})
        self._rebuild(limit)

    def _rebuild(self, limit: int = 10) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        p = self._palette
        items = sorted(self._counter.items(), key=lambda kv: -kv[1])[:limit]
        self.set_subtitle(f"{len(self._counter)} 项" if self._counter else "")
        if not items:
            self._layout.addWidget(EmptyState("暂无记录", self))
            return
        max_count = max(v for _, v in items) or 1
        for name, count in items:
            row = BarRow(self)
            row.set_data(name, count, max_count, p.accent, p)
            row.clicked.connect(self.rowClicked)
            self._layout.addWidget(row)
