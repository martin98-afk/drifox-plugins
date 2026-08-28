# -*- coding: utf-8 -*-
"""中国象棋视觉资产 — 与主程序 Colors 解耦的"游戏专属"硬编码配色

依据 leader P2 决策：
- 三组主题色（背景 / 主色 / 强调）硬编码此插件，本游戏主题固定反而是好事
- 通用 Token（圆角/间距/字号/阴影）借用主程序 design_tokens（try/except 兜底）

设计目标：
1. 浅米色木纹棋盘 + 圆角阴影棋子 + 卡片式底部面板
2. 主流品牌色彩（中国象棋常见朱红/哑金）
3. 兼容主程序深浅主题切换（浅色背景字色自动反转）
"""

from __future__ import annotations

from typing import Any

# ── 用户硬编码三色（来自需求基线）────────────────────────────
USER_BG = "#f5f5f7"          # 浅色背景
USER_PRIMARY = "#2c5f8d"     # 主色（蓝灰）
USER_ACCENT = "#d4af37"      # 强调色（哑金）

# ── 象棋专用扩展色（基于上述三色派生，不来自主程序）──────────
BOARD_WOOD = "#d9b27a"       # 棋盘木纹主色（暖米黄）
BOARD_WOOD_TOP = "#e3c79a"  # 木纹渐变上端
BOARD_WOOD_MID = "#cfa674"  # 木纹渐变中段
BOARD_WOOD_BOTTOM = "#b58456"  # 木纹渐变下端（深棕收尾）
BOARD_BORDER = "#6b4a2a"     # 棋盘边框
BOARD_LINE = "#3a2a14"       # 棋盘线条（深褐）
BOARD_TEXT = "#3a2a14"       # 河界/标签字色

PIECE_RED = "#c62828"        # 红方边框 + 字色
PIECE_BLACK = "#1a1a1a"      # 黑方边框 + 字色
PIECE_BG_TOP = "#ffffff"     # 棋子径向高光中心
PIECE_BG_RED_MID = "#fbf2dc" # 红方棋子渐变中段（米白）
PIECE_BG_RED_BOT = "#e8d3a3" # 红方棋子渐变外环
PIECE_BG_BLK_MID = "#f4f4f4" # 黑方棋子渐变中段
PIECE_BG_BLK_BOT = "#d8d8d8" # 黑方棋子渐变外环

STATUS_INFO = "#7FDBFF"
STATUS_SUCCESS = "#34d399"
STATUS_WARNING = "#fbbf24"
STATUS_ERROR = "#ef4444"
STATUS_FALLBACK_BG = "rgba(245, 158, 11, 0.8)"  # 兜底走法警告条

# ── InfoBar 红条专用（与 status_error 区开）──────────────────
INFOBAR_ERROR_BG = "rgba(239, 68, 68, 0.12)"
INFOBAR_ERROR_BORDER = "#ef4444"
INFOBAR_WARNING_BG = "rgba(251, 191, 36, 0.12)"
INFOBAR_WARNING_BORDER = "#fbbf24"

# ── 字号（基线，不随主程序缩放 — 游戏专属）─────────────────────
FONT_FAMILY = "'Microsoft YaHei', '楷体', 'Segoe UI'"
PIECE_FONT_PX = 24            # 棋子中文（约 cell*0.46）
STATUS_FONT_PX = 14
LABEL_FONT_PX = 11

# ── 间距 / 圆角 / 阴影（直接给出字面值，不强依赖 design_tokens）───
BORDER_RADIUS_PIECE = 50      # 圆形棋子 = width/2（百分比）
BORDER_RADIUS_CARD = 12       # 卡片容器
BORDER_RADIUS_BTN = 8         # 按钮
PIECE_SHADOW_BLUR = 10
PIECE_SHADOW_OFFSET_Y = 3
PIECE_SHADOW_ALPHA = 120      # rgba 0-255

# ── 棋盘视觉交互色（高亮/合法落点/hover）──
SELECTED_HIGHLIGHT = "#f7c948"     # 选中：金色环
LEGAL_HIGHLIGHT = "#88c97a"        # 合法落点：绿色实心圆
LAST_MOVE_HIGHLIGHT = "#d4a93a"    # 最后走子：橘黄点
HOVER_EMPTY_DOT = "rgba(212, 175, 55, 0.45)"  # 空格 hover：淡黄小点

