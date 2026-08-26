# -*- coding: utf-8 -*-
"""主题色映射 — 将主程序注入的 ctx 转换为卡片可用的 QColor 字典

设计约束（闭包）：
- 不导入 app.core / app.widgets 内部模块
- 文字颜色优先取主程序注入的 colors.text_primary / text_secondary
  （权威主题色，任何主题下都与主界面一致），缺失才按 is_dark 回退。
- 背景面板跟随 is_dark：暗色主题深底、亮色主题浅底。
"""

from typing import Optional

from PyQt5.QtGui import QColor


def make_palette(ctx: Optional[dict] = None) -> dict:
    """从上下文 colors 构建配色字典（含 QColor 值 + 字体信息）

    ctx 缺失/空时回退暗色默认，保证任何情况下卡片可渲染。
    """
    ctx = ctx or {}
    raw = ctx.get("colors", {}) or {}
    is_dark = bool(ctx.get("is_dark", True))

    def _qcolor(key: str, fallback_light: str, fallback_dark: str) -> QColor:
        val = raw.get(key, "")
        if val:
            return QColor(val)
        return QColor(fallback_dark if is_dark else fallback_light)

    # 文字色：优先主程序注入的主题色（权威），缺失按 is_dark 回退
    text = _qcolor("text_primary", "#1e1e1e", "#ffffff")
    text_secondary = _qcolor("text_secondary", "#505050", "#ffffff")

    accent = _qcolor("accent", "#2878dc", "#62a0ea")
    success = _qcolor("success", "#00a888", "#50e3c2")
    warning = _qcolor("accent_warm", "#f59e0b", "#ffc107")
    danger = _qcolor("danger", "#e5484d", "#ff6b6b")

    return {
        "accent": accent,
        "accent_fill": QColor(accent.red(), accent.green(), accent.blue(), 60),
        "success": success,
        "success_fill": QColor(success.red(), success.green(), success.blue(), 50),
        "warning": warning,
        "danger": danger,
        "danger_fill": QColor(danger.red(), danger.green(), danger.blue(), 50),
        "text": text,
        "text_secondary": text_secondary,
        "card_bg": _qcolor("card_bg", "#00000014", "#ffffff14"),
        "border": _qcolor("border", "#cccccc80", "#0000001e"),
        "hover_bg": _qcolor("hover_bg", "#0000000a", "#ffffff0a"),
        "is_dark": is_dark,
        "font_family": ctx.get("font_family", "Microsoft YaHei"),
        "font_size": ctx.get("font_size", 14),
    }


def rgba(c: QColor, alpha: int = -1) -> str:
    """QColor → rgba() 字符串（供 QSS 使用）"""
    a = c.alpha() if alpha < 0 else alpha
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"
