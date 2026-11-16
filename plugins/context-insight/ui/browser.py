# -*- coding: utf-8 -*-
"""Context Browser —— 任选一个请求，展开它实际由哪些消息组成。"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .analyzer import CATEGORY_COLORS, CATEGORY_LABELS, SessionAnalysis, _content_text
from .fmt import fmt_int, fmt_k, fmt_ts
from .scrollbars import scrollbar_style
from .theme import Palette
from .widgets import css, css_html


def _cat_of(comp: Dict[str, int]) -> str:
    if not comp:
        return "overhead"
    return max(comp.items(), key=lambda kv: kv[1])[0]


class ContextBrowser(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._analysis: Optional[SessionAnalysis] = None
        self._selected = -1
        self._session_id = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._splitter = QSplitter(Qt.Horizontal, self)
        self._splitter.setChildrenCollapsible(False)

        self._list = QListWidget(self._splitter)
        self._list.setObjectName("ciStepList")
        self._list.setMinimumWidth(150)
        self._list.setMaximumWidth(230)
        self._list.currentRowChanged.connect(self._on_row)

        self._detail = QTextBrowser(self._splitter)
        self._detail.setObjectName("ciStepDetail")
        self._detail.setOpenExternalLinks(False)
        self._detail.setFrameShape(QTextBrowser.NoFrame)

        self._splitter.addWidget(self._list)
        self._splitter.addWidget(self._detail)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        layout.addWidget(self._splitter, 1)
        self._apply_style()

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self._apply_style()
        self._render_list()

    def _apply_style(self) -> None:
        p = self._palette
        selected_fg = "#1f1f1f" if p.is_dark else "#ffffff"
        # hover 用文字色的低透明度，明暗主题都可见且不会是实黑/实白
        hover_bg = p.alpha(p.text_primary, 18)
        self._list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; outline: none; }}"
            f"QListWidget::item {{ color: {css(p.text_secondary)}; padding: 5px 6px; border-radius: 6px;"
            f" margin: 1px 0; }}"
            f"QListWidget::item:selected {{ background: {css(p.accent)}; color: {selected_fg}; }}"
            f"QListWidget::item:hover {{ background: {css(hover_bg)}; }}"
            + scrollbar_style(self._palette, 6)
        )
        self._detail.setStyleSheet(
            f"QTextBrowser {{ background: transparent; border: none; color: {css(p.text_primary)};"
            f" font-size: {p.fs(-1)}px; }}"
            + scrollbar_style(self._palette, 6)
        )

    def set_analysis(self, analysis: SessionAnalysis) -> None:
        same_session = analysis.meta.session_id == self._session_id
        keep = self._selected if same_session and 0 <= self._selected < len(analysis.steps) else -1
        self._session_id = analysis.meta.session_id
        self._analysis = analysis
        self._selected = keep if keep >= 0 else (len(analysis.steps) - 1 if analysis.steps else -1)
        self._render_list()

    def _render_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        analysis = self._analysis
        if analysis is None:
            self._list.blockSignals(False)
            return
        for i, step in enumerate(analysis.steps):
            delta = step.delta_tokens
            delta_text = f"  {'+' if delta >= 0 else ''}{fmt_k(delta)}" if delta else ""
            text = f"#{i + 1}  {fmt_k(step.input_tokens)}{delta_text}\n{fmt_ts(step.ts, False)} · {step.model[:18]}"
            item = QListWidgetItem(text)
            self._list.addItem(item)
        self._list.blockSignals(False)
        if analysis.steps:
            row = self._selected if 0 <= self._selected < len(analysis.steps) else len(analysis.steps) - 1
            self._list.setCurrentRow(row)
            self._render_detail(row)

    def _on_row(self, row: int) -> None:
        self._selected = row
        self._render_detail(row)

    def _render_detail(self, row: int) -> None:
        analysis = self._analysis
        if analysis is None or not analysis.steps or not (0 <= row < len(analysis.steps)):
            self._detail.setHtml(
                f"<div style='color:{css_html(self._palette.text_secondary)}; padding:12px'>选择一个请求查看组成</div>"
            )
            return
        step = analysis.steps[row]
        p = self._palette
        parts: List[str] = []
        parts.append(
            "<div style='padding:2px 0 8px 0'>"
            f"<span style='font-size:{p.fs(0)}px;font-weight:600;color:{css_html(p.text_primary)}'>Step #{row + 1}</span>"
            f"<span style='color:{css_html(p.alpha(p.text_primary, 190))}'> · {html.escape(step.ts)} · {html.escape(step.model)}</span><br/>"
            f"<span style='color:{css_html(p.text_primary)}'>上下文 ≈ {fmt_int(step.input_tokens)} tokens</span>"
            f"<span style='color:{css_html(p.alpha(p.text_primary, 190))}'> · 输出 {fmt_int(step.output_tokens)}"
            f" · {'API 精确值' if step.has_usage else '本地估算'}</span>"
            "</div>"
        )
        # 分类汇总
        comp = step.context_composition
        total = sum(comp.values()) or 1
        chips = []
        for key, value in sorted(comp.items(), key=lambda kv: -kv[1]):
            if value <= 0:
                continue
            color = CATEGORY_COLORS.get(key, "#888888")
            pct = value / total * 100
            chips.append(
                f"<span style='background:{color}33;color:{css_html(p.text_primary)};border:1px solid {color}88;"
                f"border-radius:7px;padding:1px 6px;margin-right:4px'>{html.escape(CATEGORY_LABELS.get(key, key))}"
                f" {pct:.0f}%</span>"
            )
        parts.append("<div style='line-height:22px;padding-bottom:10px'>" + " ".join(chips) + "</div>")

        # 消息列表（system + 0..step.index）
        rows: List[Dict[str, Any]] = []
        if analysis.system_tokens:
            rows.append(
                {
                    "idx": -1,
                    "role": "system",
                    "category": "system",
                    "tokens": analysis.system_tokens,
                    "text": analysis.meta.system_prompt,
                    "ts": "",
                }
            )
        for i in range(0, min(step.index + 1, len(analysis.messages))):
            msg = analysis.messages[i]
            cats = analysis.msg_categories[i] if i < len(analysis.msg_categories) else {}
            token_count = analysis.msg_tokens[i] if i < len(analysis.msg_tokens) else 0
            text = _content_text(msg.get("content"))
            if not text and msg.get("tool_calls"):
                text = " → ".join(
                    str((c.get("function") or {}).get("name") or "") for c in msg.get("tool_calls") or []
                )
            rows.append(
                {
                    "idx": i,
                    "role": str(msg.get("role") or ""),
                    "category": _cat_of(cats),
                    "tokens": token_count,
                    "text": text,
                    "ts": str(msg.get("timestamp") or ""),
                }
            )
        # 消息多时折叠中段，保留头部 system 与尾部
        display = rows
        folded = 0
        if len(rows) > 160:
            display = rows[:20] + rows[-130:]
            folded = len(rows) - len(display)
        for n, item in enumerate(display):
            if folded and n == 20:
                parts.append(
                    f"<div style='color:{css_html(p.text_secondary)};padding:6px 0'>… 省略 {folded} 条较早消息 …</div>"
                )
            color = CATEGORY_COLORS.get(item["category"], "#888888")
            text = (item["text"] or "").replace("\n", " ")
            preview = html.escape(text[:180]) + ("…" if len(text) > 180 else "")
            role = html.escape(item["role"])
            cat = html.escape(CATEGORY_LABELS.get(item["category"], item["category"]))
            ts = html.escape(fmt_ts(item["ts"], False)) if item["ts"] else ""
            parts.append(
                "<div style='border-left:3px solid %s;background:%s;margin:3px 0;padding:5px 8px;border-radius:4px'>"
                "<div style='color:%s;font-size:%spx'>%s · %s · %s tokens %s</div>"
                "<div style='color:%s;font-size:%spx'>%s</div></div>"
                % (
                    color,
                    css_html(p.alpha(p.border, 22)),
                    css_html(p.alpha(p.text_primary, 195)),
                    p.fs(-3),
                    role,
                    cat,
                    fmt_int(item["tokens"]),
                    ts,
                    css_html(p.text_primary),
                    p.fs(-1),
                    preview,
                )
            )
        self._detail.setHtml("".join(parts))
        self._detail.verticalScrollBar().setValue(0)
