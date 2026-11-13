# -*- coding: utf-8 -*-
"""上下文洞察全页 —— 跨会话 KPI、7 日用量、活跃热力图、组成、台账与会话卡。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .analyzer import CATEGORY_COLORS, CATEGORY_LABELS, CATEGORY_ORDER
from .cards import LedgerCard
from .charts import BarChart, DonutChart, Heatmap, StackedBar
from .collector import IndexWorker, cached_summaries, scan_state
from .fmt import day_list, fmt_cost, fmt_int, fmt_k, fmt_ts
from .panel import ContextPanel
from .plugin_config import get_config, set_data_root
from .scrollbars import scrollbar_style
from .theme import Palette, apply_tooltip_palette, parse_color
from .widgets import clear_layout, ElidedLabel, EmptyState, KpiCard, LegendList, SectionCard, SegmentedControl, TabStrip, css, css_html, make_label

try:
    from qfluentwidgets import ComboBox as _SortCombo
except Exception:  # pragma: no cover
    from PyQt5.QtWidgets import QComboBox as _SortCombo


_PLUGIN = "context-insight"
_CARD_ID = "context-insights"


class SessionCard(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, palette: Palette, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._session_id = ""
        self.setObjectName("ciSessionCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(250)
        self.setMaximumWidth(360)
        self.setFixedHeight(self._fit_height(palette))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(9)
        self._donut = DonutChart(self)
        self._donut.setFixedSize(56, 56)
        self._donut.set_palette_obj(palette)
        self._donut.segmentClicked.connect(lambda _key: self.clicked.emit(self._session_id))
        layout.addWidget(self._donut)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(2)
        self._title = ElidedLabel("", self)
        self._title.setStyleSheet(f"color: {css(palette.text_primary)}; font-size: {palette.fs(-1)}px; font-weight: 600;")
        self._meta = QLabel(self)
        self._meta.setStyleSheet(f"color: {css(palette.text_secondary)}; font-size: {palette.fs(-3)}px;")
        self._nums = QLabel(self)
        self._nums.setStyleSheet(f"color: {css(palette.text_primary)}; font-size: {palette.fs(-2)}px;")
        self._bar = StackedBar(self)
        self._bar.setFixedHeight(6)
        self._bar.set_palette_obj(palette)
        right.addStretch(1)
        right.addWidget(self._title)
        right.addWidget(self._meta)
        right.addWidget(self._nums)
        right.addWidget(self._bar)
        right.addStretch(1)
        layout.addLayout(right, 1)
        self._apply_style()

    @staticmethod
    def _fit_height(palette: Palette) -> int:
        # 标题/元信息/数值三行 + 进度条 + 间距，随宿主字号缩放
        text = (palette.fs(0) + palette.fs(-2) + palette.fs(-1)) * 1.35
        return max(92, int(18 + text + 14))

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self.setFixedHeight(self._fit_height(palette))
        self._donut.set_palette_obj(palette)
        self._bar.set_palette_obj(palette)
        self._apply_style()
        if hasattr(self, "_last_item"):
            self.set_data(self._last_item)

    def _apply_style(self) -> None:
        p = self._palette
        self.setStyleSheet(
            f"#ciSessionCard {{ background: {css(p.card_bg)}; border: 1px solid {css(p.alpha(p.border, 150))};"
            f" border-radius: 11px; }}"
            f"#ciSessionCard:hover {{ border: 1px solid {css(p.alpha(p.accent, 190))}; }}"
            f"#ciSessionCard QLabel {{ background: transparent; }}"
        )
        # 主题/字号刷新时同步刷三行文字（set_palette_obj 只换卡面不够）
        self._title.setStyleSheet(
            f"color: {css(p.text_primary)}; font-size: {p.fs(0)}px; font-weight: 600;"
        )
        self._meta.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-2)}px;")
        self._nums.setStyleSheet(f"color: {css(p.text_primary)}; font-size: {p.fs(-1)}px;")

    def set_data(self, item: Dict[str, Any]) -> None:
        self._session_id = str(item.get("session_id") or "")
        title = str(item.get("title") or "未命名会话")
        self._title.set_full_text(title)
        project = str(item.get("project") or "默认项目")
        agent = str(item.get("agent_name") or "")
        updated = fmt_ts(str(item.get("updated_at") or ""))
        used = int(item.get("used_tokens", 0) or 0)
        budget = int(item.get("budget_tokens", 0) or 0)
        ctx_text = f"上下文 {int(used / budget * 100)}%" if budget > 0 else "上下文 —"
        self._meta.setText(" · ".join(x for x in (project, agent, updated, ctx_text) if x))
        usage = item.get("usage") or {}
        self._nums.setText(
            f"{fmt_k(usage.get('total', 0))} tokens · {fmt_int(usage.get('turns', 0))} 轮 · "
            f"{fmt_cost(item.get('cost_usd', 0), bool(item.get('cost_known', True)))}"
        )
        comp = item.get("context_latest") or {}
        rows = [
            (key, CATEGORY_LABELS.get(key, key), int(comp.get(key, 0)), parse_color(CATEGORY_COLORS.get(key, "#888888")))
            for key in CATEGORY_ORDER
            if int(comp.get(key, 0) or 0) > 0
        ]
        self._donut.set_data(rows, "", "")
        if budget > 0:
            self._bar.set_data(
                [("used", "已用", min(used, budget), self._palette.accent)],
                [("free", max(0, budget - used), self._palette.alpha(self._palette.border, 120))],
            )
        else:
            self._bar.set_data([])

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._session_id:
            self.clicked.emit(self._session_id)
        super().mousePressEvent(event)


class InsightsPage(QWidget):
    """全页覆盖卡内容。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider = None
        self._ctx: Dict[str, Any] = {}
        self._palette = Palette()
        self._summaries: List[Dict[str, Any]] = []
        self._worker: Optional[IndexWorker] = None
        self._loading = False
        self._range = "7d"
        self._filter_day = ""
        self._search = ""
        self._sort = "recent"
        self._group = False
        self._session_cards: List[SessionCard] = []
        self._current_top = "insights"
        self._build_ui()
        self._apply_palette()

    # ── 宿主契约 ──
    def set_context_provider(self, provider) -> None:
        self._provider = provider
        try:
            self._ctx = provider() if provider else {}
        except Exception:
            self._ctx = {}
        panel = getattr(self, "_session_panel", None)
        if panel is not None:
            panel.set_context_provider(provider)
        # 宿主的 font_size 在 ctx 里，provider 注入后立刻按新字号重刷
        if hasattr(self, "_kpis"):
            self._apply_palette()

    def show_card(self) -> None:
        self._ctx = self._provider() if self._provider else self._ctx
        caps = self._ctx.get("capabilities") or {}
        data_dir = caps.get("storage.data_dir") if hasattr(caps, "get") else None
        if data_dir:
            set_data_root(data_dir)
        self._range = self._read_default_range()
        self._range_control.set_current(self._range)
        self._apply_palette()
        if self._current_top == "session":
            self._session_panel.set_context_provider(self._provider)
            self._session_panel.show_card()
        else:
            self._start_scan()

    def show_tab(self, key: str) -> None:
        """外部入口（/context）切到指定顶级 tab。"""
        self._on_top_tab(key)

    def refresh_theme(self) -> None:
        self._apply_palette()

    # ── UI ──
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget(self)
        header.setObjectName("ciInsightsHeader")
        head = QVBoxLayout(header)
        head.setContentsMargins(18, 14, 18, 8)
        head.setSpacing(6)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        title = QLabel("上下文洞察", header)
        title.setStyleSheet("font-size: 18px; font-weight: 700; background: transparent;")
        subtitle = QLabel("跨会话用量、组成、活动与 Agent 编队", header)
        subtitle.setStyleSheet("font-size: 11px; background: transparent;")
        self._title = title
        self._subtitle = subtitle
        row.addWidget(title)
        row.addWidget(subtitle)
        row.addStretch(1)
        self._range_control = SegmentedControl(
            [("today", "今天"), ("7d", "7 天"), ("30d", "30 天"), ("all", "全部")],
            self._range,
            header,
        )
        self._range_control.changed.connect(self._on_range)
        row.addWidget(self._range_control)
        self._btn_refresh = QPushButton("刷新", header)
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.clicked.connect(self._refresh_current)
        self._btn_settings = QPushButton("设置", header)
        self._btn_settings.setCursor(Qt.PointingHandCursor)
        self._btn_settings.clicked.connect(self._open_settings)
        row.addWidget(self._btn_refresh)
        row.addWidget(self._btn_settings)
        head.addLayout(row)
        self._top_tabs = TabStrip(
            [("insights", "洞察"), ("session", "会话上下文")], "insights", header
        )
        self._top_tabs.changed.connect(self._on_top_tab)
        head.addWidget(self._top_tabs)
        self._status = QLabel("", header)
        self._status.setStyleSheet("font-size: 10px; background: transparent;")
        head.addWidget(self._status)
        root.addWidget(header)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.viewport().setStyleSheet("background: transparent;")
        body = QWidget(self._scroll)
        body.setStyleSheet("background: transparent;")
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(18, 6, 18, 20)
        self._body.setSpacing(12)
        self._scroll.setWidget(body)

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._scroll)
        self._session_panel = ContextPanel(self, embedded=True)
        self._session_panel.set_context_provider(self._provider)
        self._stack.addWidget(self._session_panel)
        root.addWidget(self._stack, 1)

        # KPI
        self._kpi_host = QWidget(body)
        self._kpi_layout = QHBoxLayout(self._kpi_host)
        self._kpi_layout.setContentsMargins(0, 0, 0, 0)
        self._kpi_layout.setSpacing(10)
        self._kpis: Dict[str, KpiCard] = {}
        for key, label in (
            ("tokens", "计费 Token"),
            ("cost", "预估成本"),
            ("cache", "缓存命中率"),
            ("turns", "轮次 / 请求"),
            ("sessions", "活跃会话"),
        ):
            card = KpiCard(label)
            self._kpis[key] = card
            self._kpi_layout.addWidget(card, 1)
        self._body.addWidget(self._kpi_host)

        # 7 日用量 + 组成
        charts_row = QHBoxLayout()
        charts_row.setContentsMargins(0, 0, 0, 0)
        charts_row.setSpacing(12)
        self._usage_card = SectionCard("7 日用量", body)
        self._usage_card.set_subtitle("柱 = Token · 折线 = 成本")
        self._usage_chart = BarChart(self._usage_card)
        self._usage_card.add_widget(self._usage_chart)
        charts_row.addWidget(self._usage_card, 3)

        self._composition_card = SectionCard("计费组成", body)
        self._composition_donut = DonutChart(self._composition_card)
        self._composition_donut.setMinimumHeight(150)
        self._composition_card.add_widget(self._composition_donut, 1)
        self._composition_legend = LegendList(self._composition_card)
        self._composition_card.add_widget(self._composition_legend)
        charts_row.addWidget(self._composition_card, 2)
        self._body.addLayout(charts_row)

        # 热力图
        self._heat_card = SectionCard("活动热力图", body)
        self._heat_card.set_subtitle("最近 16 周每日计费 Token · 点击某天筛选")
        self._heatmap = Heatmap(self._heat_card)
        self._heatmap.dayClicked.connect(self._on_day)
        heat_row = QHBoxLayout()
        heat_row.setContentsMargins(0, 0, 0, 0)
        heat_row.setSpacing(16)
        self._heatmap.setFixedWidth(580)
        heat_row.addWidget(self._heatmap)
        self._heat_summary = QLabel("", self._heat_card)
        self._heat_summary.setWordWrap(True)
        self._heat_summary.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        heat_row.addWidget(self._heat_summary, 1)
        self._heat_card.add_layout(heat_row)
        self._body.addWidget(self._heat_card)

        # 台账
        ledger_row = QHBoxLayout()
        ledger_row.setContentsMargins(0, 0, 0, 0)
        ledger_row.setSpacing(12)
        self._skills_card = LedgerCard("技能加载", body)
        self._tools_card = LedgerCard("工具调用", body)
        self._commands_card = LedgerCard("命令执行", body)
        ledger_row.addWidget(self._skills_card, 1)
        ledger_row.addWidget(self._tools_card, 1)
        ledger_row.addWidget(self._commands_card, 1)
        self._body.addLayout(ledger_row)

        # 会话列表
        sessions_card = SectionCard("会话", body)
        self._sessions_card = sessions_card
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        self._search_edit = QLineEdit(sessions_card)
        self._search_edit.setPlaceholderText("搜索标题 / 项目 / 智能体")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search)
        self._search_edit.setFixedHeight(28)
        controls.addWidget(self._search_edit, 1)
        self._sort_combo = _SortCombo(sessions_card)
        self._sort_combo.addItem("最近活动", userData="recent")
        self._sort_combo.addItem("Token 从多到少", userData="tokens")
        self._sort_combo.addItem("上下文占用", userData="context")
        self._sort_combo.currentIndexChanged.connect(self._on_sort)
        self._sort_combo.setFixedHeight(28)
        controls.addWidget(self._sort_combo)
        self._group_btn = QPushButton("按项目分组", sessions_card)
        self._group_btn.setCheckable(True)
        self._group_btn.setCursor(Qt.PointingHandCursor)
        self._group_btn.toggled.connect(self._on_group)
        self._group_btn.setFixedHeight(28)
        controls.addWidget(self._group_btn)
        self._filter_hint = QLabel("", sessions_card)
        self._filter_hint.setStyleSheet("font-size: 10px;")
        controls.addWidget(self._filter_hint)
        sessions_card.add_layout(controls)
        self._cards_host = QWidget(sessions_card)
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        sessions_card.add_widget(self._cards_host)
        self._body.addWidget(sessions_card)
        self._body.addStretch(1)

        self._empty = EmptyState("正在扫描会话库…", body)
        self._body.insertWidget(self._body.count() - 1, self._empty)

    # ── 主题 ──
    def _apply_palette(self) -> None:
        self._palette = Palette(self._ctx)
        apply_tooltip_palette(self._palette)
        p = self._palette
        self.setStyleSheet(
            f"#ciInsightsHeader {{ background: transparent; }}"
            f"QWidget {{ color: {css(p.text_primary)}; }}"
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QWidget#qt_scrollarea_viewport {{ background: transparent; }}"
            f"QLineEdit {{ background: {css(p.alpha(p.border, 28))}; color: {css(p.text_primary)};"
            f" border: 1px solid {css(p.alpha(p.border, 140))}; border-radius: 7px; padding: 3px 8px;"
            f" font-size: {p.fs(-1)}px; }}"
            f"QComboBox {{ background: {css(p.alpha(p.border, 28))}; color: {css(p.text_primary)};"
            f" border: 1px solid {css(p.alpha(p.border, 140))}; border-radius: 7px; padding: 2px 8px;"
            f" font-size: {p.fs(-1)}px; }}"
            f"QComboBox QAbstractItemView {{ background: {css(p.content_bg)}; color: {css(p.text_primary)};"
            f" selection-background-color: {css(p.accent)}; }}"
            f"QPushButton {{ background: {css(p.alpha(p.border, 28))}; color: {css(p.text_primary)};"
            f" border: 1px solid {css(p.alpha(p.border, 140))}; border-radius: 7px; padding: 3px 10px;"
            f" font-size: {p.fs(-1)}px; }}"
            f"QPushButton:hover {{ border-color: {css(p.accent)}; }}"
            f"QPushButton:checked {{ background: {css(p.alpha(p.accent, 40))}; border-color: {css(p.accent)}; }}"
            + scrollbar_style(p, 8)
        )
        self._title.setStyleSheet(f"color: {css(p.text_primary)}; font-size: {p.fs(2)}px; font-weight: 700;")
        self._subtitle.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-2)}px;")
        self._status.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-3)}px;")
        self._filter_hint.setStyleSheet(f"color: {css(p.accent)}; font-size: {p.fs(-3)}px;")
        self._range_control.set_palette_obj(p)
        self._top_tabs.set_palette_obj(p)
        if hasattr(self, "_session_panel"):
            self._session_panel.refresh_theme()
        for card in self._kpis.values():
            card.set_palette_obj(p)
        for card in (
            self._usage_card,
            self._composition_card,
            self._heat_card,
            self._skills_card,
            self._tools_card,
            self._commands_card,
            self._sessions_card,
        ):
            card.set_palette_obj(p)
        self._usage_chart.set_palette_obj(p)
        self._composition_donut.set_palette_obj(p)
        self._composition_legend.set_palette_obj(p)
        self._heatmap.set_palette_obj(p)
        self._heat_summary.setStyleSheet(f"color: {css(p.text_primary)}; background: transparent;")
        self._empty.set_palette_obj(p)
        for card in self._session_cards:
            card.set_palette_obj(p)

    # ── 扫描 ──
    def _start_scan(self, force: bool = False) -> None:
        if self._loading:
            return
        caps = self._ctx.get("capabilities") or {}
        history = caps.get("session.history") if hasattr(caps, "get") else None
        if not history:
            self._status.setText("宿主未提供 session.history 能力")
            self._empty.set_text("无法读取会话历史：缺少 session.history 能力")
            return
        # 磁盘快照先上屏：缓存命中时零等待，后台再做增量校验
        snapshot = cached_summaries()
        if snapshot:
            self._summaries = snapshot
            self._status.setText(f"已载入 {len(snapshot)} 个会话")
            self._render_all()
        scanning, scan_age = scan_state()
        if scanning or (not force and snapshot and scan_age < 15):
            if not snapshot:
                self._status.setText("扫描中…")
                self._empty.set_text("正在扫描会话库…")
                # 别的页发起的扫描：轮询等它落地，否则本页会停在空态
                self._await_scan()
            return
        self._loading = True
        if not snapshot:
            self._empty.set_text("正在扫描会话库…")
        self._status.setText("扫描中…")
        worker = IndexWorker(history, self)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_index)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_scan_done)
        self._worker = worker
        worker.start()

    def _await_scan(self, tries: int = 30) -> None:
        """等外部发起的扫描结束，再拿内存快照渲染。"""
        scanning, _ = scan_state()
        if not scanning:
            snapshot = cached_summaries()
            if snapshot:
                self._summaries = snapshot
                self._status.setText(f"已载入 {len(snapshot)} 个会话")
                self._render_all()
            return
        if tries > 0:
            QTimer.singleShot(400, lambda: self._await_scan(tries - 1))

    def _on_scan_done(self) -> None:
        self._loading = False

    def _on_progress(self, done: int, total: int) -> None:
        self._status.setText(f"扫描中… {done}/{total}")

    def _on_failed(self, message: str) -> None:
        self._status.setText(f"扫描失败：{message}")
        self._empty.set_text(f"扫描失败：{message}")

    def _on_index(self, summaries: list) -> None:
        self._summaries = [s for s in summaries if isinstance(s, dict)]
        self._status.setText(f"已载入 {len(self._summaries)} 个会话")
        self._render_all()

    # ── 聚合 ──
    def _range_days(self) -> int:
        return {"today": 1, "7d": 7, "30d": 30, "all": 36500}.get(self._range, 7)

    def _cutoff_date(self) -> date:
        return (datetime.now() - timedelta(days=self._range_days() - 1)).date()

    def _active_items(self) -> List[Dict[str, Any]]:
        if self._range == "all" and not self._filter_day:
            return list(self._summaries)
        cutoff = self._cutoff_date().isoformat()
        out = []
        for item in self._summaries:
            if self._filter_day:
                if self._filter_day in (item.get("daily") or {}):
                    out.append(item)
                elif str(item.get("updated_at", ""))[:10] == self._filter_day:
                    out.append(item)
                continue
            updated = str(item.get("updated_at") or "")[:10]
            if updated >= cutoff:
                out.append(item)
        return out

    def _range_usage(self, item: Dict[str, Any]) -> Tuple[int, int, int]:
        """返回 (input, output, requests) 限定在当前范围/筛选日。"""
        daily = item.get("daily") or {}
        if self._filter_day:
            slot = daily.get(self._filter_day)
            if slot:
                return int(slot[0]), int(slot[1]), int(slot[2])
            usage = item.get("usage") or {}
            if str(item.get("updated_at", ""))[:10] == self._filter_day:
                return int(usage.get("input", 0)), int(usage.get("output", 0)), int(usage.get("requests", 0))
            return 0, 0, 0
        if self._range == "all" or not daily:
            usage = item.get("usage") or {}
            return int(usage.get("input", 0)), int(usage.get("output", 0)), int(usage.get("requests", 0))
        cutoff = self._cutoff_date().isoformat()
        in_sum = out_sum = req = 0
        for day, slot in daily.items():
            if str(day) >= cutoff:
                in_sum += int(slot[0])
                out_sum += int(slot[1])
                req += int(slot[2])
        return in_sum, out_sum, req

    def _range_cost(self, item: Dict[str, Any]) -> float:
        usage = item.get("usage") or {}
        total = int(usage.get("total", 0) or 0)
        if total <= 0:
            return 0.0
        rin, rout, _ = self._range_usage(item)
        return float(item.get("cost_usd", 0) or 0) * (rin + rout) / total

    def _range_composition(self, item: Dict[str, Any]) -> Dict[str, int]:
        comp = {k: int(v) for k, v in (item.get("context_total") or {}).items() if int(v) > 0}
        usage = item.get("usage") or {}
        total = int(usage.get("total", 0) or 0)
        rin, rout, _ = self._range_usage(item)
        target = rin + rout
        # 无 usage 的会话没有可靠的计费拆分，直接置空，避免组成总量比 KPI 多出
        # 几百万；有 usage 的会话按「范围用量 / 该会话累计组成」等比缩放，保证
        # 环形图总量与 KPI 严格一致（context_total 含估算步骤，通常大于计费用量）。
        if total <= 0 or target <= 0:
            return {}
        comp_total = sum(comp.values())
        if comp_total <= 0:
            return {"overhead": target}
        ratio = target / comp_total
        out = {k: int(v * ratio) for k, v in comp.items()}
        diff = target - sum(out.values())
        if diff and out:
            last = max(out, key=lambda k: out[k])
            out[last] = max(1, out[last] + diff)
        return out

    # ── 渲染 ──
    def _render_all(self) -> None:
        items = self._active_items()
        total_in = total_out = total_req = 0
        total_cost = 0.0
        turns = 0
        for item in items:
            rin, rout, req = self._range_usage(item)
            total_in += rin
            total_out += rout
            total_req += req
            total_cost += self._range_cost(item)
            turns += int((item.get("usage") or {}).get("turns", 0))
        total_tokens = total_in + total_out
        self._kpis["tokens"].set_value(fmt_k(total_tokens), f"{fmt_k(total_in)} in / {fmt_k(total_out)} out")
        self._kpis["cost"].set_value(fmt_cost(total_cost), "按 models.dev 标价")
        self._kpis["cache"].set_value("—", "仅活跃会话可读")
        self._kpis["turns"].set_value(f"{fmt_int(turns)} / {fmt_int(total_req)}", "轮次 / API 请求")
        self._kpis["sessions"].set_value(fmt_int(len(items)), f"范围 {self._range_label()}")
        self._render_usage(items)
        self._render_composition(items)
        self._render_heatmap()
        self._render_ledgers(items)
        self._render_sessions(items)
        has_data = bool(self._summaries)
        self._empty.setVisible(not has_data)
        if not has_data:
            self._empty.set_text("会话库为空")

    def _range_label(self) -> str:
        if self._filter_day:
            return self._filter_day
        return {"today": "今天", "7d": "7 天", "30d": "30 天", "all": "全部"}.get(self._range, self._range)

    def _render_usage(self, items: List[Dict[str, Any]]) -> None:
        days = day_list(7)
        values = {d: 0 for d in days}
        costs = {d: 0.0 for d in days}
        for item in items:
            daily = item.get("daily") or {}
            usage = item.get("usage") or {}
            total = int(usage.get("total", 0) or 0)
            for day, slot in daily.items():
                if day in values:
                    tokens = int(slot[0]) + int(slot[1])
                    values[day] += tokens
                    if total > 0:
                        costs[day] += float(item.get("cost_usd", 0) or 0) * tokens / total
        labels = [d[5:] for d in days]
        self._usage_chart.set_data(labels, [values[d] for d in days], [costs[d] for d in days])

    def _render_composition(self, items: List[Dict[str, Any]]) -> None:
        total_comp: Dict[str, int] = {}
        for item in items:
            for key, value in self._range_composition(item).items():
                total_comp[key] = total_comp.get(key, 0) + int(value)
        rows = [
            (key, CATEGORY_LABELS.get(key, key), int(total_comp.get(key, 0)), parse_color(CATEGORY_COLORS.get(key, "#888888")))
            for key in CATEGORY_ORDER
            if int(total_comp.get(key, 0) or 0) > 0
        ]
        rows.sort(key=lambda r: -r[2])
        total = sum(r[2] for r in rows)
        self._composition_card.set_subtitle(fmt_int(total) + " tokens")
        self._composition_donut.set_data(rows, fmt_k(total), "计费组成")
        self._composition_legend.set_data(rows, total)

    def _render_heatmap(self) -> None:
        values: Dict[str, int] = {}
        for item in self._summaries:
            for day, slot in (item.get("daily") or {}).items():
                values[day] = values.get(day, 0) + int(slot[0]) + int(slot[1])
        self._heatmap.set_data(values)
        # 右侧统计：活跃天数 / 峰值日 / 16 周合计
        recent = day_list(16 * 7)
        active = [d for d in recent if values.get(d, 0) > 0]
        total = sum(values.get(d, 0) for d in recent)
        peak_day = max(recent, key=lambda d: values.get(d, 0)) if recent else ""
        peak = values.get(peak_day, 0) if peak_day else 0
        p = self._palette
        top_days = sorted(recent, key=lambda d: values.get(d, 0), reverse=True)[:5]
        top_lines = "".join(
            f"<div style='color:{css_html(p.text_secondary)};font-size:{p.fs(-2)}px;margin-top:2px'>"
            f"{d} <span style='color:{css_html(p.text_primary)}'>{fmt_k(values.get(d, 0))}</span></div>"
            for d in top_days
            if values.get(d, 0) > 0
        )
        self._heat_summary.setText(
            f"<div style='font-size:{p.fs(-1)}px;color:{css_html(p.text_primary)}'>"
            f"<b>{len(active)}</b> 天有活动 <span style='color:{css_html(p.text_secondary)}'>/ 112 天</span><br/>"
            f"<b>{fmt_k(total)}</b> tokens <span style='color:{css_html(p.text_secondary)}'>16 周合计</span><br/>"
            f"<b>{fmt_k(peak)}</b> tokens <span style='color:{css_html(p.text_secondary)}'>峰值 {peak_day or '—'}</span>"
            f"<div style='margin-top:8px;color:{css_html(p.text_primary)};font-size:{p.fs(-2)}px'>最活跃的 5 天</div>"
            f"{top_lines}</div>"
        )

    def _render_ledgers(self, items: List[Dict[str, Any]]) -> None:
        tools: Dict[str, int] = {}
        skills: Dict[str, int] = {}
        commands: Dict[str, int] = {}
        for item in items:
            for key, value in (item.get("tool_counts") or {}).items():
                tools[key] = tools.get(key, 0) + int(value)
            for key, value in (item.get("skill_counts") or {}).items():
                skills[key] = skills.get(key, 0) + int(value)
            for key, value in (item.get("command_counts") or {}).items():
                commands[key] = commands.get(key, 0) + int(value)
        self._tools_card.set_data(tools)
        self._skills_card.set_data(skills)
        self._commands_card.set_data(commands)

    def _visible_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        text = (self._search or "").strip().lower()
        out = []
        for item in items:
            if text:
                haystack = " ".join(
                    str(item.get(k) or "")
                    for k in ("title", "project", "agent_name", "team_name", "models")
                ).lower()
                if text not in haystack:
                    continue
            out.append(item)
        if self._sort == "tokens":
            out.sort(key=lambda i: -(int((i.get("usage") or {}).get("total", 0))))
        elif self._sort == "context":
            out.sort(key=lambda i: -(int(i.get("used_tokens", 0))))
        else:
            out.sort(key=lambda i: str(i.get("updated_at") or ""), reverse=True)
        return out

    def _render_sessions(self, items: List[Dict[str, Any]]) -> None:
        clear_layout(self._cards_layout)
        self._session_cards = []
        visible = self._visible_items(items)
        self._filter_hint.setText(f"筛选：{self._filter_day}" if self._filter_day else "")
        if not visible:
            self._cards_layout.addWidget(EmptyState("没有匹配的会话", self._cards_host))
            return
        if self._group:
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for item in visible:
                groups.setdefault(str(item.get("project") or "默认项目"), []).append(item)
            for project, group in groups.items():
                header = make_label(project, self._palette, 0, True)
                header.setContentsMargins(2, 6, 2, 0)
                self._cards_layout.addWidget(header)
                self._cards_layout.addWidget(self._make_grid(group))
        else:
            self._cards_layout.addWidget(self._make_grid(visible))

    def _make_grid(self, items: List[Dict[str, Any]]) -> QWidget:
        host = QWidget(self._cards_host)
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        cols = 3
        for i, item in enumerate(items[:60]):
            card = SessionCard(self._palette, host)
            card.clicked.connect(self._open_session)
            card.set_data(item)
            card._last_item = item  # type: ignore[attr-defined]
            grid.addWidget(card, i // cols, i % cols)
            self._session_cards.append(card)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        return host

    # ── 交互 ──
    def _on_top_tab(self, key: str) -> None:
        if key not in ("insights", "session"):
            return
        self._current_top = key
        self._top_tabs.set_current(key)
        self._stack.setCurrentIndex(1 if key == "session" else 0)
        self._range_control.setVisible(key == "insights")
        self._status.setVisible(key == "insights")
        if key == "session":
            self._session_panel.set_context_provider(self._provider)
            self._session_panel.show_card()

    def _refresh_current(self) -> None:
        if self._current_top == "session":
            self._session_panel.set_context_provider(self._provider)
            self._session_panel.show_card()
        else:
            self._start_scan(force=True)

    def _on_range(self, key: str) -> None:
        self._range = key
        self._filter_day = ""
        self._render_all()

    def _on_day(self, day: str) -> None:
        self._filter_day = day
        self._render_all()

    def _on_search(self, text: str) -> None:
        self._search = text
        self._render_sessions(self._active_items())

    def _on_sort(self, _index: int) -> None:
        self._sort = str(self._sort_combo.currentData() or "recent")
        self._render_sessions(self._active_items())

    def _on_group(self, checked: bool) -> None:
        self._group = bool(checked)
        self._render_sessions(self._active_items())

    def _open_session(self, session_id: str) -> None:
        ok = False
        caps = self._ctx.get("capabilities") or {}
        manage = caps.get("session.manage") if hasattr(caps, "get") else None
        try:
            if manage is not None:
                select = manage.get("select") if hasattr(manage, "get") else None
                if callable(select):
                    ok = bool(select(session_id))
        except Exception as e:
            logger.debug(f"[context-insight] 切换会话失败: {e}")
        if ok:
            hide = caps.get("ui.card.hide") if hasattr(caps, "get") else None
            if callable(hide):
                try:
                    hide(_CARD_ID)
                except Exception:
                    pass
        else:
            self._status.setText("打开会话失败（宿主未提供 session.manage 能力）")

    def _open_settings(self) -> None:
        caps = self._ctx.get("capabilities") or {}
        notify = caps.get("ui.notify") if hasattr(caps, "get") else None
        if callable(notify):
            try:
                notify("上下文洞察", "请到 设置 → 插件 → 上下文洞察偏好 修改", "info")
                return
            except Exception:
                pass
        self._status.setText("请在 设置 → 插件 → 上下文洞察偏好 中修改")

    def _read_default_range(self) -> str:
        value = get_config("default_range", "7d")
        return str(value) if value in ("today", "7d", "30d", "all") else "7d"

    def shutdown(self) -> None:
        """插件卸载前停掉扫描线程并递归停掉内嵌会话面板。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            try:
                worker.stop()
                worker.wait(2000)
            except Exception:
                pass
        panel = getattr(self, "_session_panel", None)
        if panel is not None and hasattr(panel, "shutdown"):
            try:
                panel.shutdown()
            except Exception:
                pass
