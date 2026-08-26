# -*- coding: utf-8 -*-
"""workbuddy 产物面板主题样式（参考 browser/ui/theme.py 的轻量实现，不跨插件耦合）

从 registry 注入的 UI 上下文（ctx）派生主题色与 QSS，确保深浅主题跟随 DriFox，
并正确使用 ctx 中的 font_family / font_size / is_dark / colors 等字段。
"""
from PyQt5.QtCore import Qt  # noqa: F401


def _ctx_colors(ctx: dict) -> dict:
    return (ctx.get("colors", {}) or {}) if isinstance(ctx, dict) else {}


def theme_colors(ctx: dict = None) -> dict:
    """从 UI 上下文解析主题色（真实 token + 深浅 fallback）。"""
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
        or ("rgba(128,128,128,0.25)" if is_dark else "rgba(0,0,0,0.10)"),
        "accent": colors.get("accent") or ("#66c6ff" if is_dark else "#0078d4"),
        "hover": colors.get("hover_bg")
        or ("rgba(255,255,255,0.10)" if is_dark else "rgba(0,0,0,0.06)"),
        "selected": colors.get("selected_bg")
        or ("rgba(102,198,255,0.32)" if is_dark else "rgba(0,120,215,0.18)"),
        "code_bg": "#111722" if is_dark else "#f4f6f9",
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
    """面板整体：大圆角、无边框感（弱边框）、统一背景。

    注意：QSS 类型选择器不认 Python 类名（ArtifactPanelCard），必须用
    objectName 选择器（_build_ui 已 setObjectName("wbRoot")），否则整条
    规则被 QSS 解析器静默丢弃（表现为背景失效 + 白底白字）。
    """
    return (
        f"QFrame#wbRoot {{ background: {c['card']};"
        f" border: 1px solid {c['border']}; border-radius: 12px; }}"
        f"QFrame#wbRoot QLabel {{ background: transparent; border: none; }}"
    )


def icon_btn_style(c: dict, ff="", fs=0) -> str:
    """头部图标按钮：无边框透明底，hover 浮现圆角底色。"""
    return (
        "QPushButton { background: transparent; border: none; border-radius: 6px;"
        f" padding: 5px; color: {c['secondary']};"
        + (f" font-family: '{ff}'; font-size: {max(fs - 2, 11)}px;" if ff else "")
        + " }"
        f"QPushButton:hover {{ background: {c['hover']}; color: {c['text']}; }}"
        f"QPushButton:pressed {{ background: {c['selected']}; }}"
    )


def tab_style(c: dict, ff="", fs=0) -> str:
    """WorkBuddy 式 QTabWidget：pill 选中态 + accent 下划线 + 内容区融合。"""
    font = f"font-family: '{ff}'; font-size: {max(fs - 1, 12)}px;" if ff else ""
    return (
        # 内容 pane 与 tab 条无缝衔接
        f"QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 10px;"
        f" background: {c['raised']}; top: -1px; }}"
        f"QTabWidget::tab-bar {{ left: 8px; }}"
        f"QTabBar {{ background: transparent; }}"
        f"QTabBar::tab {{ background: transparent; color: {c['secondary']};"
        f" padding: 5px 14px 5px 10px; margin: 3px 2px 3px 0;"
        f" border-radius: 14px; border: 1px solid transparent; {font} }}"
        f"QTabBar::tab:hover {{ background: {c['hover']}; color: {c['text']}; }}"
        f"QTabBar::tab:selected {{ background: {c['selected']};"
        f" border-color: {c['accent']}; color: {c['text']}; font-weight: 600; }}"
        # 不要写 QTabBar::close-button 规则——QSS 一旦出现该选择器，Qt 切换到
        # stylesheet 渲染模式，代码里 setIcon 的关闭图标会被忽略（×不可见）。
    )


def viewer_style(c: dict, ff="", fs=0) -> str:
    """内容 viewer（QTextBrowser）：融入 pane 背景、无独立边框。"""
    font = f"font-family: '{ff}'; font-size: {fs}px;" if ff else ""
    return (
        f"QTextBrowser {{ background: transparent; border: none;"
        f" color: {c['text']}; padding: 16px 20px; {font} }}"
    )


def empty_state_style(c: dict, ff="") -> str:
    """空态容器样式。"""
    return (
        "QWidget#wbEmpty { background: transparent; }"
        + (f"font-family: '{ff}';" if ff else "")
    )