# ── 走子动效色（#6 升级）──
LAST_MOVE_FROM_HIGHLIGHT = "rgba(102, 152, 255, 0.7)"    # 起点蓝
LAST_MOVE_TO_HIGHLIGHT = "rgba(212, 175, 55, 0.7)"       # 终点金
CAPTURED_PIECE_BG = "#fff4d6"                             # 被吃棋子淡出底色
PATH_ARROW_COLOR = "rgba(212, 175, 55, 0.6)"              # 路径箭头：金色半透


# ── 通用 Token（借用主程序 design_tokens，缺失时不报错）────────
def _import_general_tokens():
    """懒导入主程序设计 Token；失败返回带默认值的占位类。"""
    class _FallbackTokens:
        BorderRadius = type("BR", (), {"SM": "4px", "MD": "8px", "LG": "18px"})()
        Spacing = type("S", (), {"XS": 4, "SM": 8, "MD": 12, "LG": 16, "XL": 20, "XXL": 24})()
        FontSizes = type("FS", (), {"SM": "11px", "MD": "12px", "LG": "14px"})()
        Animations = type("A", (), {"FAST_MS": 150, "NORMAL_MS": 200, "SLOW_MS": 300})()

    try:
        from app.utils.design_tokens import BorderRadius, Spacing, FontSizes, Animations  # type: ignore

        return BorderRadius, Spacing, FontSizes, Animations
    except Exception:
        return (
            _FallbackTokens.BorderRadius,
            _FallbackTokens.Spacing,
            _FallbackTokens.FontSizes,
            _FallbackTokens.Animations,
        )


BorderRadius, Spacing, FontSizes, Animations = _import_general_tokens()


# ── 便捷函数 ────────────────────────────────────────────────────
def piece_shadow_color(alpha: int | None = None) -> str:
    """棋子外阴影 rgba 字符串，alpha 默认 PIECE_SHADOW_ALPHA"""
    a = alpha if alpha is not None else PIECE_SHADOW_ALPHA
    return f"rgba(0, 0, 0, {a})"


def piece_qss_stylesheet(side: str, font_px: int | None = None) -> str:
    """生成棋子 QSS（红/黑两版），供 setStyleSheet() 直接使用。

    Args:
        side: 'red' / 'black'
        font_px: 棋子字号；默认 PIECE_FONT_PX
    """
    fp = font_px or PIECE_FONT_PX
    if side == "red":
        bg_grad = (
            f"qradial-gradient(circle at 35% 30%, "
            f"{PIECE_BG_TOP} 0%, {PIECE_BG_RED_MID} 40%, {PIECE_BG_RED_BOT} 100%)"
        )
        border_c = PIECE_RED
        text_c = PIECE_RED
    else:
        bg_grad = (
            f"qradial-gradient(circle at 35% 30%, "
            f"{PIECE_BG_TOP} 0%, {PIECE_BG_BLK_MID} 50%, {PIECE_BG_BLK_BOT} 100%)"
        )
        border_c = PIECE_BLACK
        text_c = PIECE_BLACK

    return (
        f"QLabel {{"
        f"background: {bg_grad};"
        f"border: 2px solid {border_c};"
        f"border-radius: {BORDER_RADIUS_PIECE}%;"
        f"color: {text_c};"
        f"font-weight: bold;"
        f"font-family: {FONT_FAMILY};"
        f"font-size: {fp}px;"
        f"}}"
    )


def board_qss_stylesheet() -> str:
    """棋盘底板 QSS（木纹渐变 + 边框 + 内阴影）"""
    return (
        f"QWidget#chessBoardPanel {{"
        f"background-color: {BOARD_WOOD};"
        f"background-image:"
        f"  radial-gradient(ellipse at center,"
        f"    rgba(255, 240, 200, 0.35) 0%,"
        f"    rgba(120, 80, 40, 0.0) 70%),"
        f"  repeating-linear-gradient(85deg,"
        f"    rgba(180, 130, 70, 0.18) 0px, rgba(180, 130, 70, 0.18) 1px,"
        f"    transparent 1px, transparent 6px),"
        f"  linear-gradient(180deg, {BOARD_WOOD_TOP} 0%, {BOARD_WOOD_MID} 50%, {BOARD_WOOD_BOTTOM} 100%);"
        f"border: 2px solid {BOARD_BORDER};"
        f"border-radius: {BORDER_RADIUS_CARD}px;"
        f"}}"
    )


