# -*- coding: utf-8 -*-
"""像素小人绘制 — QPainter 8-bit 风格智能体精灵

设计约束（闭包）：
- 不导入 app.core / app.widgets 内部模块
- 纯 QPainter 绘制，无外部图片资源
- 每个 agent 角色有专属配色与特征（皇冠/眼镜/头盔/天线…）
"""

from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QWidget


# ── 角色色板 ─────────────────────────────────────────────
# hair: 头发/帽子色；body: 身体主色；accent: 特征色（皇冠/高光/装饰）
AGENT_STYLES: Dict[str, Dict[str, str]] = {
    "leader": {"hair": "#F5B301", "body": "#8B5CF6", "accent": "#FFD700"},
    "plan": {"hair": "#1E3A5F", "body": "#3B82F6", "accent": "#93C5FD"},
    "build": {"hair": "#F97316", "body": "#EA580C", "accent": "#FDE68A"},
    "review": {"hair": "#059669", "body": "#10B981", "accent": "#A7F3D0"},
    "code-reviewer": {"hair": "#B91C1C", "body": "#EF4444", "accent": "#FCA5A5"},
    "explore": {"hair": "#0E7490", "body": "#06B6D4", "accent": "#67E8F9"},
    "task-executor": {"hair": "#4B5563", "body": "#6B7280", "accent": "#D1D5DB"},
    "compaction": {"hair": "#CA8A04", "body": "#EAB308", "accent": "#FEF08A"},
    "title": {"hair": "#DB2777", "body": "#EC4899", "accent": "#FBCFE8"},
    "researcher": {"hair": "#7C3AED", "body": "#A78BFA", "accent": "#DDD6FE"},
    "analyst": {"hair": "#0F766E", "body": "#14B8A6", "accent": "#99F6E4"},
    "designer": {"hair": "#C026D3", "body": "#E879F9", "accent": "#F5D0FE"},
    "tester": {"hair": "#B45309", "body": "#F59E0B", "accent": "#FDE68A"},
    "architect": {"hair": "#334155", "body": "#64748B", "accent": "#CBD5E1"},
    "writer": {"hair": "#9D174D", "body": "#F472B6", "accent": "#FBCFE8"},
    "security": {"hair": "#065F46", "body": "#10B981", "accent": "#A7F3D0"},
    "ops": {"hair": "#78350F", "body": "#D97706", "accent": "#FDE68A"},
    "translator": {"hair": "#1D4ED8", "body": "#60A5FA", "accent": "#DBEAFE"},
}
# 未知角色变体色板（按名字哈希选取，同角色多窗口可区分）
VARIANT_STYLES: List[Dict[str, str]] = [
    {"hair": "#475569", "body": "#94A3B8", "accent": "#E2E8F0"},
    {"hair": "#7C2D12", "body": "#C2410C", "accent": "#FDBA74"},
    {"hair": "#14532D", "body": "#16A34A", "accent": "#BBF7D0"},
    {"hair": "#1E3A8A", "body": "#2563EB", "accent": "#BFDBFE"},
    {"hair": "#4A044E", "body": "#9333EA", "accent": "#E9D5FF"},
    {"hair": "#831843", "body": "#DB2777", "accent": "#FBCFE8"},
    {"hair": "#064E3B", "body": "#0D9488", "accent": "#99F6E4"},
    {"hair": "#450A0A", "body": "#DC2626", "accent": "#FECACA"},
    {"hair": "#422006", "body": "#CA8A04", "accent": "#FEF08A"},
    {"hair": "#0C4A6E", "body": "#0891B2", "accent": "#A5F3FC"},
]
DEFAULT_STYLE: Dict[str, str] = VARIANT_STYLES[0]

# 发型变体（按行覆盖，哈希选取；与角色专属特征叠加时角色特征优先）
HAIR_VARIANTS: Dict[str, Dict[int, str]] = {
    "default": {},
    "flat": {  # 平头
        0: "..HHHH....",
        1: ".HHHHHH...",
        2: "..HHHH....",
    },
    "spiky": {  # 莫西干
        0: "...HH.....",
        1: "..HHHH....",
        2: ".HHHHHH...",
    },
    "cap": {  # 棒球帽
        0: "HHHHHHHH..",
        1: "HHHHHHHH..",
        2: "..HHH.....",
    },
    "long": {  # 长发
        0: ".HHHHHH...",
        1: "HHHHHHHH..",
        2: "HHHHHHHH..",
        3: ".SSSSSS...",
        4: "HSEESSEH..",
        5: "HSSSSSSH..",
    },
    "bald": {  # 光头 + 小胡子
        0: "..........",
        1: "..........",
        2: "..........",
        4: ".SEESSE...",
        6: "...HHH....",
    },
}
SKIN = "#F1C27D"
EYE = "#3B2F2F"

