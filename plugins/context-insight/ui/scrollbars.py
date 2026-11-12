# -*- coding: utf-8 -*-
"""统一滚动条样式 —— 插件内自绘，颜色随 Palette 明暗主题。"""

from __future__ import annotations

from .theme import Palette
from .widgets import css


def scrollbar_style(palette: Palette, width: int = 8) -> str:
    width = max(4, min(int(width), 20))
    handle = palette.alpha(palette.text_primary, 50)
    hover = palette.alpha(palette.text_primary, 90)
    return f"""
        QScrollBar:vertical {{
            background: transparent;
            width: {width}px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {css(handle)};
            border-radius: {width // 2}px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover,
        QScrollBar::handle:vertical:pressed {{
            background: {css(hover)};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: {width}px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {css(handle)};
            border-radius: {width // 2}px;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover,
        QScrollBar::handle:horizontal:pressed {{
            background: {css(hover)};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
    """