def primary_button_qss() -> str:
    """主操作按钮 QSS（金色渐变 + 圆角）"""
    return (
        f"QPushButton {{"
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f" stop:0 {USER_ACCENT}, stop:1 {USER_PRIMARY});"
        f"color: white; border: none;"
        f"border-radius: {BORDER_RADIUS_BTN}px;"
        f"padding: 4px 14px; font-weight: bold;"
        f"}}"
        f"QPushButton:hover {{"
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f" stop:0 {USER_ACCENT}, stop:0.5 {USER_PRIMARY}, stop:1 {USER_ACCENT});"
        f"}}"
    )


def card_container_qss() -> str:
    """卡片容器 QSS（浅色用户基线 + 圆角 + 细边）"""
    return (
        f"QWidget#chessCardPanel {{"
        f"background-color: {USER_BG};"
        f"border: 1px solid rgba(44, 95, 141, 0.25);"
        f"border-radius: {BORDER_RADIUS_CARD}px;"
        f"}}"
    )


def infobar_error_qss() -> str:
    """错误红条 QSS（不依赖 qfluentwidgets，回退样式）"""
    return (
        f"QWidget#infobarError {{"
        f"background-color: {INFOBAR_ERROR_BG};"
        f"border: 1px solid {INFOBAR_ERROR_BORDER};"
        f"border-radius: 6px;"
        f"padding: 8px 12px;"
        f"color: {STATUS_ERROR};"
        f"}}"
    )


def __getattr__(name: str) -> Any:
    """兼容旧调用 _theme.XXX（防遗漏导入）"""
    return globals().get(name)


# ── 合集 QSS（ChessCard._apply_theme() 一次注入）────────────────────

def get_full_qss(card_bg: Optional[str] = None) -> str:
    """返回 ChessCard 的完整 QSS（含卡片容器 + 棋盘底板 + 按钮）。

    Args:
        card_bg: 主卡片背景色；None 时使用 USER_BG（#f5f5f7）

    各 QSS 段：
      1. 外层卡片容器 (#chessCardPanel)
      2. 棋盘底板容器 (#chessBoardPanel) — 木纹三层叠加
      3. 主操作按钮 (#chessPrimaryBtn) — 金→蓝渐变
      4. 危险按钮 (#chessDangerBtn) — 红
      5. 状态标签/提示标签
    """
    bg = card_bg or USER_BG
    return (
        # 1) 外层卡片
        f"QWidget#chessCardPanel {{"
        f"background-color: {bg};"
        f"border: 1px solid rgba(44, 95, 141, 0.20);"
        f"border-radius: {BORDER_RADIUS_CARD}px;"
        f"}}"
        f"QLabel {{ color: #2c2c2c; font-family: {FONT_FAMILY}; }}"
        f"QLabel#chessHintLabel {{ color: rgba(0,0,0,0.55); font-size: {LABEL_FONT_PX}px; }}"
        f"QLabel#chessStatusLabel {{ color: {USER_PRIMARY}; font-size: {STATUS_FONT_PX}px; font-weight: bold; }}"
        f"QWidget#chessStatusBar {{"
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f" stop:0 {bg}, stop:1 #ffffff);"
        f"border-bottom: 1px solid rgba(44, 95, 141, 0.15);"
        f"}}"
        # 2) 棋盘底板（木纹三层叠加）
        f"QWidget#chessBoardPanel {{"
        f"background-color: {BOARD_WOOD};"
        f"background-image:"
        f"  radial-gradient(ellipse at center,"
        f"    rgba(255, 240, 200, 0.35) 0%,"
        f"    rgba(120, 80, 40, 0.0) 70%),"
        f"  repeating-linear-gradient(85deg,"
        f"    rgba(180, 130, 70, 0.18) 0px, rgba(180, 130, 70, 0.18) 1px,"
        f"    transparent 1px, transparent 6px),"
        f"  linear-gradient(180deg, {BOARD_WOOD_TOP} 0%, {BOARD_WOOD_MID} 50%, {BOARD_WOOD_BOTTOM} 100%);"
        f"border: 2px solid {BOARD_BORDER};"
        f"border-radius: 8px;"
        f"}}"
        # 3) 主操作按钮（金→蓝渐变）
        f"QPushButton#chessPrimaryBtn {{"
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f" stop:0 {USER_ACCENT}, stop:1 {USER_PRIMARY});"
        f"color: white; border: none;"
        f"border-radius: 8px;"
        f"padding: 4px 14px;"
        f"font-weight: bold; font-family: {FONT_FAMILY};"
        f"}}"
        f"QPushButton#chessPrimaryBtn:hover {{"
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f" stop:0 #e3c055, stop:0.5 {USER_PRIMARY}, stop:1 #355f8a);"
        f"}}"
        f"QPushButton#chessPrimaryBtn:pressed {{"
        f"background: {USER_PRIMARY};"
        f"padding-top: 5px; padding-left: 15px;"
        f"}}"
        # 4) 危险按钮（如未来重置/终止）
        f"QPushButton#chessDangerBtn {{"
        f"background: {STATUS_ERROR};"
        f"color: white; border: none;"
        f"border-radius: 8px;"
        f"padding: 4px 14px;"
        f"font-weight: bold;"
        f"}}"
        f"QPushButton#chessDangerBtn:hover {{ background: #dc2626; }}"
        # 5) 状态条
        f"QLabel#chessTaskTag {{"
        f"background: rgba(212, 175, 55, 0.15);"
        f"color: {USER_PRIMARY};"
        f"padding: 3px 8px;"
        f"border-radius: 4px;"
        f"font-family: {FONT_FAMILY};"
        f"}}"
    )