# ── 像素网格模板（12 宽 × 16 高）────────────────────────
# 字符映射：H=hair  S=skin  E=eye  B=body  D=body阴影  W=accent高光
BASE_GRID: List[str] = [
    "..HHHH....",   # 0 头发顶
    ".HHHHHH...",   # 1
    ".HHHHHH...",   # 2
    ".SSSSSS...",   # 3 脸
    ".SEESSE...",   # 4 眼睛
    ".SSSSSS...",   # 5
    "..SSSS....",   # 6 下巴
    ".BBBBBB...",   # 7 身体
    "BBBBBBBB..",   # 8
    "BBBBBBBB..",   # 9
    "BBDDBBDD..",   # 10 腰带
    "BBBBBBBB..",   # 11
    ".BB..BB...",   # 12 腿
    ".BB..BB...",   # 13
    ".BB..BB...",   # 14
    ".BBB.BBB..",   # 15 脚
]

# 角色特征覆盖（按行替换）
FEATURE_OVERLAYS: Dict[str, Dict[int, str]] = {
    # leader：金色皇冠（2 行）+ 无头发
    "leader": {
        0: "..W..W....",
        1: "WWWWWWWW..",
        2: ".WWWWWW...",
    },
    # plan：大框眼镜（眼睛行全框）
    "plan": {
        4: ".EEEEEE...",
    },
    # build：安全帽 + 宽帽檐（row2 加宽）
    "build": {
        2: "HHHHHHHH..",
    },
    # explore：天线（头顶加一行天线杆 + 信号球）
    "explore": {
        0: "....H.W...",
        1: "....H.....",
    },
    # task-executor：耳麦（头发两侧加弧）
    "task-executor": {
        2: ".HHHHHHH..",
    },
    # code-reviewer：贝雷帽（头发顶部加 accent 横条）
    "code-reviewer": {
        0: "WWWWWWWW..",
    },
    # compaction：书本装饰（身体右侧加 W 竖条）
    "compaction": {
        8: "BBBBBBBBBW",
        9: "BBBBBBBBBW",
        11: "BBBBBBBBBW",
    },
    # title：铅笔发型（头顶 accent 尖）
    "title": {
        0: ".WWWWW....",
    },
}

# ── 状态定义 ─────────────────────────────────────────────
# 状态 → (徽标字符, 状态点颜色, 中文名)
STATE_DEFS: Dict[str, Tuple[str, str, str]] = {
    "streaming": ("▸▸", "#50E3C2", "输出中"),
    "thinking": ("…", "#62A0EA", "思考中"),
    "question": ("?", "#FFC107", "提问中"),
    "error": ("!", "#FF6B6B", "异常"),
    "busy": ("⚙", "#FFA726", "忙碌"),
    "idle": ("", "#50C878", "空闲"),
}


def _hash_idx(s: str, n: int) -> int:
    """字符串哈希取模（稳定，同输入同结果）"""
    return sum(ord(c) for c in s) % n if s else 0


def _pick_hair_variant(s: str) -> Optional[Dict[int, str]]:
    keys = list(HAIR_VARIANTS.keys())
    return HAIR_VARIANTS[keys[_hash_idx(s + "hair", len(keys))]]


def get_agent_style(agent_name: str, salt: str = "") -> Dict[str, str]:
    """按角色名取色板（忽略括号变体，如 build(branch) → build）

    salt（如 window_id）参与哈希：未知角色按盐选变体色板，
    无专属特征的角色按盐选发型变体——同角色多成员可视觉区分。
    """
    base = agent_name.split("(")[0].strip().lower()
    if base in AGENT_STYLES:
        style = dict(AGENT_STYLES[base])
        style["hair_variant"] = None if FEATURE_OVERLAYS.get(base) else _pick_hair_variant(base + salt)
    else:
        style = dict(VARIANT_STYLES[_hash_idx(base + salt, len(VARIANT_STYLES))])
        style["hair_variant"] = _pick_hair_variant(base + salt)
    return style


