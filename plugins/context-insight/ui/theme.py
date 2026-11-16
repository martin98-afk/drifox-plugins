# -*- coding: utf-8 -*-
"""主题适配 —— 把宿主 token / ctx colors 解析成 QColor，提供自绘控件色板。"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from PyQt5.QtGui import QColor


def parse_color(value: Any, fallback: str = "#888888") -> QColor:
    """解析 #hex / rgb() / rgba() / 颜色名（QColor 不认 CSS 函数）。

    fallback 也可能就是 rgba() 串（如 text_secondary 的默认值），因此不能
    直接把 fallback 丢给 QColor —— 必须和 value 走同一条解析路径。
    """
    for candidate in (value, fallback):
        text = str(candidate or "").strip()
        if not text:
            continue
        if text.startswith("#"):
            color = QColor(text)
            if color.isValid():
                return color
        m = re.match(
            r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)",
            text,
        )
        if m:
            r, g, b = (int(float(m.group(i))) for i in (1, 2, 3))
            alpha_raw = m.group(4)
            alpha = 255
            if alpha_raw is not None:
                a = float(alpha_raw)
                alpha = int(round(a * 255)) if a <= 1.0 else int(a)
            return QColor(
                max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)),
                max(0, min(255, alpha)),
            )
        color = QColor(text)
        if color.isValid():
            return color
    return QColor("#888888")


def _is_dark() -> bool:
    try:
        from qfluentwidgets import isDarkTheme

        return bool(isDarkTheme())
    except Exception:
        return True


class Palette:
    """一次刷新得到的颜色集合（避免 paint 里反复读主题）。"""

    def __init__(self, ctx: Optional[Dict[str, Any]] = None):
        ctx = ctx or {}
        colors = ctx.get("colors") or {}
        self.is_dark = bool(ctx.get("is_dark", _is_dark()))
        self.text_primary = parse_color(colors.get("text_primary"), "#ffffff" if self.is_dark else "#1f1f1f")
        self.text_secondary = parse_color(
            colors.get("text_secondary"), "rgba(255,255,255,0.55)" if self.is_dark else "rgba(0,0,0,0.5)"
        )
        self.border = parse_color(colors.get("border"), "#3d3d3d" if self.is_dark else "#e2e2e2")
        self.accent = parse_color(
            colors.get("accent") or colors.get("text_accent"), "#62a0ea" if self.is_dark else "#2878dc"
        )
        card_bg_raw = colors.get("card_bg") or colors.get("card_bg_solid")
        if isinstance(card_bg_raw, str) and "{alpha}" in card_bg_raw:
            card_bg_raw = card_bg_raw.format(alpha=230)
        self.card_bg = parse_color(
            card_bg_raw,
            "rgba(33,33,38,235)" if self.is_dark else "rgba(255,255,255,240)",
        )
        self.content_bg = parse_color(
            colors.get("content_bg"), "#2a2a2e" if self.is_dark else "#f5f5f7"
        )
        self.hover_bg = self.alpha(self.text_primary, 18)
        self.track = QColor(self.border)
        self.track.setAlpha(90 if self.is_dark else 50)
        self.font_family = str(ctx.get("font_family") or "") or ""
        try:
            self.font_size = int(ctx.get("font_size") or 13)
        except (TypeError, ValueError):
            self.font_size = 13

    def fs(self, delta: int = 0, minimum: int = 10) -> int:
        """按宿主 ctx.font_size 派生字号（delta 负数表示小一号）。"""
        try:
            base = int(self.font_size)
        except (TypeError, ValueError):
            base = 13
        return max(int(minimum), base + int(delta))

    def alpha(self, color: QColor, alpha: int) -> QColor:
        out = QColor(color)
        out.setAlpha(max(0, min(255, alpha)))
        return out

    def text_muted(self, alpha: int = 150) -> QColor:
        return self.alpha(self.text_secondary, alpha)


def apply_tooltip_palette(palette: "Palette") -> None:
    """原生 QToolTip 的兜底配色（自绘图表提示框已替代主路径）。"""
    try:
        from PyQt5.QtGui import QPalette
        from PyQt5.QtWidgets import QToolTip

        pal = QToolTip.palette()
        pal.setColor(QPalette.ToolTipBase, palette.card_bg)
        pal.setColor(QPalette.ToolTipText, palette.text_primary)
        QToolTip.setPalette(pal)
    except Exception:
        pass
