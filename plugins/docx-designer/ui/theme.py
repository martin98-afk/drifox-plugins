# -*- coding: utf-8 -*-
"""主题色派生（精简自 browser 插件同款实现，键名保持一致）。"""


def _ctx(owner=None) -> dict:
    provider = getattr(owner, "_context_provider", None)
    if provider is None:
        return {}
    try:
        return provider() or {}
    except Exception:
        return {}


def theme_colors(owner=None) -> dict:
    try:
        from qfluentwidgets import isDarkTheme

        _is_dark = isDarkTheme()
    except Exception:
        _is_dark = True

    ctx = _ctx(owner)
    ctx_is_dark = ctx.get("is_dark")
    is_dark = ctx_is_dark if isinstance(ctx_is_dark, bool) else _is_dark
    colors = ctx.get("colors", {}) or {} if isinstance(ctx, dict) else {}
    ff = ctx.get("font_family") or "Microsoft YaHei"
    fs = ctx.get("font_size") or 14
    try:
        fs = int(fs)
    except (TypeError, ValueError):
        fs = 14
    return {
        "is_dark": is_dark,
        "ff": ff,
        "fs": fs,
        "text": colors.get("text_primary")
        or ("rgba(255,255,255,0.90)" if is_dark else "rgba(0,0,0,0.85)"),
        "secondary": colors.get("text_secondary")
        or ("rgba(255,255,255,0.58)" if is_dark else "rgba(0,0,0,0.55)"),
        "muted": colors.get("text_muted") or ("#8b98ad" if is_dark else "#666666"),
        "surface": colors.get("card_bg_solid") or ("#161e2d" if is_dark else "#ffffff"),
        "raised": colors.get("content_bg") or ("#1d2533" if is_dark else "#f5f5f5"),
        "border": colors.get("border")
        or ("rgba(128,128,128,0.25)" if is_dark else "rgba(0,0,0,0.18)"),
        "accent": colors.get("accent") or ("#66c6ff" if is_dark else "#0078d4"),
        "hover": colors.get("hover_bg")
        or ("rgba(255,255,255,0.10)" if is_dark else "rgba(0,0,0,0.08)"),
    }
