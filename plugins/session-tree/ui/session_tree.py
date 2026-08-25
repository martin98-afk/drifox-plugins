# -*- coding: utf-8 -*-
"""SessionTreeCard — 会话树浮动卡片（左侧停靠）

类似 Codex 桌面版左侧面板：按时间分组展示当前项目的会话列表。

功能：
- 按时间分组：今天 / 昨天 / 近7天 / 近30天 / 更早（按 last_time），组标题可折叠
- 团队会话（team_run_id 非空）聚合为子树：父节点（团队）+ 成员子节点，可折叠
- 树层级白线：子节点左侧竖线 + 连接横线（跟随主题深浅）
- 顶部搜索框（200ms 防抖）：按标题/预览/agent 名过滤，搜索时自动展开全部
- 点击会话项 → 切换会话（main_widget._switch_to_session_by_id）
- 顶部「新建」按钮 → 新建会话（main_widget._create_new_session）
- 右键菜单：重命名 / 归档 / 永久删除
- 当前会话高亮 + 自动滚动可见

性能设计（防卡）：
- 3s 轮询走「指纹对比」：主题指纹 / 列表指纹（session_id+title+last_time+query）
  无变化则不重建、不重设样式、不 setText
- item 内容级 diff：复用 widget 时仅更新变化的文本
- 组标题/树节点按 key 复用（不 deleteLater 重建）
- set_colors 值比对：主题未变不重复解析 QSS
- 折叠/展开状态跨刷新保持（不随轮询重置）

响应式宽度：
- 宽模式（>= 240px）：两行（标题 + 预览），时间右对齐
- 窄模式（< 240px）：单行紧凑，头部隐藏标题/计数
- 超窄（item < 130px）：隐藏时间标签，空间全给标题
- 标题/预览用 ElideMiddle 省略 + tooltip 全文

设计约束（闭包）：
- 不导入 app.core / app.widgets 内部模块
- 数据访问仅通过 ctx["main_widget"] 的公开属性/方法
"""

import datetime
import re
from typing import Callable, Dict, List, Optional, Tuple

from loguru import logger
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CaptionLabel, FluentIcon, IconWidget, StrongBodyLabel, TransparentToolButton, isDarkTheme

# ── 常量 ──────────────────────────────────────────────────

_GROUP_ORDER = ("today", "yesterday", "7d", "30d", "older")
_GROUP_LABELS = {"today": "今天", "yesterday": "昨天", "7d": "近7天", "30d": "近30天", "older": "更早"}
_REFRESH_INTERVAL_MS = 3000  # 轮询刷新间隔
_MODE_THRESHOLD = 240  # 宽/窄模式切换阈值（px）
_ITEM_H_WIDE = 54  # 宽模式会话项高度（两行）
_ITEM_H_NARROW = 34  # 窄模式会话项高度（单行）
_MIN_WIDTH = 120  # 卡片最小宽度（dock 拖拽下限）
_SEARCH_DEBOUNCE_MS = 200  # 搜索防抖
_TREE_LINE_X = 5  # 树竖线 x 坐标（item 内）
_TREE_INDENT = 16  # 子项内容左缩进


# ── 工具函数 ──────────────────────────────────────────────


def _parse_ts(ts: str) -> Optional[datetime.datetime]:
    """解析 "YYYY-MM-DD HH:MM:SS" → datetime；失败返回 None"""
    if not ts:
        return None
    try:
        return datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _group_of(ts: str, now: datetime.datetime) -> str:
    """按 last_time 归类：today / yesterday / 7d / 30d / older"""
    dt = _parse_ts(ts)
    if dt is None:
        return "older"
    today = now.date()
    day = dt.date()
    if day == today:
        return "today"
    if day == today - datetime.timedelta(days=1):
        return "yesterday"
    if (today - day).days < 7:
        return "7d"
    if (today - day).days <= 30:
        return "30d"
    return "older"


def _time_text(ts: str, group: str) -> str:
    """会话项右侧时间文本：今天 HH:MM / 昨天 / N天前 / MM-DD"""
    dt = _parse_ts(ts)
    if dt is None:
        return ""
    if group == "today":
        return dt.strftime("%H:%M")
    if group == "yesterday":
        return "昨天"
    if group == "7d":
        days = (datetime.date.today() - dt.date()).days
        return f"{days}天前"
    return dt.strftime("%m-%d")


def _preview_text(session: Dict, max_len: int = 46) -> str:
    """会话预览文本：优先 DB preview，回退空串"""
    p = (session.get("preview") or "").strip()
    if p:
        return p if len(p) <= max_len else p[:max_len] + "…"
    return ""


