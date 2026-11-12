# -*- coding: utf-8 -*-
"""会话级 Context 面板 —— 嵌入全页洞察卡的「会话上下文」tab。

包含概览/组成/趋势/事件/浏览/文件/命令/编队八个子 tab；数据由 DetailWorker
在后台分析当前会话，流式落定时按开关节流刷新。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from loguru import logger
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .analyzer import SessionAnalysis
from .browser import ContextBrowser
from .cards import (
    CommandsCard,
    CompositionCard,
    CurrentContextCard,
    EventsCard,
    FilesCard,
    StatsCard,
    TimingCard,
)
from .charts import TrendChart
from .trend import TrendList
from .collector import DetailWorker, cached_summaries, IndexWorker
from .fleet import FleetWidget
from .fmt import fmt_cost, fmt_int, fmt_k
from .scrollbars import scrollbar_style
from .plugin_config import get_config, set_data_root
from .teamcomms import append_snapshot, build_lane_roster, gather_team_comms, load_snapshot
from .theme import Palette, apply_tooltip_palette
from .widgets import LegendChips, SegmentedControl, SectionCard, TabStrip, css


class _ScrollPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }" + scrollbar_style(Palette(), 8))
        self.viewport().setAutoFillBackground(False)
        self.viewport().setStyleSheet("background: transparent;")
        self._body = QWidget(self)
        self._body.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(10, 8, 10, 12)
        self._layout.setSpacing(10)
        self.setWidget(self._body)

    def body_layout(self) -> QVBoxLayout:
        return self._layout


class ContextPanel(QWidget):
    """会话级 Context 面板。宿主注入 ctx provider，首次显示时统一刷新。"""

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = bool(embedded)
        self._provider = None
        self._ctx: Dict[str, Any] = {}
        self._palette = Palette()
        self._analysis: Optional[SessionAnalysis] = None
        self._session_id = ""
        self._worker: Optional[DetailWorker] = None
        self._index_worker: Optional[IndexWorker] = None
        self._index_requested = False
        self._loading = False
        self._last_refresh = 0.0
        self._subscribed = False
        self._tabs: Dict[str, QWidget] = {}
        self._pending_refresh = False
        self._trend_selected = -1
        self._build_ui()
        self._apply_palette()

    # ── 宿主契约 ──
    def set_context_provider(self, provider) -> None:
        self._provider = provider
        try:
            self._ctx = provider() if provider else {}
        except Exception:
            self._ctx = {}
        if hasattr(self, "_tabs_bar"):
            self._apply_palette()

    def show_card(self) -> None:
        self._ctx = self._provider() if self._provider else self._ctx
        caps = self._ctx.get("capabilities") or {}
        data_dir = caps.get("storage.data_dir") if hasattr(caps, "get") else None
        if data_dir:
            set_data_root(data_dir)
        self._apply_palette()
        self._subscribe_once()
        self._refresh_data(force=True)

    def refresh_theme(self) -> None:
        self._apply_palette()

    # ── UI 构建 ──
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget(self)
        header.setObjectName("ciPanelHeader")
        head = QVBoxLayout(header)
        head.setContentsMargins(12, 10, 12, 6)
        head.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        self._title = QLabel("上下文", header)
        self._title.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent;")
        self._subtitle = QLabel("", header)
        self._subtitle.setStyleSheet("font-size: 10px; background: transparent;")
        title_row.addWidget(self._title)
        title_row.addWidget(self._subtitle, 1)
        self._btn_refresh = QPushButton("↻", header)
        self._btn_refresh.setFixedSize(24, 24)
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.setToolTip("刷新")
        self._btn_refresh.clicked.connect(lambda: self._refresh_data(force=True))
        self._btn_settings = QPushButton("⚙", header)
        self._btn_settings.setFixedSize(24, 24)
        self._btn_settings.setCursor(Qt.PointingHandCursor)
        self._btn_settings.setToolTip("打开上下文洞察偏好设置")
        self._btn_settings.clicked.connect(self._open_settings)
        title_row.addWidget(self._btn_refresh)
        title_row.addWidget(self._btn_settings)
        if self._embedded:
            self._title.hide()
            self._btn_refresh.hide()
            self._btn_settings.hide()
        head.addLayout(title_row)

        # 顶部摘要
        summary = QHBoxLayout()
        summary.setContentsMargins(0, 4, 0, 0)
        summary.setSpacing(8)
        self._summary = QLabel("等待数据", header)
        self._summary.setStyleSheet("font-size: 10px; background: transparent;")
        self._summary.setWordWrap(True)
        summary.addWidget(self._summary, 1)
        head.addLayout(summary)
        root.addWidget(header)

        self._tabs_bar = TabStrip(
            [
                ("overview", "概览"),
                ("composition", "组成"),
                ("trend", "趋势"),
                ("events", "事件"),
                ("browser", "浏览"),
                ("files", "文件"),
                ("commands", "命令"),
                ("fleet", "编队"),
            ],
            "overview",
            self,
        )
        self._tabs_bar.changed.connect(self._switch_tab)
        tab_host = QWidget(self)
        tab_layout = QHBoxLayout(tab_host)
        tab_layout.setContentsMargins(10, 0, 10, 0)
        tab_layout.addWidget(self._tabs_bar)
        root.addWidget(tab_host)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack, 1)

        # 概览
        page = _ScrollPage(self)
        self._stats_card = StatsCard(page)
        self._current_card = CurrentContextCard(page)
        self._timing_card = TimingCard(page)
        page.body_layout().addWidget(self._stats_card)
        page.body_layout().addWidget(self._current_card)
        page.body_layout().addWidget(self._timing_card)
        page.body_layout().addStretch(1)
        self._register_tab("overview", page)
        self._overview_page = page

        # 组成
        page = _ScrollPage(self)
        self._composition_card = CompositionCard("Token 组成", True, page)
        page.body_layout().addWidget(self._composition_card)
        page.body_layout().addStretch(1)
        self._register_tab("composition", page)

        # 趋势
        page = _ScrollPage(self)
        controls = SectionCard("上下文趋势", page)
        self._trend_controls = controls
        ctrl_row = QHBoxLayout()
        ctrl_row.setContentsMargins(0, 0, 0, 0)
        ctrl_row.setSpacing(8)
        self._granularity = SegmentedControl(
            [("step", "按请求"), ("turn", "按轮次")], "step", controls
        )
        self._mode = SegmentedControl([("total", "累计组成"), ("delta", "单次变化")], "total", controls)
        self._layout_mode = SegmentedControl(
            [("vertical", "竖向"), ("horizontal", "横向")], "vertical", controls
        )
        self._granularity.changed.connect(self._on_granularity)
        self._mode.changed.connect(lambda _k: self._render_trend())
        self._layout_mode.changed.connect(lambda _k: self._apply_trend_layout())
        ctrl_row.addWidget(self._granularity)
        ctrl_row.addWidget(self._mode)
        ctrl_row.addWidget(self._layout_mode)
        ctrl_row.addStretch(1)
        controls.add_layout(ctrl_row)
        self._trend_card = controls
        self._trend_summary = QLabel("", controls)
        self._trend_summary.setWordWrap(True)
        self._trend_summary.setStyleSheet("font-size: 12px; background: transparent;")
        controls.add_widget(self._trend_summary)
        self._trend_legend = LegendChips(controls)
        controls.add_widget(self._trend_legend)
        self._trend_list = TrendList(controls)
        self._trend_list.stepClicked.connect(self._on_trend_step)
        controls.add_widget(self._trend_list)
        self._trend_chart = TrendChart(controls)
        self._trend_chart.stepClicked.connect(self._on_trend_step)
        self._trend_chart.setVisible(False)
        controls.add_widget(self._trend_chart)
        page.body_layout().addWidget(controls)
        page.body_layout().addStretch(1)
        self._register_tab("trend", page)

        # 事件
        page = _ScrollPage(self)
        self._events_card = EventsCard(page)
        page.body_layout().addWidget(self._events_card)
        page.body_layout().addStretch(1)
        self._register_tab("events", page)

        # 浏览
        page = QWidget(self)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(10, 8, 10, 10)
        self._browser = ContextBrowser(page)
        page_layout.addWidget(self._browser, 1)
        self._register_tab("browser", page)

        # 文件
        page = _ScrollPage(self)
        self._files_card = FilesCard(page)
        page.body_layout().addWidget(self._files_card)
        page.body_layout().addStretch(1)
        self._register_tab("files", page)

        # 命令
        page = _ScrollPage(self)
        self._commands_card = CommandsCard(page)
        page.body_layout().addWidget(self._commands_card)
        page.body_layout().addStretch(1)
        self._register_tab("commands", page)

        # 编队
        page = _ScrollPage(self)
        self._fleet = FleetWidget(page)
        page.body_layout().addWidget(self._fleet)
        page.body_layout().addStretch(1)
        self._register_tab("fleet", page)

        root.addWidget(self._stack)

    def _register_tab(self, key: str, page: QWidget) -> None:
        self._tabs[key] = page
        self._stack.addWidget(page)

    # ── 主题 ──
    def _apply_palette(self) -> None:
        self._palette = Palette(self._ctx)
        apply_tooltip_palette(self._palette)
        p = self._palette
        self.setStyleSheet(
            f"#ciPanelHeader {{ background: transparent; }}"
            f"QWidget {{ color: {css(p.text_primary)}; }}"
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QWidget#qt_scrollarea_viewport {{ background: transparent; }}"
        )
        self._title.setStyleSheet(f"color: {css(p.text_primary)}; font-size: {p.fs(-1)}px; font-weight: 600;")
        self._subtitle.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-3)}px;")
        self._summary.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-3)}px;")
        btn_qss = (
            f"QPushButton {{ background: transparent; color: {css(p.text_secondary)}; border: none;"
            f" border-radius: 6px; font-size: {p.fs(0)}px; }}"
            f"QPushButton:hover {{ background: {css(p.hover_bg)}; color: {css(p.text_primary)}; }}"
        )
        self._btn_refresh.setStyleSheet(btn_qss)
        self._btn_settings.setStyleSheet(btn_qss)
        self._tabs_bar.set_palette_obj(p)
        self._stats_card.set_palette_obj(p)
        self._current_card.set_palette_obj(p)
        self._timing_card.set_palette_obj(p)
        self._composition_card.set_palette_obj(p)
        self._events_card.set_palette_obj(p)
        self._files_card.set_palette_obj(p)
        self._commands_card.set_palette_obj(p)
        self._browser.set_palette_obj(p)
        self._fleet.set_palette_obj(p)
        self._trend_controls.set_palette_obj(p)
        self._granularity.set_palette_obj(p)
        self._mode.set_palette_obj(p)
        self._layout_mode.set_palette_obj(p)
        self._trend_list.set_palette_obj(p)
        self._trend_chart.set_palette_obj(p)
        self._trend_legend.set_palette_obj(p)
        self._trend_summary.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-1)}px;")
        for page in self.findChildren(_ScrollPage):
            page.setStyleSheet("QScrollArea { background: transparent; border: none; }" + scrollbar_style(p, 8))

    # ── 数据 ──
    def _resolve_session_id(self) -> str:
        return str(self._ctx.get("session_id") or "")

    def _refresh_data(self, force: bool = False) -> None:
        if self._loading:
            self._pending_refresh = True
            return
        self._session_id = self._resolve_session_id()
        if not self._session_id:
            self._summary.setText("没有活跃会话")
            return
        caps = self._ctx.get("capabilities") or {}
        history = caps.get("session.history") if hasattr(caps, "get") else None
        if not history:
            self._summary.setText("宿主未提供 session.history 能力")
            return
        if not force and time.monotonic() - self._last_refresh < 0.8:
            return
        self._last_refresh = time.monotonic()
        self._loading = True
        self._summary.setText("正在分析上下文…")
        schema_fn = caps.get("model.schema") if hasattr(caps, "get") else None
        worker = DetailWorker(
            self._session_id,
            history=history,
            schema_fn=schema_fn,
            parent=self,
        )
        worker.finished_ok.connect(self._on_analysis)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_done)
        self._worker = worker
        worker.start()

    def _on_worker_done(self) -> None:
        self._loading = False
        if self._pending_refresh:
            self._pending_refresh = False
            QTimer.singleShot(60, lambda: self._refresh_data(force=True))

    def _on_failed(self, message: str) -> None:
        self._summary.setText(f"分析失败：{message}")
        logger.warning(f"[context-insight] {message}")

    def _on_analysis(self, analysis: SessionAnalysis) -> None:
        if not isinstance(analysis, SessionAnalysis):
            return
        self._analysis = analysis
        meta = analysis.meta
        title = meta.title or "未命名会话"
        self._subtitle.setText(title[:56])
        self._summary.setText(
            f"{fmt_int(analysis.used_tokens)} / {fmt_k(analysis.budget_tokens)} tokens · "
            f"{analysis.percent}% · {fmt_int(analysis.usage.get('requests', 0))} 请求 · "
            f"{fmt_cost(analysis.cost_usd, analysis.cost_known)}"
        )
        self._stats_card.set_analysis(analysis)
        self._current_card.set_analysis(analysis)
        self._timing_card.set_analysis(analysis)
        self._composition_card.set_analysis(analysis)
        self._events_card.set_analysis(analysis)
        self._files_card.set_analysis(analysis)
        self._commands_card.set_analysis(analysis)
        self._browser.set_analysis(analysis)
        self._render_trend()
        self._render_fleet()

    # ── 趋势 ──
    def _trend_steps(self) -> List[Dict[str, Any]]:
        analysis = self._analysis
        if analysis is None:
            return []
        granularity = self._granularity.current()
        if granularity == "turn":
            out: List[Dict[str, Any]] = []
            prev = 0
            for turn in analysis.turns:
                if not turn.steps:
                    continue
                last = turn.steps[-1]
                comp = dict(last.context_composition)
                delta = turn.input_tokens - prev if prev else 0
                prev = turn.input_tokens
                out.append(
                    {
                        "ts": turn.start_ts,
                        "input": turn.input_tokens,
                        "output": turn.output_tokens,
                        "composition": comp,
                        "delta": delta,
                        "event": any(e.step_index == last.index for e in analysis.events),
                    }
                )
            return out
        return [
            {
                "ts": step.ts,
                "input": step.input_tokens,
                "output": step.output_tokens,
                "composition": dict(step.context_composition),
                "delta": step.delta_tokens,
                "event": any(e.step_index == step.index for e in analysis.events),
                "index": i,
            }
            for i, step in enumerate(analysis.steps)
        ]

    def _render_trend(self) -> None:
        steps = self._trend_steps()
        from .analyzer import CATEGORY_COLORS, CATEGORY_LABELS
        from .theme import parse_color

        keys = [
            (key, parse_color(CATEGORY_COLORS.get(key, "#888888")))
            for key in (
                "system",
                "tools",
                "user",
                "injected",
                "skill",
                "assistant",
                "reasoning",
                "tool_calls",
                "tool_results",
                "overhead",
            )
        ]
        self._trend_chart.set_data(steps, keys, self._mode.current())
        self._trend_list.set_data(steps, keys, self._mode.current(), self._granularity.current())
        self._trend_list.set_selected(self._trend_selected)
        self._apply_trend_layout()
        if self._trend_selected >= len(steps):
            self._trend_selected = -1
        self._trend_controls.set_subtitle(f"{len(steps)} 个数据点")
        if self._mode.current() == "delta":
            self._trend_legend.set_data(
                [("增长", self._palette.accent), ("回落", parse_color("#f87171"))]
            )
        else:
            totals = {}
            for step in steps:
                for key, value in (step.get("composition") or {}).items():
                    totals[key] = totals.get(key, 0) + int(value)
            legend_rows = [
                (CATEGORY_LABELS.get(key, key), parse_color(CATEGORY_COLORS.get(key, "#888888")))
                for key, _value in sorted(totals.items(), key=lambda kv: -kv[1])
                if _value > 0
            ]
            self._trend_legend.set_data(legend_rows)
        self._render_trend_summary()

    def _render_trend_summary(self) -> None:
        analysis = self._analysis
        if analysis is None or not analysis.steps:
            self._trend_summary.setText("")
            return
        idx = self._trend_selected if 0 <= self._trend_selected < len(analysis.steps) else len(analysis.steps) - 1
        if self._granularity.current() == "turn":
            turns = [t for t in analysis.turns if t.steps]
            if not turns:
                self._trend_summary.setText("")
                return
            turn = turns[min(idx, len(turns) - 1)]
            user_text = turn.user_text or "（本轮无用户文本）"
            step = turn.steps[-1]
            new_parts = []
            if step.context_composition:
                from .analyzer import CATEGORY_LABELS

                top = max(step.context_composition.items(), key=lambda kv: kv[1])
                new_parts.append(f"{CATEGORY_LABELS.get(top[0], top[0])} {fmt_k(top[1])}")
            self._trend_summary.setText(
                f"<b>User</b> {user_text[:80]}<br/>"
                f"<b>In</b> 上下文 {fmt_k(turn.input_tokens)} · {' · '.join(new_parts)}<br/>"
                f"<b>Response</b> 输出 {fmt_k(turn.output_tokens)} · {turn.tool_calls} 次工具调用"
            )
            return
        step = analysis.steps[min(idx, len(analysis.steps) - 1)]
        prev_step = analysis.steps[idx - 1] if idx > 0 else None
        new_tokens = step.input_tokens - (prev_step.input_tokens if prev_step else 0)
        self._trend_summary.setText(
            f"<b>Step</b> #{idx + 1} · {step.ts}<br/>"
            f"<b>In</b> {fmt_k(step.input_tokens)} tokens（变化 {'+' if new_tokens >= 0 else ''}{fmt_k(new_tokens)}）<br/>"
            f"<b>Response</b> 输出 {fmt_k(step.output_tokens)} · {len(step.tool_calls)} 次工具调用"
        )

    def _on_granularity(self, _key: str) -> None:
        self._trend_selected = -1
        self._render_trend()

    def _on_trend_step(self, index: int) -> None:
        self._trend_selected = index
        self._trend_list.set_selected(index)
        self._render_trend_summary()

    def _apply_trend_layout(self) -> None:
        vertical = self._layout_mode.current() == "vertical"
        self._trend_list.setVisible(vertical)
        self._trend_chart.setVisible(not vertical)

    # ── 编队 ──
    def _render_fleet(self) -> None:
        analysis = self._analysis
        if analysis is None:
            return
        meta = analysis.meta
        current = {
            "session_id": meta.session_id,
            "session_title": meta.title,
            "agent_name": meta.agent_name or "main",
            "model": analysis.models[0] if analysis.models else "",
            "model_meta": f"{len(analysis.tool_counts)} 种工具 · {fmt_k(analysis.usage.get('total', 0))} tokens",
            "usage": analysis.usage,
            "cost_usd": analysis.cost_usd,
            "cost_known": analysis.cost_known,
            "percent": analysis.percent,
            "is_streaming": bool(self._ctx.get("streaming", False)),
        }
        caps = self._ctx.get("capabilities") or {}
        summaries = cached_summaries()
        if not summaries and not self._index_requested:
            history = caps.get("session.history") if hasattr(caps, "get") else None
            if history:
                self._index_requested = True
                worker = IndexWorker(history, self)
                worker.finished_ok.connect(lambda _rows: self._render_fleet())
                worker.finished.connect(lambda: setattr(self, "_index_requested", False))
                self._index_worker = worker
                worker.start()
        team = []
        if meta.team_run_id or meta.team_name:
            for item in summaries:
                if item.get("session_id") == meta.session_id:
                    continue
                same_team = bool(meta.team_run_id) and item.get("team_run_id") == meta.team_run_id
                if not same_team and meta.team_name and not meta.team_run_id:
                    same_team = item.get("team_name") == meta.team_name
                if same_team:
                    team.append(
                        {
                            "agent_name": item.get("agent_name") or "member",
                            "team_name": item.get("team_name") or meta.team_name,
                            "session_title": item.get("title", ""),
                            "usage": item.get("usage") or {},
                            "cost_usd": item.get("cost_usd", 0),
                            "cost_known": item.get("cost_known", True),
                            "percent": item.get("percent", 0),
                            "live": False,
                        }
                    )
        subs = []
        comms_payload: Dict[str, Any] = {}
        team_read = caps.get("team.read") if hasattr(caps, "get") else None
        if team_read is not None:
            getter = team_read.get if hasattr(team_read, "get") else lambda name: getattr(team_read, name, None)
            team_name = meta.team_name or "default"
            gathered = gather_team_comms(team_read, team_name)
            live_events = gathered.get("events") or []
            run_id = meta.team_run_id or ""
            if run_id:
                if live_events:
                    append_snapshot(run_id, live_events)
                merged: Dict[str, Dict[str, Any]] = {}
                for old_event in load_snapshot(run_id):
                    merged[str(old_event.get("mail_id"))] = old_event
                for live_event in live_events:
                    merged[str(live_event.get("mail_id"))] = live_event
                events = sorted(merged.values(), key=lambda e: (float(e.get("time") or 0), str(e.get("mail_id") or "")))
            else:
                events = live_events
            lanes = build_lane_roster(
                gathered.get("members") or [],
                gathered.get("leader") or "",
                events,
                meta.agent_name or "",
            )
            comms_payload = {"lanes": lanes, "events": events}
            for method_name, status in (("get_running_tasks", "running"), ("get_pending_tasks", "pending")):
                fn = getter(method_name)
                if not callable(fn):
                    continue
                try:
                    tasks = fn() or []
                except Exception:
                    continue
                for task in tasks if isinstance(tasks, list) else []:
                    if not isinstance(task, dict):
                        continue
                    subs.append(
                        {
                            "agent_name": task.get("agent_name") or task.get("name") or "sub",
                            "description": task.get("task_description") or task.get("description") or "",
                            "status": task.get("status") or status,
                            "updated_at": task.get("updated_at") or task.get("created_at") or "",
                        }
                    )
        self._fleet.set_data(
            {
                "current": current,
                "team": team,
                "subagents": subs,
                "comms": comms_payload,
                "is_streaming": current["is_streaming"],
            }
        )

    # ── 交互 ──
    def _switch_tab(self, key: str) -> None:
        page = self._tabs.get(key)
        if page is not None:
            self._stack.setCurrentWidget(page)

    def _open_settings(self) -> None:
        caps = self._ctx.get("capabilities") or {}
        notify = caps.get("ui.notify") if hasattr(caps, "get") else None
        if callable(notify):
            try:
                notify("上下文洞察", "请到 设置 → 插件 → 上下文洞察偏好 修改", "info")
                return
            except Exception:
                pass
        self._summary.setText("请在 设置 → 插件 → 上下文洞察偏好 中修改")

    # ── 信号订阅 ──
    def _subscribe_once(self) -> None:
        if self._subscribed:
            return
        self._subscribed = True
        caps = self._ctx.get("capabilities") or {}
        subscribe = caps.get("stream.subscribe") if hasattr(caps, "get") else None
        events = {
            "messages_updated": self._on_stream_event,
            "stream_finished": self._on_stream_event,
            "session_changed": self._on_session_changed,
            "context_updated": self._on_stream_event,
        }
        if callable(subscribe):
            try:
                subscribe(events)
            except Exception as e:
                logger.debug(f"[context-insight] 能力订阅失败: {e}")

    def _on_stream_event(self, *_args) -> None:
        if not self.isVisible():
            return
        if not self._auto_refresh():
            return
        QTimer.singleShot(700, lambda: self._refresh_data(force=False))

    def _on_session_changed(self, *_args) -> None:
        try:
            if self._provider is not None:
                self._ctx = self._provider() or self._ctx
        except Exception:
            pass
        sid = self._resolve_session_id()
        if sid and sid != self._session_id:
            self._analysis = None
            QTimer.singleShot(120, lambda: self._refresh_data(force=True))

    def _auto_refresh(self) -> bool:
        return bool(get_config("auto_refresh", True))

    def shutdown(self) -> None:
        """插件卸载/窗口销毁前停掉后台线程，避免 QThread 运行中被析构。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            try:
                worker.stop()
                worker.wait(3000)
            except Exception:
                pass
        index_worker = self._index_worker
        if index_worker is not None and index_worker.isRunning():
            try:
                index_worker.stop()
                index_worker.wait(2000)
            except Exception:
                pass
