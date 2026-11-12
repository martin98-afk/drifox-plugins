# -*- coding: utf-8 -*-
"""编队（Fleet）—— 当前 Agent、团队成员与子智能体卡片。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .fmt import fmt_cost, fmt_k, fmt_ts
from .theme import Palette
from .widgets import clear_layout, EmptyState, Pill, SectionCard, css, make_label


class _AgentCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ciAgentCard")
        self.setMinimumHeight(112)
        self._palette = Palette()
        self._title = QLabel(self)
        self._role = QLabel(self)
        self._meta = QLabel(self)
        self._meta.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self._title, 1)
        head.addWidget(self._role)
        layout.addLayout(head)
        layout.addWidget(self._meta, 1)
        self._apply_style()

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self._apply_style()

    def _apply_style(self) -> None:
        p = self._palette
        self.setStyleSheet(
            f"#ciAgentCard {{ background: {css(p.card_bg)}; border: 1px solid {css(p.alpha(p.border, 150))};"
            f" border-radius: 10px; }}"
            f"#ciAgentCard QLabel {{ color: {css(p.text_primary)}; background: transparent; }}"
        )
        self._title.setStyleSheet(f"color: {css(p.text_primary)}; font-size: {p.fs(-1)}px; font-weight: 600; background: transparent;")
        self._role.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-3)}px; background: transparent;")
        self._meta.setStyleSheet(f"color: {css(p.text_secondary)}; font-size: {p.fs(-3)}px; background: transparent;")

    def set_data(self, name: str, role: str, meta: str, role_color=None) -> None:
        self._title.setText(name or "（未命名）")
        self._role.setText(role)
        if role_color is not None:
            self._role.setStyleSheet(
                f"color: {css(role_color)}; font-size: {self._palette.fs(-3)}px; background: {css(role_color)}20;"
                f" border-radius: 6px; padding: 1px 6px;"
            )
        self._meta.setText(meta)


class FleetWidget(QWidget):
    """编队视图：当前 Agent / 团队成员 / 子智能体。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = Palette()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._current_card: Optional[SectionCard] = None
        self._team_card: Optional[SectionCard] = None
        self._sub_card: Optional[SectionCard] = None
        self._data: Dict[str, Any] = {}

    def set_palette_obj(self, palette: Palette) -> None:
        self._palette = palette
        self._render()

    def set_data(self, data: Dict[str, Any]) -> None:
        self._data = data or {}
        self._render()

    def _clear(self) -> None:
        clear_layout(self._layout)

    def _render(self) -> None:
        self._clear()
        p = self._palette
        current = self._data.get("current") or {}
        team = self._data.get("team") or []
        subs = self._data.get("subagents") or []
        is_streaming = bool(self._data.get("is_streaming"))

        # ── 当前 Agent ──
        card = SectionCard("当前 Agent", self)
        card.set_palette_obj(p)
        card.set_subtitle("实时")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.addWidget(
            self._agent_card(
                current.get("agent_name") or "main",
                "生成中" if is_streaming else ("在线" if current.get("session_id") else "空闲"),
                current,
                role_color=p.accent if is_streaming else None,
            ),
            0,
            0,
        )
        grid.addWidget(
            self._agent_card(
                current.get("model") or "未知模型",
                "模型",
                {
                    "agent_name": "",
                    "session_title": current.get("session_title", ""),
                    "meta": current.get("model_meta", ""),
                },
            ),
            0,
            1,
        )
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        card.add_layout(grid)
        self._layout.addWidget(card)
        self._current_card = card

        # ── 团队成员 ──
        team_card = SectionCard("团队成员", self)
        team_card.set_palette_obj(p)
        team_card.set_subtitle(f"{len(team)} 个" if team else "")
        if team:
            grid2 = QGridLayout()
            grid2.setContentsMargins(0, 0, 0, 0)
            grid2.setHorizontalSpacing(10)
            grid2.setVerticalSpacing(10)
            for i, member in enumerate(team[:8]):
                grid2.addWidget(
                    self._agent_card(
                        member.get("agent_name") or "member",
                        member.get("team_name") or "成员",
                        member,
                        role_color=p.alpha(p.accent, 220) if member.get("live") else None,
                    ),
                    i // 2,
                    i % 2,
                )
            grid2.setColumnStretch(0, 1)
            grid2.setColumnStretch(1, 1)
            team_card.add_layout(grid2)
        else:
            team_card.add_widget(EmptyState("当前会话不在团队中", self))
        self._layout.addWidget(team_card)
        self._team_card = team_card

        # ── 子智能体 ──
        sub_card = SectionCard("子智能体", self)
        sub_card.set_palette_obj(p)
        sub_card.set_subtitle(f"{len(subs)} 个" if subs else "")
        if subs:
            for sub in subs[:12]:
                row = QFrame(self)
                row.setObjectName("ciSubRow")
                row.setStyleSheet(
                    f"#ciSubRow {{ background: {css(p.alpha(p.border, 30))}; border-radius: 7px; }}"
                )
                layout = QHBoxLayout(row)
                layout.setContentsMargins(9, 7, 9, 7)
                layout.setSpacing(8)
                name = make_label(sub.get("agent_name") or "sub", p, 0, True)
                status = Pill(sub.get("status") or "unknown", row)
                status.set_palette_obj(p)
                status.set_color(p.accent if sub.get("status") in ("finished", "success") else p.text_secondary)
                desc = make_label((sub.get("description") or "")[:90], p, -2, secondary=True)
                desc.setWordWrap(False)
                layout.addWidget(name)
                layout.addWidget(status)
                layout.addWidget(desc, 1)
                count = make_label(fmt_ts(sub.get("updated_at") or sub.get("created_at")), p, -2, secondary=True)
                layout.addWidget(count)
                sub_card.add_widget(row)
        else:
            sub_card.add_widget(EmptyState("当前会话没有子智能体任务", self))
        self._layout.addWidget(sub_card)
        self._sub_card = sub_card
        self._layout.addStretch(1)

    def _agent_card(self, name: str, role: str, info: Dict[str, Any], role_color=None) -> QFrame:
        card = _AgentCard(self)
        card.set_palette_obj(self._palette)
        bits: List[str] = []
        if info.get("session_title"):
            bits.append(str(info.get("session_title"))[:48])
        if info.get("usage"):
            usage = info.get("usage") or {}
            bits.append(f"{fmt_k(usage.get('total', 0))} tokens")
        if info.get("cost_usd") is not None:
            bits.append(fmt_cost(info.get("cost_usd"), bool(info.get("cost_known", True))))
        if info.get("meta"):
            bits.append(str(info.get("meta")))
        if info.get("percent") is not None:
            bits.append(f"上下文 {info.get('percent')}%")
        card.set_data(name, role, " · ".join(b for b in bits if b), role_color)
        return card
