# -*- coding: utf-8 -*-
"""浏览器插件主题颜色解析。"""


def theme_colors(owner=None) -> dict:
    try:
        from qfluentwidgets import isDarkTheme

        is_dark = isDarkTheme()
    except Exception:
        is_dark = True

    ctx = {}
    provider = getattr(owner, "_context_provider", None)
    if provider is not None:
        try:
            ctx = provider() or {}
        except Exception:
            pass
    colors = ctx.get("colors", {})
    return {
        "is_dark": is_dark,
        "text": colors.get("text_primary") or ("rgba(255,255,255,0.90)" if is_dark else "rgba(0,0,0,0.85)"),
        "secondary": colors.get("text_secondary") or ("rgba(255,255,255,0.58)" if is_dark else "rgba(0,0,0,0.55)"),
        "border": colors.get("border") or "rgba(128,128,128,0.25)",
        "surface": colors.get("surface") or ("#1e1e1e" if is_dark else "#ffffff"),
        "raised": colors.get("card") or ("#252525" if is_dark else "#f5f5f5"),
        "hover": "#333333" if is_dark else "#e8e8e8",
    }


def scrollbar_style(owner=None) -> str:
    """现代窄滚动条，供收藏、历史和下载列表复用。"""
    c = theme_colors(owner)
    return (
        "QScrollBar:vertical { width: 10px; background: transparent; margin: 2px; }"
        f"QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 28px; border-radius: 4px; }}"
        "QScrollBar::handle:vertical:hover { background: rgba(100,140,210,0.75); }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        "QScrollBar:horizontal { height: 10px; background: transparent; margin: 2px; }"
        f"QScrollBar::handle:horizontal {{ background: {c['border']}; min-width: 28px; border-radius: 4px; }}"
        "QScrollBar::handle:horizontal:hover { background: rgba(100,140,210,0.75); }"
        "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }"
    )


def dialog_style(owner=None, include_line_edit=False) -> str:
    c = theme_colors(owner)
    line_edit = (
        f"QLineEdit {{ background: {c['raised']}; border: 1px solid {c['border']}; border-radius: 6px;"
        f" color: {c['text']}; padding: 5px 10px; }}"
        if include_line_edit else ""
    )
    return (
        f"QDialog {{ background: {c['surface']}; }}"
        f"QLabel {{ color: {c['text']}; }}"
        + line_edit
        + f"QListWidget {{ background: {c['raised']}; border: 1px solid {c['border']}; border-radius: 6px; color: {c['text']}; }}"
        "QListWidget::item { padding: 6px; }"
        "QListWidget::item:selected { background: rgba(0,120,215,0.4); }"
        f"QPushButton {{ background: {c['raised']}; border: 1px solid {c['border']}; border-radius: 6px;"
        f" color: {c['text']}; padding: 6px 14px; }}"
        f"QPushButton:hover {{ background: {c['hover']}; }}"
    )