def _hex_color(ctx: dict, key: str, light: str, dark: str) -> QColor:
    """从 context colors 取色，rgba()/hex 兼容，失败回退默认"""
    raw = ctx.get("colors", {}).get(key, "")
    if raw:
        m = re.match(r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)", raw)
        if m:
            a = float(m.group(4)) if m.group(4) is not None else 1.0
            return QColor(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(a * 255))
        return QColor(raw)
    return QColor(dark if ctx.get("is_dark", True) else light)


def _colors_from_ctx(ctx: dict) -> dict:
    """从 context 构造颜色字典（供会话项/组标题渲染）"""
    is_dark = ctx.get("is_dark", True)
    return {
        "accent": _hex_color(ctx, "accent", "#2878dc", "#62a0ea"),
        "text": _hex_color(ctx, "text_primary", "#1f1f1f", "#ffffff"),
        "text_secondary": _hex_color(ctx, "text_secondary", "#6b6b6b", "#9d9d9d"),
        "border": _hex_color(ctx, "border", "#d0d0d0", "#2e2e2e"),
        "tree_line": QColor(0, 0, 0, 76) if not is_dark else QColor(255, 255, 255, 76),
        "is_dark": is_dark,
        "font_family": ctx.get("font_family", "Microsoft YaHei"),
        "font_size": ctx.get("font_size", 14),
    }


def _theme_fingerprint(ctx: dict) -> Tuple:
    """主题指纹：colors/字体/明暗任一变化才重刷样式"""
    colors = ctx.get("colors", {})
    return (
        ctx.get("is_dark"),
        ctx.get("font_family"),
        ctx.get("font_size"),
        colors.get("accent"),
        colors.get("text_primary"),
        colors.get("text_secondary"),
        colors.get("border"),
        ctx.get("card_bg"),
    )


def _list_fingerprint(sessions: List[Dict], query: str = "") -> Tuple:
    """列表指纹：数量 + (session_id, title, last_time) 序列 + 搜索词，无变化不重建"""
    return (
        len(sessions),
        query,
        tuple((s.get("session_id"), s.get("title"), s.get("last_time")) for s in sessions),
    )


def _build_tree_rows(sessions: List[Dict], query: str) -> List[Tuple[str, Dict, Optional[List[Dict]]]]:
    """把平铺会话列表聚合为树行（保持原时间降序）

    Returns:
        [(kind, session, children), ...]
        - kind="normal": 普通会话，children=None
        - kind="team": 团队父节点（用最新成员会话），children=成员列表
        团队会话（team_run_id 非空）按 run_id 聚合；搜索时父节点保留当任一成员匹配，
        子项仅保留匹配成员；普通会话直接过滤。
    """
    q = (query or "").strip().lower()

    def _match(s: Dict) -> bool:
        if not q:
            return True
        hay = " ".join(
            [
                (s.get("title") or ""),
                (s.get("preview") or ""),
                (s.get("agent_name") or ""),
                (s.get("team_name") or ""),
            ]
        ).lower()
        return q in hay

    rows: List[Tuple[str, Dict, Optional[List[Dict]]]] = []
    seen_teams: set = set()
    for s in sessions:
        run_id = (s.get("team_run_id") or "").strip()
        if not run_id:
            if _match(s):
                rows.append(("normal", s, None))
            continue
        if run_id in seen_teams:
            continue
        seen_teams.add(run_id)
        members = [m for m in sessions if (m.get("team_run_id") or "").strip() == run_id]
        matched = [m for m in members if _match(m)]
        if not matched:
            continue
        rows.append(("team", s, matched))
    return rows


# ══════════════════════════════════════════════════════════
# 自动省略 QLabel（ElideMiddle）
# ══════════════════════════════════════════════════════════