def draw_pixel_sprite(
    painter: QPainter,
    x: int,
    y: int,
    scale: int,
    agent_name: str,
    bounce: int = 0,
    salt: str = "",
):
    """在 (x, y) 处绘制像素小人（左上角为基准，bounce 为上下浮动偏移）"""
    style = get_agent_style(agent_name, salt)
    hair = QColor(style["hair"])
    body = QColor(style["body"])
    accent = QColor(style["accent"])
    skin = QColor(SKIN)
    eye = QColor(EYE)
    body_dark = body.darker(130)

    char_map = {
        "H": hair,
        "S": skin,
        "E": eye,
        "B": body,
        "D": body_dark,
        "W": accent,
    }

    grid = list(BASE_GRID)
    base = agent_name.split("(")[0].strip().lower()
    overlay = FEATURE_OVERLAYS.get(base)
    if overlay:
        for row, line in overlay.items():
            if 0 <= row < len(grid):
                grid[row] = line
    else:
        hair_variant = style.get("hair_variant")
        if hair_variant:
            for row, line in hair_variant.items():
                if 0 <= row < len(grid):
                    grid[row] = line

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, False)
    for row, line in enumerate(grid):
        for col, ch in enumerate(line):
            if ch == " " or ch == ".":
                continue
            color = char_map.get(ch)
            if color is None:
                continue
            painter.fillRect(
                QRectF(x + col * scale, y + (row + bounce) * scale, scale, scale),
                color,
            )
    painter.restore()


class PixelSprite(QWidget):
    """像素小人控件 — 小人 + 头顶状态徽标 + 脚下上下文进度条 + 状态点

    尺寸：sprite 12×16 网格 × scale + 徽标区 + 进度条区
    """

    SPRITE_W = 12
    SPRITE_H = 16
    GRID = 3  # 默认 scale

    def __init__(self, agent_name: str, parent=None, scale: int = 3, salt: str = ""):
        super().__init__(parent)
        self._agent_name = agent_name
        self._salt = salt
        self._scale = scale
        self._state: str = "idle"
        self._context_percent: float = 0.0  # 0-100
        self._bounce_frame = 0
        w, h = self._calc_size()
        self.setFixedSize(w, h)

    def _calc_size(self):
        w = self.SPRITE_W * self._scale
        h = (
            self.SPRITE_H * self._scale
            + 14  # 顶部徽标区
            + 8  # 底部进度条区
        )
        return w, h

    # ── 外部接口 ──

    def set_state(self, state: str):
        """设置工作状态：streaming/thinking/question/error/busy/idle"""
        state = state or "idle"
        if state != self._state:
            self._state = state
            self._bounce_frame = 0
            self.update()

    def set_context(self, percent: float):
        """设置上下文负荷百分比 0-100"""
        percent = max(0.0, min(100.0, float(percent or 0)))
        if abs(percent - self._context_percent) > 0.5:
            self._context_percent = percent
            self.update()

    def advance_bounce(self):
        """忙碌动画帧推进（busy 状态小人上下浮动）"""
        if self._state in ("busy", "streaming", "thinking"):
            self._bounce_frame += 1
            self.update()

    # ── 绘制 ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w, h = self.width(), self.height()
        sc = self._scale
        sw = self.SPRITE_W * sc
        sx = (w - sw) // 2

        # 顶部状态徽标（居中）
        badge, _, _ = STATE_DEFS.get(self._state, STATE_DEFS["idle"])
        if badge:
            painter.setPen(QColor(255, 255, 255, 200))
            font = painter.font()
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, w, 14), Qt.AlignCenter, badge)

        # 浮动偏移：busy 时小跳
        bounce = 0
        if self._state in ("busy", "streaming", "thinking"):
            bounce = 1 if (self._bounce_frame // 3) % 2 == 0 else 0

        # 像素小人
        draw_pixel_sprite(painter, sx, 14, sc, self._agent_name, bounce, self._salt)

        # 底部：上下文进度条（像素风，左对齐）
        bar_y = 14 + self.SPRITE_H * sc + 3
        bar_w = sw
        bar_h = 3
        painter.fillRect(QRectF(sx, bar_y, bar_w, bar_h), QColor(255, 255, 255, 30))
        pct = self._context_percent / 100.0
        if pct > 0:
            if pct < 0.6:
                bar_color = QColor("#50E3C2")
            elif pct < 0.85:
                bar_color = QColor("#FFC107")
            else:
                bar_color = QColor("#FF6B6B")
            fill_w = max(2, int(bar_w * pct))
            painter.fillRect(QRectF(sx, bar_y, fill_w, bar_h), bar_color)

        # 右下角状态点
        dot_r = 4
        dot_color = STATE_DEFS.get(self._state, STATE_DEFS["idle"])[1]
        painter.setPen(QPen(QColor(0, 0, 0, 120), 1))
        painter.setBrush(QColor(dot_color))
        painter.drawEllipse(
            QRectF(sx + bar_w - dot_r * 2, bar_y + bar_h + 2, dot_r * 2, dot_r * 2)
        )

        painter.end()


def state_cn(state: str) -> str:
    """状态 → 中文名"""
    return STATE_DEFS.get(state, STATE_DEFS["idle"])[2]
