# -*- coding: utf-8 -*-
"""workbuddy 产物面板主题样式（参考 browser/ui/theme.py 的轻量实现，不跨插件耦合）

从 registry 注入的 UI 上下文（ctx）派生主题色与 QSS，确保深浅主题跟随 DriFox，
并正确使用 ctx 中的 font_family / font_size / is_dark / colors 等字段。
"""
from PyQt5.QtCore import Qt  # noqa: F401


def _ctx_colors(ctx: dict) -> dict:
    return (ctx.get("colors", {}) or {}) if isinstance(ctx, dict) else {}


def theme_colors(ctx: dict = None) -> dict:
    """从 UI 上下文解析主题色（真实 token + 深浅 fallback）。

    Args:
        ctx: registry 注入的上下文 dict，含 colors / is_dark / font_family /
             font_size 等字段；为空时用 qfluentwidgets 当前主题兜底。
    """
    try:
        from qfluentwidgets import isDarkTheme

        _is_dark = isDarkTheme()
    except Exception:
        _is_dark = True

    ctx = ctx if isinstance(ctx, dict) else {}
    ctx_is_dark = ctx.get("is_dark")
    is_dark = ctx_is_dark if isinstance(ctx_is_dark, bool) else _is_dark
    colors = _ctx_colors(ctx)
    ff = ctx.get("font_family") or "Microsoft YaHei"
    try:
        fs = int(ctx.get("font_size") or 14)
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
        "card": colors.get("card_bg")
        or ("rgba(22,30,45,0.96)" if is_dark else "#ffffff"),
        "raised": colors.get("content_bg") or ("#1d2533" if is_dark else "#f5f5f5"),
        "border": colors.get("border")
        or ("rgba(128,128,128,0.25)" if is_dark else "rgba(0,0,0,0.12)"),
        "accent": colors.get("accent") or ("#66c6ff" if is_dark else "#0078d4"),
        "hover": colors.get("hover_bg")
        or ("rgba(255,255,255,0.10)" if is_dark else "rgba(0,0,0,0.08)"),
        "selected": colors.get("selected_bg")
        or ("rgba(102,198,255,0.32)" if is_dark else "rgba(0,120,215,0.22)"),
    }


def make_style(color=None, ff="", fs=0, extra="") -> str:
    """通用 QSS 组合器：color/font-family/font-size 按需拼接。"""
    parts = []
    if color:
        parts.append(f"color: {color};")
    if ff:
        parts.append(f"font-family: '{ff}';")
    if fs:
        parts.append(f"font-size: {fs}px;")
    if extra:
        parts.append(extra)
    return " ".join(parts)


def panel_style(c: dict) -> str:
    """卡片整体背景 / 圆角样式。"""
    return (
        f"QFrame {{ background: {c['card']}; border: 1px solid {c['border']};"
        f" border-radius: 10px; }}"
    )


def list_style(c: dict, ff="", fs=0) -> str:
    """左侧 artifact 列表样式（圆角 + hover/selected 主题态）。"""
    font = f"font-family: '{ff}'; font-size: {fs}px;" if ff else ""
    return (
        f"QListWidget {{ background: {c['raised']}; border: 1px solid {c['border']};"
        f" border-radius: 8px; color: {c['text']}; {font} }}"
        f"QListWidget::item {{ padding: 8px 10px; border-radius: 4px; {font} }}"
        f"QListWidget::item:hover {{ background: {c['hover']}; }}"
        f"QListWidget::item:selected {{ background: {c['selected']}; color: {c['text']}; }}"
    )


def viewer_style(c: dict, ff="", fs=0) -> str:
    """右侧 viewer（QTextBrowser）样式。"""
    font = f"font-family: '{ff}'; font-size: {fs}px;" if ff else ""
    return (
        f"QTextBrowser {{ background: {c['raised']}; border: 1px solid {c['border']};"
        f" border-radius: 8px; color: {c['text']}; padding: 10px; {font} }}"
    )


def tab_style(c: dict, ff="", fs=0) -> str:
    """WorkBuddy 式 QTabWidget 样式：文档模式 tab 条 + 圆角内容区。"""
    font = f"font-family: '{ff}'; font-size: {fs - 1}px;" if ff else ""
    return (
        f"QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 8px;"
        f" background: {c['raised']}; top: -1px; }}"
        f"QTabBar {{ background: transparent; }}"
        f"QTabBar::tab {{ background: transparent; color: {c['secondary']};"
        f" padding: 6px 12px; margin-right: 2px; border: 1px solid transparent;"
        f" border-top-left-radius: 6px; border-top-right-radius: 6px; {font} }}"
        f"QTabBar::tab:hover {{ background: {c['hover']}; color: {c['text']}; }}"
        f"QTabBar::tab:selected {{ background: {c['raised']};"
        f" border-color: {c['border']}; color: {c['text']}; font-weight: 600; }}"
        f"QTabBar::close-button {{ subcontrol-position: right;"
        f" background: transparent; border-radius: 3px; }}"
    )


def btn_style(c: dict, ff="", fs=0) -> str:
    """圆角主题按钮样式（替代原生灰按钮）。"""
    font = f"font-family: '{ff}'; font-size: {fs}px;" if ff else ""
    return (
        f"QPushButton {{ background: {c['raised']}; border: 1px solid {c['border']};"
        f" border-radius: 6px; color: {c['text']}; padding: 5px 14px; {font} }}"
        f"QPushButton:hover {{ background: {c['hover']}; }}"
        f"QPushButton:pressed {{ background: {c['selected']}; }}"
        f"QPushButton:disabled {{ color: {c['muted']}; }}"
    )