class _ElidedLabel(QLabel):
    """自动根据可用宽度省略文本的 QLabel（中间省略 + tooltip 全文）"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self.setToolTip(text if text else None)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._apply_plain()

    def setText(self, text: str):  # noqa: N802
        self._full_text = text
        self.setToolTip(text if text else None)
        self._update_elided()

    def set_full(self, text: str):
        """设置完整文本（同 setText 语义，命名更明确）"""
        self.setText(text)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._update_elided()

    def _apply_plain(self):
        self.setTextFormat(Qt.PlainText)

    def _update_elided(self):
        w = self.width()
        if w <= 0:
            self._apply_plain()
            if self.text() != self._full_text:
                super().setText(self._full_text)
            return
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full_text, Qt.ElideMiddle, w)
        self._apply_plain()
        if self.text() != elided:
            super().setText(elided)


# ══════════════════════════════════════════════════════════
# 单个会话项（支持树层级）
# ══════════════════════════════════════════════════════════


class _SessionItem(QWidget):
    """会话树节点

    kind:
      - "normal": 普通会话
      - "team": 团队父节点（箭头折叠 + 👥 前缀）
      - "member": 团队成员子节点（缩进 + 树线 + 👤 前缀）
    depth=1 的子节点在左侧绘制树层级白线（竖线 + 连接横线）。
    """

    clicked = pyqtSignal(str)  # session_id（团队节点传 run_id）
    rightClicked = pyqtSignal(str, object)
    toggled = pyqtSignal(str)  # 折叠切换（团队节点传 run_id）

    def __init__(
        self,
        session_id: str,
        kind: str,
        depth: int,
        title: str,
        time_text: str,
        preview: str,
        colors: dict,
        parent=None,
    ):
        super().__init__(parent)
        self._sid = session_id
        self._kind = kind
        self._depth = depth
        self._colors: dict = {}
        self._raw_title = title
        self._time_text = time_text
        self._raw_preview = preview
        self._collapsed = False
        self._wide = False  # 初始 False，让 set_wide(True) 生效（设置固定高度）
        self.setObjectName("SessionItem")
        self.setProperty("current", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 树层级线（子控件实现，避免 paintEvent + QPainter 在 QSS 环境下
        # 触发 Qt 5.15 崩溃 0xc0000409；视觉等价 1px 竖线 + 连接横线）
        self._tree_v = QFrame(self)
        self._tree_v.setObjectName("treeV")
        self._tree_v.setFixedWidth(1)
        self._tree_v.hide()
        self._tree_h = QFrame(self)
        self._tree_h.setObjectName("treeH")
        self._tree_h.setFixedHeight(1)
        self._tree_h.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(10 + (depth * _TREE_INDENT), 4, 8, 4)
        root.setSpacing(1)

        # 第一行：箭头（团队）+ 标题 + 时间
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)
        self._arrow_lb = QLabel("▾", self)
        self._arrow_lb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._arrow_lb.setVisible(kind == "team")
        title_row.addWidget(self._arrow_lb, 0)

        self._title_lb = _ElidedLabel(title, self)
        title_row.addWidget(self._title_lb, 1)

        self._time_lb = QLabel(time_text, self)
        self._time_lb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        title_row.addWidget(self._time_lb, 0, Qt.AlignRight)
        root.addLayout(title_row)

        # 第二行：预览（宽模式显示）
        self._preview_lb = _ElidedLabel(preview, self)
        root.addWidget(self._preview_lb)

        self.set_colors(colors)
        self.set_wide(True)

    # ── 数据更新（内容级 diff：未变化不重设） ──

    def update_content(self, title: str, time_text: str, preview: str):
        if title != self._raw_title:
            self._raw_title = title
            self._title_lb.set_full(title)
        if time_text != self._time_text:
            self._time_text = time_text
            self._time_lb.setText(time_text)
        if preview != self._raw_preview:
            self._raw_preview = preview
            self._preview_lb.set_full(preview)

    # ── 模式 ──

    def set_wide(self, wide: bool):
        """宽/窄模式切换：宽=两行（标题+预览），窄=单行"""
        if wide == self._wide:
            return
        self._wide = wide
        self.setFixedHeight(_ITEM_H_WIDE if wide else _ITEM_H_NARROW)
        self._preview_lb.setVisible(wide)
        self._update_tree_lines()
        self.update()

    # ── 折叠（团队节点） ──

    def set_collapsed(self, collapsed: bool):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._arrow_lb.setText("▸" if collapsed else "▾")
        self._update_tree_lines()
        self.update()

    # ── 主题 ──

    def set_colors(self, colors: dict):
        if colors == self._colors:
            return
        self._colors = colors
        self._apply_style()

    def _apply_style(self):
        c = self._colors
        accent = c["accent"]
        self._arrow_lb.setStyleSheet(
            f"color: {c['text_secondary'].name()}; background: transparent; border: none;"
            f"font-size: {c['font_size'] - 2}px; font-family: {c['font_family']};"
        )
        self._title_lb.setStyleSheet(
            f"color: {c['text'].name()}; background: transparent; border: none;"
            f"font-size: {c['font_size']}px; font-family: {c['font_family']};"
        )
        self._time_lb.setStyleSheet(
            f"color: {c['text_secondary'].name()}; background: transparent; border: none;"
            f"font-size: {max(c['font_size'] - 3, 9)}px; font-family: {c['font_family']};"
        )
        self._preview_lb.setStyleSheet(
            f"color: {c['text_secondary'].name()}; background: transparent; border: none;"
            f"font-size: {max(c['font_size'] - 3, 9)}px; font-family: {c['font_family']};"
        )
        # 挂载 hover/current 背景 QSS（动态属性 current 变化时 refresh）
        hover_bg = "rgba(128,128,128,0.10)" if c["is_dark"] else "rgba(0,0,0,0.06)"
        cur_bg = f"rgba({accent.red()},{accent.green()},{accent.blue()},0.16)"
        cur_border = f"rgba({accent.red()},{accent.green()},{accent.blue()},255)"
        super().setStyleSheet(
            f"QWidget#SessionItem {{ background: transparent; border-radius: 6px; border: none; }}"
            f"QWidget#SessionItem:hover {{ background: {hover_bg}; }}"
            f"QWidget#SessionItem[current=\"true\"] {{"
            f"  background: {cur_bg}; border-left: 3px solid {cur_border}; border-radius: 6px; }}"
        )
        # 树线颜色跟随主题
        tl = c["tree_line"].name()
        self._tree_v.setStyleSheet(f"QFrame#treeV {{ background: {tl}; border: none; }}")
        self._tree_h.setStyleSheet(f"QFrame#treeH {{ background: {tl}; border: none; }}")

    def set_current(self, is_current: bool):
        if self.property("current") == is_current:
            return
        self.setProperty("current", is_current)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    # ── 事件 ──

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        try:
            # 超窄（单行模式且宽度不足）：隐藏时间标签，空间全给标题
            want_time = self._wide or self.width() >= 130
            if want_time != self._time_lb.isVisible():
                self._time_lb.setVisible(want_time)
            self._update_tree_lines()
        except RuntimeError:
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._kind == "team":
                self.toggled.emit(self._sid)
            else:
                self.clicked.emit(self._sid)
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(self._sid, event.globalPos())
        super().mousePressEvent(event)

    # ── 树层级线（子控件定位，替代 paintEvent + QPainter） ──

    def _update_tree_lines(self):
        """按深度/折叠状态摆放树线子控件

        - member（depth=1）：竖线顶到底 + 中间连接横线
        - team 父节点（展开）：竖线从中间到底（衔接首个成员竖线）
        """
        h = self.height()
        mid = h // 2
        if self._depth > 0:
            self._tree_v.setGeometry(_TREE_LINE_X, 0, 1, h)
            self._tree_h.setGeometry(_TREE_LINE_X, mid, 9, 1)
            self._tree_v.show()
            self._tree_h.show()
        elif self._kind == "team" and not self._collapsed:
            self._tree_v.setGeometry(_TREE_LINE_X, mid, 1, max(h - mid, 0))
            self._tree_v.show()
            self._tree_h.hide()
        else:
            self._tree_v.hide()
            self._tree_h.hide()


# ══════════════════════════════════════════════════════════
# 分组标题（可折叠）
# ══════════════════════════════════════════════════════════


class _GroupHeader(QLabel):
    """时间分组标题（今天 / 昨天 / 近7天 …），点击折叠/展开"""

    toggled = pyqtSignal(str)  # group key

    def __init__(self, text: str, group_key: str, colors: dict, parent=None):
        super().__init__(text, parent)
        self._colors: dict = {}
        self._group_key = group_key
        self._collapsed = False
        self.setObjectName("GroupHeader")
        self.setContentsMargins(10, 10, 8, 2)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")
        self.set_colors(colors)

    def set_collapsed(self, collapsed: bool):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._apply_style()

    def set_colors(self, colors: dict):
        if colors == self._colors:
            return
        self._colors = colors
        self._apply_style()

    def _apply_style(self):
        c = self._colors
        arrow = "▸" if self._collapsed else "▾"
        hover_bg = "rgba(128,128,128,0.08)" if c["is_dark"] else "rgba(0,0,0,0.05)"
        self.setStyleSheet(
            f"QWidget#GroupHeader {{ color: {c['text_secondary'].name()}; background: transparent;"
            f" border: none; border-radius: 4px;"
            f" font-size: {max(c['font_size'] - 3, 9)}px; font-family: {c['font_family']}; }}"
            f"QWidget#GroupHeader:hover {{ background: {hover_bg}; }}"
        )
        self.setText(f"{arrow} {_GROUP_LABELS[self._group_key]}")

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.toggled.emit(self._group_key)
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════
# 主卡片
# ══════════════════════════════════════════════════════════


class SessionTreeCard(QWidget):
    """会话树浮动卡片 — 停靠在 Tab 窗口左侧停靠区"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._provider: Optional[Callable[[], dict]] = None
        self._colors: dict = {
            "accent": QColor(98, 160, 234),
            "text": QColor(255, 255, 255),
            "text_secondary": QColor(157, 157, 157),
            "border": QColor(46, 46, 46),
            "tree_line": QColor(255, 255, 255, 76),
            "is_dark": True,
            "font_family": "Microsoft YaHei",
            "font_size": 14,
        }
        self._items: Dict[str, _SessionItem] = {}  # key -> item（普通/团队用 sid，成员用 sid）
        self._headers: Dict[str, _GroupHeader] = {}  # group -> header
        self._current_sid: str = ""
        self._current_project: str = ""
        self._theme_fp: Optional[Tuple] = None
        self._list_fp: Optional[Tuple] = None
        self._wide = True
        self._query = ""
        self._collapsed_groups: set = set()
        self._collapsed_teams: set = set()
        self._search_timer: Optional[QTimer] = None
        self._setup_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(_REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._on_tick)
        self._refresh_timer.start()

    # ── UI 构建 ──

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── 头部：图标 + 标题 + 计数 + 按钮 ──
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 0, 0)
        header.setSpacing(2)

        self._header_icon = IconWidget(FluentIcon.CHAT, self)
        self._header_icon.setFixedSize(18, 18)
        header.addWidget(self._header_icon, 0)

        self._title_lb = StrongBodyLabel("会话", self)
        header.addWidget(self._title_lb, 0)

        self._count_lb = CaptionLabel("", self)
        header.addWidget(self._count_lb, 1, Qt.AlignVCenter)

        self._new_btn = TransparentToolButton(FluentIcon.ADD, self)
        self._new_btn.setToolTip("新建会话")
        self._new_btn.clicked.connect(self._on_new_clicked)
        header.addWidget(self._new_btn, 0)

        self._refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self._refresh_btn.setToolTip("刷新列表")
        self._refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self._refresh_btn, 0)
        root.addLayout(header)

        # ── 搜索框 ──
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("搜索会话…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(28)
        self._search.textChanged.connect(self._on_search_changed)
        root.addWidget(self._search)

        # ── 列表 ──
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.NoFrame)

        self._list_container = QWidget(self._scroll)
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._list_container)
        root.addWidget(self._scroll, 1)

        # ── 分隔线 + 底部项目信息 ──
        self._sep = QFrame(self)
        self._sep.setFrameShape(QFrame.HLine)
        self._sep.setFixedHeight(1)
        root.addWidget(self._sep)

        self._footer_lb = CaptionLabel("", self)
        self._footer_lb.setContentsMargins(4, 2, 4, 0)
        root.addWidget(self._footer_lb)

        self.setMinimumWidth(_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    # ── 上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._provider = provider
        self._theme_fp = None
        self._list_fp = None
        self._refresh()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._theme_fp = None
        self._list_fp = None
        # 延迟到事件循环稳定后刷新：避免在窗口 show 事件栈内做重量级重建
        # + ensureWidgetVisible（启动早期布局未完成时操作滚动区有崩溃风险）
        QTimer.singleShot(0, self._refresh)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        try:
            self._apply_mode()
        except RuntimeError:
            pass

    # ── 主题 ──

    def _apply_latest_theme(self, ctx: dict) -> bool:
        """应用最新主题；返回是否有变化"""
        fp = _theme_fingerprint(ctx)
        if fp == self._theme_fp:
            return False
        self._theme_fp = fp

        self._colors = _colors_from_ctx(ctx)
        font_family = self._colors["font_family"]
        font_size = self._colors["font_size"]
        self.setFont(QFont(font_family, font_size))
        self._title_lb.setStyleSheet(
            f"color: {self._colors['text'].name()}; font-size: {font_size + 1}px; font-family: {font_family};"
        )
        self._count_lb.setStyleSheet(
            f"color: {self._colors['text_secondary'].name()}; font-size: {max(font_size - 3, 9)}px;"
            f"font-family: {font_family};"
        )
        self._search.setStyleSheet(
            f"QLineEdit {{ background: rgba(128,128,128,0.12); border: none; border-radius: 8px;"
            f" padding: 0 10px; color: {self._colors['text'].name()};"
            f" font-size: {font_size}px; font-family: {font_family}; }}"
            f"QLineEdit::placeholder {{ color: {self._colors['text_secondary'].name()}; }}"
        )
        self._sep.setStyleSheet(f"background: {self._colors['border'].name()};")
        self._footer_lb.setStyleSheet(
            f"color: {self._colors['text_secondary'].name()}; font-size: {max(font_size - 3, 9)}px;"
            f"font-family: {font_family};"
        )
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self._scroll.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }"
            "QScrollBar::handle:vertical { background: rgba(128,128,128,0.35); border-radius: 3px; min-height: 24px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(128,128,128,0.55); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        for item in self._items.values():
            item.set_colors(self._colors)
        for header in self._headers.values():
            header.set_colors(self._colors)
        return True

    # ── 宽/窄模式 ──

    def _apply_mode(self):
        wide = self.width() >= _MODE_THRESHOLD
        if wide == self._wide:
            return
        self._wide = wide
        for item in self._items.values():
            item.set_wide(wide)
        self._title_lb.setVisible(wide)
        self._count_lb.setVisible(wide)
        self._search.setPlaceholderText("搜索会话…" if wide else "搜索…")

    # ── 数据刷新 ──

    def _on_search_changed(self, text: str):
        """搜索输入防抖：200ms 后刷新"""
        if self._search_timer is None:
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(self._apply_search)
        self._search_timer.start(_SEARCH_DEBOUNCE_MS)

    def _apply_search(self):
        self._query = self._search.text().strip()
        self._list_fp = None
        self._refresh()

    def _on_tick(self):
        """定时轮询：仅可见时刷新；指纹无变化时零开销"""
        if not self.isVisible():
            return
        try:
            self._refresh()
        except RuntimeError:
            pass

    def _refresh(self):
        """完整刷新：主题指纹 + 列表指纹双门控，未变化跳过重建"""
        if self._provider is None:
            return
        try:
            ctx = self._provider()
        except Exception as e:
            logger.debug(f"[session-tree] provider 异常: {e}")
            return
        mw = ctx.get("main_widget")
        if mw is None:
            return

        theme_changed = self._apply_latest_theme(ctx)
        self._apply_mode()

        project = getattr(mw, "_current_project", "") or ""
        if not project:
            project = "默认项目"
        self._current_project = project
        self._current_sid = getattr(mw, "_current_session_id", "") or ""

        sessions: List[Dict] = []
        hm = getattr(mw, "history_manager", None)
        if hm is not None and hasattr(hm, "get_history_list"):
            try:
                sessions = list(hm.get_history_list(project=project) or [])
            except Exception as e:
                logger.debug(f"[session-tree] get_history_list 异常: {e}")
                sessions = []

        fp = _list_fingerprint(sessions, self._query)
        if fp == self._list_fp and not theme_changed:
            # 列表未变 + 主题未变：只更新当前高亮（切换会话场景）
            if self._current_sid != getattr(self, "_last_highlighted_sid", None):
                self._update_highlight()
            return

        self._list_fp = fp
        self._rebuild(sessions)
        self._update_footer(len(sessions))

    # ── 列表重建（增量复用，内容级 diff + 折叠/搜索） ──

    def _rebuild(self, sessions: List[Dict]):
        now = datetime.datetime.now()
        rows = _build_tree_rows(sessions, self._query)
        searching = bool(self._query)

        groups: Dict[str, List] = {}
        for row in rows:
            g = _group_of(row[1].get("last_time") or "", now)
            groups.setdefault(g, []).append(row)

        # 当前列表中的 widget 全部取出（含组标题/会话项/stretch）
        pulled: list = []
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                pulled.append(w)

        existing_items: Dict[str, _SessionItem] = {}
        existing_headers: Dict[str, _GroupHeader] = {}
        leftover: list = []
        for w in pulled:
            sid = getattr(w, "_sid", None)
            gkey = getattr(w, "_group_key", None)
            if sid is not None and sid in self._items:
                existing_items[sid] = w
            elif gkey is not None and gkey in self._headers:
                existing_headers[gkey] = w
            else:
                leftover.append(w)
        for w in leftover:
            try:
                w.setParent(None)
                w.deleteLater()
            except RuntimeError:
                pass
        self._items = {}
        self._headers = {}

        for g in _GROUP_ORDER:
            group_rows = groups.get(g)
            if not group_rows:
                continue
            # 组标题（复用）
            header = existing_headers.pop(g, None)
            if header is None:
                header = _GroupHeader(_GROUP_LABELS[g], g, self._colors, self._list_container)
                header.toggled.connect(self._on_group_toggled)
            else:
                header.set_colors(self._colors)
            group_collapsed = g in self._collapsed_groups and not searching
            header.set_collapsed(group_collapsed)
            self._list_layout.addWidget(header)
            self._headers[g] = header
            if group_collapsed:
                continue
            # 会话项 / 团队子树
            for row in group_rows:
                kind, s, children = row
                sid = s.get("session_id", "")
                if not sid:
                    continue
                if kind == "team":
                    self._render_team_node(existing_items, s, children, searching)
                else:
                    self._render_leaf(existing_items, s, kind, 0, g)

        # 未复用的旧 header/item → 删除
        for w in list(existing_items.values()) + list(existing_headers.values()):
            try:
                w.setParent(None)
                w.deleteLater()
            except RuntimeError:
                pass

        # 末尾 stretch（顶部对齐）
        self._list_layout.addStretch(1)

        # 当前会话滚动可见（仅切换时；启动早期滚动区未布局时静默跳过）
        self._last_highlighted_sid = self._current_sid
        cur = self._items.get(self._current_sid)
        if cur is not None:
            try:
                self._scroll.ensureWidgetVisible(cur, 0, 40)
            except RuntimeError:
                pass

    def _render_leaf(self, existing_items, s: Dict, kind: str, depth: int, g: str):
        """渲染普通会话 / 团队成员子节点"""
        sid = s.get("session_id", "")
        title = s.get("title") or "未命名会话"
        preview = _preview_text(s)
        if kind == "member":
            agent = (s.get("agent_name") or "").strip()
            if agent:
                title = f"👤 {title}"
                preview = f"成员 {agent}"
        item = existing_items.pop(sid, None)
        if item is None or item._kind != kind or item._depth != depth:
            if item is not None:
                try:
                    item.setParent(None)
                    item.deleteLater()
                except RuntimeError:
                    pass
            item = _SessionItem(
                sid, kind, depth, title, _time_text(s.get("last_time") or "", g), preview, self._colors, self._list_container
            )
            item.clicked.connect(self._on_item_clicked)
            item.rightClicked.connect(self._on_item_right_clicked)
        else:
            item.update_content(title, _time_text(s.get("last_time") or "", g), preview)
            item.set_colors(self._colors)
        item.set_wide(self._wide)
        item.set_current(sid == self._current_sid)
        self._list_layout.addWidget(item)
        self._items[sid] = item

    def _render_team_node(self, existing_items, s: Dict, members: List[Dict], searching: bool):
        """渲染团队父节点 + 成员子树"""
        run_id = (s.get("team_run_id") or "").strip()
        team_name = (s.get("team_name") or "").strip() or "团队会话"
        title = f"👥 {team_name}"
        time_text = f"{len(members)} 成员"
        latest = max(members, key=lambda m: m.get("last_time") or "")
        preview = f"最后活动 {_time_text(latest.get('last_time') or '', _group_of(latest.get('last_time') or '', datetime.datetime.now()))}"

        item = existing_items.pop(run_id, None)
        if item is None or item._kind != "team" or item._depth != 0:
            if item is not None:
                try:
                    item.setParent(None)
                    item.deleteLater()
                except RuntimeError:
                    pass
            item = _SessionItem(run_id, "team", 0, title, time_text, preview, self._colors, self._list_container)
            item.toggled.connect(self._on_team_toggled)
        else:
            item.update_content(title, time_text, preview)
            item.set_colors(self._colors)
        team_collapsed = run_id in self._collapsed_teams and not searching
        item.set_collapsed(team_collapsed)
        item.set_wide(self._wide)
        item.set_current(False)
        self._list_layout.addWidget(item)
        self._items[run_id] = item

        if team_collapsed:
            return
        for member in members:
            self._render_leaf(existing_items, member, "member", 1, _group_of(member.get("last_time") or "", datetime.datetime.now()))

    def _update_highlight(self):
        """列表结构未变时只更新当前高亮（切换会话场景）"""
        self._last_highlighted_sid = self._current_sid
        for sid, item in self._items.items():
            item.set_current(sid == self._current_sid)
        cur = self._items.get(self._current_sid)
        if cur is not None:
            try:
                self._scroll.ensureWidgetVisible(cur, 0, 40)
            except RuntimeError:
                pass

    def _update_footer(self, count: int):
        self._count_lb.setText(f"{count}")
        self._footer_lb.setText(f"{self._current_project} · {count} 个会话")

    # ── 折叠交互 ──

    def _on_group_toggled(self, group_key: str):
        if group_key in self._collapsed_groups:
            self._collapsed_groups.discard(group_key)
        else:
            self._collapsed_groups.add(group_key)
        self._list_fp = None
        self._refresh()

    def _on_team_toggled(self, run_id: str):
        if run_id in self._collapsed_teams:
            self._collapsed_teams.discard(run_id)
        else:
            self._collapsed_teams.add(run_id)
        self._list_fp = None
        self._refresh()

    # ── 交互 ──

    def _on_new_clicked(self):
        mw = self._active_main_widget()
        if mw is None:
            return
        try:
            mw._create_new_session()
        except Exception as e:
            logger.warning(f"[session-tree] 新建会话失败: {e}")

    def _on_item_clicked(self, session_id: str):
        mw = self._active_main_widget()
        if mw is None:
            return
        try:
            mw._switch_to_session_by_id(session_id)
        except Exception as e:
            logger.warning(f"[session-tree] 切换会话失败: {e}")

    def _on_item_right_clicked(self, session_id: str, global_pos):
        mw = self._active_main_widget()
        if mw is None:
            return
        menu = QMenu(self)
        rename_action = menu.addAction("✏️ 重命名")
        archive_action = menu.addAction("📦 归档会话")
        menu.addSeparator()
        delete_action = menu.addAction("🗑 永久删除")
        chosen = menu.exec_(global_pos)
        if chosen is None:
            return
        if chosen == rename_action:
            self._rename_session(mw, session_id)
        elif chosen == archive_action:
            self._archive_session(mw, session_id)
        elif chosen == delete_action:
            self._delete_session(mw, session_id)

    def _active_main_widget(self):
        """动态解析当前活跃 Tab 的 main_widget（多窗口隔离）"""
        if self._provider is None:
            return None
        try:
            return self._provider().get("main_widget")
        except Exception:
            return None

    # ── 会话操作（数据层 + 主程序 UI 同步） ──

    def _rename_session(self, mw, session_id: str):
        hm = getattr(mw, "history_manager", None)
        if hm is None:
            return
        idx = hm.find_index_by_session_id(session_id)
        if idx is None:
            return
        record = hm.get_session_by_session_id(session_id) or {}
        old_title = record.get("title") or record.get("name") or "未命名会话"
        new_title, ok = QInputDialog.getText(self, "重命名会话", "新标题：", QLineEdit.Normal, old_title)
        if not ok or not (new_title or "").strip():
            return
        new_title = new_title.strip()
        hm.update_session_title(idx, new_title)
        hm.set_user_edited_title(idx, True)
        try:
            store = getattr(mw, "session_store", None)
            if store is not None and hasattr(store, "update_session_title"):
                store.update_session_title(session_id, new_title)
        except Exception:
            pass
        try:
            sm = getattr(mw, "session_manager", None)
            cs = sm.get_current_session() if sm is not None else None
            if cs is not None and getattr(cs, "session_id", "") == session_id:
                if hasattr(cs, "set_topic_summary"):
                    cs.set_topic_summary(new_title)
                if hasattr(cs, "set_user_edited_title"):
                    cs.set_user_edited_title(True)
                if hasattr(mw, "_sync_dialog_title"):
                    mw._sync_dialog_title()
        except Exception:
            pass
        try:
            mw._notify_history_data_changed()
        except Exception:
            pass
        self._refresh()

    def _archive_session(self, mw, session_id: str):
        hm = getattr(mw, "history_manager", None)
        if hm is None:
            return
        idx = hm.find_index_by_session_id(session_id)
        if idx is None:
            return
        # 归档当前会话：先切到新会话（内部自动保存当前会话），避免 UI 指向已归档会话
        if session_id == getattr(mw, "_current_session_id", ""):
            try:
                mw._create_new_session()
            except Exception:
                pass
            idx = hm.find_index_by_session_id(session_id)
            if idx is None:
                return
        try:
            archived = hm.archive_history(idx)
        except Exception as e:
            logger.warning(f"[session-tree] 归档失败: {e}")
            return
        if not archived:
            return
        try:
            be = getattr(mw, "backend", None)
            if be is not None and getattr(be, "tool_executor", None) and getattr(be, "file_recorder", None):
                be.file_recorder.clear_session(session_id)
        except Exception:
            pass
        try:
            mw._notify_history_data_changed()
        except Exception:
            pass
        self._refresh()

    def _delete_session(self, mw, session_id: str):
        ret = QMessageBox.warning(
            self,
            "永久删除会话",
            "该会话将被永久删除，此操作不可恢复。\n确定继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        # 删除当前会话：先切到新会话
        if session_id == getattr(mw, "_current_session_id", ""):
            try:
                mw._create_new_session()
            except Exception:
                pass
        hm = getattr(mw, "history_manager", None)
        try:
            store = getattr(mw, "session_store", None)
            if store is not None and hasattr(store, "delete_session"):
                store.delete_session(session_id)
        except Exception:
            pass
        if hm is not None and hasattr(hm, "remove_session"):
            try:
                hm.remove_session(session_id, release_messages_only=False)
            except Exception:
                pass
        try:
            be = getattr(mw, "backend", None)
            if be is not None and getattr(be, "tool_executor", None) and getattr(be, "file_recorder", None):
                be.file_recorder.clear_session(session_id)
        except Exception:
            pass
        try:
            mw._notify_history_data_changed()
        except Exception:
            pass
        self._refresh()

    # ── 关闭/清理 ──

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()
