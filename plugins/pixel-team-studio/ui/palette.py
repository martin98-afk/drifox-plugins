# -*- coding: utf-8 -*-
"""主题色映射 — 将主程序注入的 ctx 转换为卡片可用的配色字典

设计约束（闭包）：
- 不导入 app.core / app.widgets 内部模块
- 黑底黑字免疫（v0.2.0）：文字色亮度决定面板底色——亮字→深底、
  暗字→浅底，两者永远自洽。不再信任 qfluentwidgets isDarkTheme()
  与 theme_manager 注入色可能不一致的问题组合（历史 bug：深底注入黑字）。
- QColor("#RRGGBBAA") 在 Qt 按 #AARRGGBB 解析（8 位 hex 全是坑），
  所有带 alpha 颜色一律用 QColor(r,g,b,a) 构造。
"""

from typing import Optional

from PySide6.QtGui import QColor


def _luminance(c: QColor) -> float:
    """感知亮度 0-255"""
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def _parse(raw: Optional[str]) -> Optional[QColor]:
    """解析注入色字符串（#hex / rgba()），无效返回 None"""
    if not raw:
        return None
    c = QColor(str(raw).strip())
    return c if c.isValid() else None


def _with_alpha(c: QColor, a: int) -> QColor:
    out = QColor(c)
    out.setAlpha(a)
    return out


def make_palette(ctx: Optional[dict] = None) -> dict:
    """从上下文 colors 构建配色字典（含 QColor 值 + 字体信息）

    ctx 缺失/空时回退暗色默认，保证任何情况下卡片可渲染。
    """
    ctx = ctx or {}
    raw = ctx.get("colors", {}) or {}

    # ── 文字色（权威来源：主程序注入的主题色）──
    text = _parse(raw.get("text_primary")) or QColor("#f0f0f5")
    text_secondary = _parse(raw.get("text_secondary")) or _with_alpha(text, 170)

    # ── 底色跟随文字亮度（自洽，杜绝黑底黑字 / 白底白字）──
    is_dark = _luminance(text) >= 128

    # 对比度兜底：极端低对比主题色强制回退安全色
    if is_dark and _luminance(text) < 100:
        text = QColor("#f0f0f5")
    if not is_dark and _luminance(text) > 150:
        text = QColor("#26262e")
    if is_dark:
        if _luminance(text_secondary) < 100:
            text_secondary = _with_alpha(text, 175)
    else:
        if _luminance(text_secondary) > 150:
            text_secondary = _with_alpha(text, 175)

    def _pick(key: str, fb_dark: str, fb_light: str) -> QColor:
        c = _parse(raw.get(key))
        if c is not None:
            return c
        return QColor(fb_dark if is_dark else fb_light)

    accent = _pick("accent", "#62a0ea", "#2878dc")
    success = _pick("success", "#50e3c2", "#00a888")
    warning = _pick("accent_warm", "#ffc107", "#f59e0b")
    danger = _pick("danger", "#ff6b6b", "#e5484d")

    return {
        "is_dark": is_dark,
        "text": text,
        "text_secondary": text_secondary,
        "accent": accent,
        "accent_fill": _with_alpha(accent, 56),
        "success": success,
        "success_fill": _with_alpha(success, 46),
        "warning": warning,
        "danger": danger,
        "danger_fill": _with_alpha(danger, 46),
        # 面板底色（不透明度 >90%，避免底下内容透出显脏）
        "panel_bg": QColor(16, 18, 27, 242) if is_dark else QColor(250, 250, 252, 246),
        "panel_border": QColor(255, 255, 255, 36) if is_dark else QColor(0, 0, 0, 30),
        "card_bg": QColor(255, 255, 255, 16) if is_dark else QColor(0, 0, 0, 10),
        "card_bg_active": _with_alpha(accent, 20),
        "border": QColor(255, 255, 255, 28) if is_dark else QColor(0, 0, 0, 28),
        "hover_bg": QColor(255, 255, 255, 26) if is_dark else QColor(0, 0, 0, 16),
        "badge_bg": QColor(255, 255, 255, 24) if is_dark else QColor(0, 0, 0, 16),
        "font_family": ctx.get("font_family", "Microsoft YaHei"),
        "font_size": ctx.get("font_size", 14),
    }


def rgba(c: QColor, alpha: int = -1) -> str:
    """QColor → rgba() 字符串（供 QSS 使用）"""
    a = c.alpha() if alpha < 0 else alpha
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"