def get_piece_qss(side: str, hover: bool = False, selected: bool = False) -> str:
    """生成木制棋子 QSS（红/黑、hover/selected 四种组合）。

    木制质感：深棕木底 + 35% 30% 高光点 + 边缘暗角 + 深棕描边，不透明（alpha=1）。
    红/黑双方同木底，仅文字颜色区分（#c62828 / #1a1a1a），避免黑方不可见。

    Args:
        side: 'red' / 'black'
        hover: hover 高亮态（金色边框）
        selected: 选中态（加粗金色外圈）
    """
    # 木色不透明径向渐变：亮高光 #f0d8a0 → 木黄 #e0b878 → 木橙 #c8924a → 深棕 #8b5a2b
    bg_grad = (
        f"qradial-gradient(circle at 35% 30%, "
        f"#f0d8a0 0%, #e0b878 25%, #c8924a 60%, #8b5a2b 100%)"
    )

    if side == "red":
        text_color = PIECE_RED
    else:
        text_color = PIECE_BLACK

    # hover：金色高亮边框；否则深棕木边
    border_color = USER_ACCENT if hover else "#5a3a1a"

    border_width = "3px" if selected else "2px"
    sel_outline = f"outline: 2px solid {USER_ACCENT};" if selected else ""

    return (
        f"QLabel {{"
        f"background: {bg_grad};"
        f"border: {border_width} solid {border_color};"
        f"border-radius: 50%;"
        f"color: {text_color};"
        f"font-weight: bold;"
        f"font-family: {FONT_FAMILY};"
        f"font-size: {PIECE_FONT_PX}px;"
        f"padding: 0px;"
        f"{sel_outline}"
        f"}}"
    )


def make_piece_shadow(blur_radius: int = 10, offset_y: int = 3, alpha: int = 150):
    """QGraphicsDropShadowEffect 工厂（PySide6 QSS 不支持 box-shadow）。

    木制棋子需更明显的立体阴影：blur=10 / yOffset=3 / alpha=150。
    """
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    from PySide6.QtGui import QColor

    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur_radius)
    shadow.setOffset(0, offset_y)
    shadow.setColor(QColor(0, 0, 0, alpha))
    return shadow


__all__ = [
    # 色值
    "USER_BG", "USER_PRIMARY", "USER_ACCENT",
    "BOARD_WOOD", "BOARD_WOOD_TOP", "BOARD_WOOD_MID", "BOARD_WOOD_BOTTOM",
    "BOARD_BORDER", "BOARD_LINE", "BOARD_TEXT",
    "PIECE_RED", "PIECE_BLACK",
    "STATUS_INFO", "STATUS_SUCCESS", "STATUS_WARNING", "STATUS_ERROR",
    "INFOBAR_ERROR_BG", "INFOBAR_ERROR_BORDER",
    # 字号
    "FONT_FAMILY", "PIECE_FONT_PX", "STATUS_FONT_PX", "LABEL_FONT_PX",
    # 间距/圆角/阴影
    "BORDER_RADIUS_CARD", "BORDER_RADIUS_BTN",
    "PIECE_SHADOW_BLUR", "PIECE_SHADOW_OFFSET_Y", "PIECE_SHADOW_ALPHA",
    # 借用主程序 Token（如可用）
    "BorderRadius", "Spacing", "FontSizes", "Animations",
    # 工具函数
    "piece_shadow_color",
    "piece_qss_stylesheet", "board_qss_stylesheet",
    "primary_button_qss", "card_container_qss", "infobar_error_qss",
    "get_full_qss", "get_piece_qss", "make_piece_shadow",
]
