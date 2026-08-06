# -*- coding: utf-8 -*-
"""浏览器插件主题核心样式模块。

提供三块能力：
1. theme_colors(owner) —— 统一派生主题色（真实 token + 深浅两套 fallback）；
2. QSS 组合器（make_style / font_css / badge_style / accent_btn_style /
   ghost_btn_style / list_item_style）—— 供各面板零散控件组合样式；
3. 组合样式（scrollbar_style / dialog_style）—— 对齐主程序 CardStyles 规格。
"""


def _adjust_color(hex_color: str, amount: int) -> str:
    """简单地调亮/调暗一个 hex 颜色（复制自 ip-switcher）"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return hex_color
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = max(0, min(255, r + amount))
        g = max(0, min(255, g + amount))
        b = max(0, min(255, b + amount))
        return f"#{r:02x}{g:02x}{b:02x}"
    except ValueError:
        return hex_color


def _ctx(owner=None) -> dict:
    """从 owner 拉取最新 UI 上下文（无则空 dict）。"""
    provider = getattr(owner, "_context_provider", None)
    if provider is None:
        return {}
    try:
        return provider() or {}
    except Exception:
        return {}


def _ctx_colors(ctx: dict) -> dict:
    return (ctx.get("colors", {}) or {}) if isinstance(ctx, dict) else {}


def theme_colors(owner=None) -> dict:
    """解析主题色字典：键名刻意保留（surface/card/raised/hover 等），值全部来自真实 token。

    键名向后兼容（含 is_dark/text/secondary/border/surface/raised/hover），
    新增 muted/card/accent/selected/input_border/focus_border/tag_purple/ff/fs。
    """
    try:
        from qfluentwidgets import isDarkTheme

        _is_dark = isDarkTheme()
    except Exception:
        _is_dark = True

    ctx = _ctx(owner)
    ctx_is_dark = ctx.get("is_dark")
    is_dark = ctx_is_dark if isinstance(ctx_is_dark, bool) else _is_dark
    colors = _ctx_colors(ctx)
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
        "card": colors.get("card_bg")
        or ("rgba(22,30,45,250)" if is_dark else "#ffffff"),
        "raised": colors.get("content_bg") or ("#1d2533" if is_dark else "#f5f5f5"),
        "border": colors.get("border")
        or ("rgba(128,128,128,0.25)" if is_dark else "rgba(0,0,0,0.18)"),
        "accent": colors.get("accent") or ("#66c6ff" if is_dark else "#0078d4"),
        "hover": colors.get("hover_bg")
        or ("rgba(255,255,255,0.10)" if is_dark else "rgba(0,0,0,0.08)"),
        "selected": colors.get("selected_bg")
        or ("rgba(102,198,255,0.32)" if is_dark else "rgba(0,120,215,0.25)"),
        "input_border": colors.get("input_border") or "rgba(128,128,128,0.3)",
        "focus_border": colors.get("input_focus_border")
        or ("#C9A85C" if is_dark else "#0078d4"),
        "tag_purple": colors.get("tag_purple") or "#b388ff",
    }


# ══════════════════════════════════════════════════════════════════
# QSS 组合器
# ══════════════════════════════════════════════════════════════════


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


def font_css(ff, size) -> str:
    """字体声明：font-family:'{ff}'; font-size:{size}px;"""
    return f"font-family: '{ff}'; font-size: {size}px;"


def _hex_to_rgba(color: str, alpha: float) -> str:
    """把 6 位 hex 转成 rgba 半透明写法。

    Qt 5.15 的 QSS 不认 #RRGGBBAA 8 位后缀（按 #AARRGGBB 解析 → 颜色错位），
    半透明一律显式拼 rgba(r,g,b,0.xx)。非 6 位 hex（如已是 rgba）原样返回。
    """
    h = color.lstrip("#")
    if len(h) == 6:
        try:
            r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
            return f"rgba({r},{g},{b},{alpha})"
        except ValueError:
            pass
    return color


def badge_style(color, ff, fs=None) -> str:
    """状态徽章：color 纯色文字 + 13% 半透明底 + 33% 半透明边框 + 圆角(高度一半)。

    半透明用 rgba(r,g,b,0.xx) 显式写法（Qt 5.15 QSS 不认 #RRGGBBAA 8 位后缀）。
    """
    fs = max(10, (fs or 14) - 2)
    return (
        f"color: {color}; background: {_hex_to_rgba(color, 0.13)};"
        f" border: 1px solid {_hex_to_rgba(color, 0.33)};"
        f" border-radius: 11px; padding: 0 10px; {font_css(ff, fs)}"
    )


def accent_btn_style(accent, ff, fs=None) -> str:
    """强调按钮：accent→accent-20 对角线渐变 + 白字 + 6px 圆角 + hover 提亮（抄 ip-switcher）。"""
    fs = max(10, (fs or 14) - 2)
    return (
        f"QPushButton {{ background: qlineargradient("
        f"x1:0, y1:0, x2:1, y2:1, stop:0 {accent}, stop:1 {_adjust_color(accent, -20)}"
        f"); color: white; border: none; border-radius: 6px;"
        f" {font_css(ff, fs)} font-weight: 600; padding: 0 10px; }}"
        "QPushButton:hover { background: qlineargradient("
        f"x1:0, y1:0, x2:1, y2:1, stop:0 {_adjust_color(accent, 10)}, stop:1 {accent}"
        "); }"
        "QPushButton:disabled { background: rgba(128,128,128,0.3); color: rgba(255,255,255,0.5); }"
    )


def ghost_btn_style(ff, fs, border, text, hover_bg) -> str:
    """幽灵按钮：透明底 + border + 文本色 + hover_bg。"""
    fs = max(10, (fs or 14) - 2)
    return (
        f"QPushButton {{ background: transparent; color: {text};"
        f" border: 1px solid {border}; border-radius: 6px;"
        f" {font_css(ff, fs)} padding: 0 10px; }}"
        f"QPushButton:hover {{ background: {hover_bg}; }}"
    )


def list_item_style(ff, fs, hover, selected) -> str:
    """列表项样式：QListWidget/QAbstractItemView item padding 8px + hover + selected。"""
    fs = max(10, (fs or 14) - 2)
    return (
        "QListWidget::item, QAbstractItemView::item {"
        f" {font_css(ff, fs)} padding: 8px; border-radius: 6px; }}"
        f"QListWidget::item:hover, QAbstractItemView::item:hover {{ background: {hover}; }}"
        f"QListWidget::item:selected, QAbstractItemView::item:selected {{ background: {selected}; }}"
    )


# ══════════════════════════════════════════════════════════════════
# 组合样式
# ══════════════════════════════════════════════════════════════════


def scrollbar_style(owner=None) -> str:
    """现代窄滚动条（6px 超薄），handle 走主题 scrollbar token，供列表复用。"""
    colors = _ctx_colors(_ctx(owner))
    handle = colors.get("scrollbar_handle_bg") or "rgba(255,255,255,0.20)"
    handle_hover = colors.get("scrollbar_handle_hover_bg") or "rgba(255,255,255,0.30)"
    return (
        "QScrollBar:vertical { width: 6px; background: transparent; margin: 2px; }"
        f"QScrollBar::handle:vertical {{ background: {handle}; min-height: 30px; border-radius: 3px; }}"
        f"QScrollBar::handle:vertical:hover {{ background: {handle_hover}; }}"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        "QScrollBar:horizontal { height: 6px; background: transparent; margin: 2px; }"
        f"QScrollBar::handle:horizontal {{ background: {handle}; min-width: 30px; border-radius: 3px; }}"
        f"QScrollBar::handle:horizontal:hover {{ background: {handle_hover}; }}"
        "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }"
    )


def dialog_style(owner=None, include_line_edit=False) -> str:
    """通用弹窗样式：背景/文字/输入框/列表/按钮，全部走主题 token。"""
    c = theme_colors(owner)
    colors = _ctx_colors(_ctx(owner))
    is_dark = c["is_dark"]
    hover_strong = colors.get("hover_bg_strong") or (
        "rgba(255,255,255,0.16)" if is_dark else "rgba(0,0,0,0.10)"
    )
    line_edit = ""
    if include_line_edit:
        line_edit = (
            f"QLineEdit {{ background: {c['raised']}; border: 1px solid {c['input_border']};"
            f" border-radius: 6px; color: {c['text']}; padding: 5px 10px; }}"
            f"QLineEdit:focus {{ border-color: {c['focus_border']}; }}"
        )
    return (
        f"QDialog {{ background: {c['surface']}; }}"
        f"QLabel {{ color: {c['text']}; }}"
        + line_edit
        + f"QListWidget {{ background: {c['raised']}; border: 1px solid {c['border']};"
        f" border-radius: 8px; color: {c['text']}; }}"
        f"QListWidget::item {{ padding: 8px; border-radius: 4px; }}"
        f"QListWidget::item:hover {{ background: {c['hover']}; }}"
        f"QListWidget::item:selected {{ background: {c['selected']}; }}"
        f"QPushButton {{ background: {c['raised']}; border: 1px solid {c['border']};"
        f" border-radius: 6px; color: {c['text']}; padding: 6px 16px;"
        f" font-size: {max(10, c['fs'] - 1)}px; }}"
        f"QPushButton:hover {{ background: {c['hover']}; }}"
        f"QPushButton:pressed {{ background: {hover_strong}; }}"
    )
