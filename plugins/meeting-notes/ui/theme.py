# -*- coding: utf-8 -*-
"""主题适配：把宿主 ctx（colors/font_family/font_size/is_dark）转成可直接拼 QSS 的值。

取值优先级：ctx["colors"] 的主题 token > 深浅色兜底色。所有 key 名与主题 yaml
的 colors 段一致（text_primary / text_secondary / text_muted / border / accent /
card_bg / card_bg_solid / hover_bg / selected_bg / syntax_error / syntax_success）。

为什么不用 app.utils.design_tokens.Colors：那是进程级单例，主题切换后需要
手动 refresh，且它不反映主题插件自定义的 token；ctx 是宿主按当前主题实时给的。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

_FALLBACK_DARK: Dict[str, str] = {
    "text_primary": "#f2f4f8",
    "text_secondary": "rgba(242, 244, 248, 0.66)",
    "text_muted": "rgba(242, 244, 248, 0.42)",
    "border": "rgba(255, 255, 255, 0.12)",
    "accent": "#4c8dff",
    "card_bg": "rgba(255, 255, 255, 0.05)",
    "card_bg_solid": "rgba(30, 32, 38, 0.92)",
    "hover_bg": "rgba(255, 255, 255, 0.07)",
    "selected_bg": "rgba(76, 141, 255, 0.16)",
    "syntax_error": "#f87171",
    "syntax_success": "#4ade80",
    "accent_warm": "#fbbf24",
}

_FALLBACK_LIGHT: Dict[str, str] = {
    "text_primary": "#141821",
    "text_secondary": "rgba(20, 24, 33, 0.62)",
    "text_muted": "rgba(20, 24, 33, 0.40)",
    "border": "rgba(0, 0, 0, 0.10)",
    "accent": "#2563eb",
    "card_bg": "rgba(0, 0, 0, 0.03)",
    "card_bg_solid": "rgba(255, 255, 255, 0.94)",
    "hover_bg": "rgba(0, 0, 0, 0.05)",
    "selected_bg": "rgba(37, 99, 235, 0.12)",
    "syntax_error": "#dc2626",
    "syntax_success": "#16a34a",
    "accent_warm": "#d97706",
}

# 说话人配色：与主题无关的固定色板（深浅色都够对比度），按编号取模分配
SPEAKER_COLORS = (
    "#3b82f6",
    "#10b981",
    "#f59e0b",
    "#8b5cf6",
    "#ec4899",
    "#06b6d4",
    "#ef4444",
    "#84cc16",
)

RECORD_RED = "#e11d48"


class Theme:
    """一次 ctx 快照。主题变化时由卡片重新构造。"""

    def __init__(self, ctx: Optional[Dict[str, Any]] = None) -> None:
        ctx = ctx or {}
        colors = ctx.get("colors") or {}
        dark = ctx.get("is_dark", True)
        fb = _FALLBACK_DARK if dark else _FALLBACK_LIGHT

        def pick(key: str) -> str:
            val = colors.get(key)
            return str(val) if val else fb[key]

        self.is_dark = bool(dark)
        self.text_primary = pick("text_primary")
        self.text_secondary = pick("text_secondary")
        self.text_muted = pick("text_muted")
        self.border = pick("border")
        self.accent = pick("accent")
        self.card_bg = pick("card_bg")
        self.card_bg_solid = pick("card_bg_solid")
        self.hover_bg = pick("hover_bg")
        self.selected_bg = pick("selected_bg")
        self.error = pick("syntax_error")
        self.success = pick("syntax_success")
        self.warm = pick("accent_warm")

        self.font_family = str(ctx.get("font_family") or "Microsoft YaHei")
        try:
            self.font_size = int(ctx.get("font_size") or 14)
        except (TypeError, ValueError):
            self.font_size = 14

    # ── QSS 片段 ──

    def font(self, delta: int = 0, weight: Optional[int] = None) -> str:
        size = max(9, self.font_size + delta)
        css = f"font-family: '{self.font_family}'; font-size: {size}px;"
        if weight:
            css += f" font-weight: {weight};"
        return css

    def fg(self, color: str) -> str:
        return f"color: {color};"

    def speaker_color(self, speaker: str) -> str:
        """按说话人编号稳定取色（同一编号永远同色）。"""
        if not speaker:
            return self.text_muted
        try:
            idx = int("".join(ch for ch in speaker if ch.isdigit()) or "0")
        except ValueError:
            idx = sum(ord(c) for c in speaker)
        return SPEAKER_COLORS[idx % len(SPEAKER_COLORS)]

    def dim(self, color: str, alpha: float = 0.16) -> str:
        """把 #rrggbb 转成带透明度的 rgba；非 hex 原样返回。"""
        c = color.strip()
        if not c.startswith("#") or len(c) not in (4, 7):
            return color
        if len(c) == 4:
            c = "#" + "".join(ch * 2 for ch in c[1:])
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"

    def with_alpha(self, color: str, alpha: float) -> str:
        """同 dim，但保留无透明度入参的可读性（hex → rgba；rgba → 替换 alpha）。"""
        c = color.strip()
        if c.startswith("rgba("):
            inner = c[c.index("(") + 1 : c.rindex(")")]
            parts = [p.strip() for p in inner.split(",")]
            if len(parts) == 4:
                return f"rgba({parts[0]}, {parts[1]}, {parts[2]}, {alpha})"
            return c
        if c.startswith("rgb("):
            inner = c[c.index("(") + 1 : c.rindex(")")]
            return f"rgba({inner}, {alpha})"
        return self.dim(c, alpha)
