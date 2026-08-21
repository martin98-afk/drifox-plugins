# -*- coding: utf-8 -*-
"""ProjectSideRailCard — 响应式项目侧栏

设计要点：
- 宽高自适应：窄模式（< _MODE_THRESHOLD）只显示项目彩色 icon 列，
  宽模式（>= _MODE_THRESHOLD）显示完整项目选择器（搜索 + 新建 + 列表 + 操作）
- 复用 DriFox 现有项目数据：history_manager.get_projects() + memory_manager.get_working_directory()
- 复用 DriFox 既有切换逻辑：main_widget._on_project_selected(project)
- 复用主程序项目选择卡片（ProjectSelectorCardContent）作为宽模式内容，
  仅复用现有公开 widget 类，不修改主程序
- 头像自绘（QPainter），保证小尺寸下无 QSS 抗锯齿问题
- 主题色 + 字体跟随主程序 context_provider

设计约束：
- 不直接 import 主程序私有模块
- 通过 ctx["main_widget"] 走主程序公开属性，避免硬耦合
- 最小宽度设为 40px，使 dock splitter 可拖到只显示 icon 列
"""

import os
import re
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Callable, Dict, List, Optional

from loguru import logger
from PyQt5.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import isDarkTheme


# ══════════════════════════════════════════════════════════
# 主题色辅助
# ══════════════════════════════════════════════════════════


def _make_colors_from_context(ctx: dict) -> dict:
    """从 context 构造颜色字典"""
    is_dark = ctx.get("is_dark", True)
    raw = ctx.get("colors", {})

    def _hex(key: str, light: str, dark: str) -> QColor:
        val = raw.get(key, "")
        if val:
            m = re.match(r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d+))?\s*\)", val)
            if m:
                a = int(m.group(4)) if m.group(4) is not None else 255
                return QColor(int(m.group(1)), int(m.group(2)), int(m.group(3)), a)
            return QColor(val)
        return QColor(dark if is_dark else light)

    def _card_bg() -> QColor:
        raw_bg = ctx.get("card_bg") or raw.get("card_bg") or ""
        if not raw_bg:
            return QColor(33, 33, 38) if is_dark else QColor(245, 245, 247)
        m = re.match(r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d+))?\s*\)", raw_bg)
        if m:
            a = int(m.group(4)) if m.group(4) is not None else 255
            return QColor(int(m.group(1)), int(m.group(2)), int(m.group(3)), a)
        return QColor(raw_bg)

    return {
        "accent": _hex("accent", "#2878dc", "#62a0ea"),
        "border": _hex("border", "#cccccc80", "#ffffff1e"),
        "text": _hex("text_primary", "#000000", "#ffffff"),
        "text_secondary": _hex("text_secondary", "#666666", "#aaaaaa"),
        "card_bg": _card_bg(),
        "is_dark": is_dark,
        "font_family": ctx.get("font_family", "Microsoft YaHei"),
        "font_size": ctx.get("font_size", 14),
    }


# ══════════════════════════════════════════════════════════
# 项目首字母 + 颜色算法（独立实现，与主程序行为对齐）
# ══════════════════════════════════════════════════════════


def _extract_initials(name: str) -> str:
    """从项目名提取 1-2 字缩写（与主程序 extract_project_initials 行为对齐）"""
    if not name:
        return "?"
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in name)
    if has_cjk:
        for c in name:
            if "\u4e00" <= c <= "\u9fff":
                return c
        return name[0]
    for delim in ("_", "-", " "):
        if delim in name:
            parts = [p for p in name.split(delim) if p]
            if len(parts) >= 2:
                return (parts[0][0] + parts[-1][0]).upper()
            name = parts[0]
            break
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1|\2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1|\2", s)
    words = [w for w in s.split("|") if w]
    if len(words) >= 2:
        return (words[0][0] + words[-1][0]).upper()
    if len(name) >= 2:
        return name[:2].upper()
    return name.upper()


def _project_color(name: str, alpha: int = 255) -> QColor:
    """项目色 — HSL 全空间哈希（与主程序 get_project_color 行为对齐）"""
    import colorsys

    crc = zlib.crc32(name.encode("utf-8"))
    h = crc % 360
    s = 55 + ((crc >> 8) % 31)
    l = 50 + ((crc >> 16) % 16)
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l / 100.0, s / 100.0)
    return QColor(int(round(r * 255)), int(round(g * 255)), int(round(b * 255)), alpha)


# ══════════════════════════════════════════════════════════
# 窄模式 — 单个项目 icon widget
# ══════════════════════════════════════════════════════════


class _ProjectIcon(QWidget):
    """单个项目图标 — 与主程序 ProjectItem 视觉对齐

    主程序 ProjectItem._SINGLE_LINE_HEIGHT = 30，layout.setContentsMargins(10, 0, 4, 0)
    avatar 24×24 squircle 5px radius。本 widget 模拟同样视觉密度：
    - 高度 30（一致）
    - 宽度 40 = 24(icon) + 8×2(左右边距，对齐 ProjectItem 的 10/4 不对称 → 居中对称)
    - avatar 垂直居中（与 ProjectItem 的 AlignVCenter 一致）
    - 不画左侧强调条（窄模式无空间放置 ✓）；hover/当前状态用背景 + 颜色变化表达
    """

    clicked = pyqtSignal(str)
    rightClicked = pyqtSignal(str, object)

    _SIZE = QSize(40, 30)  # 高度 30 对齐 ProjectItem 单行；宽度 40 给左右各 8px 边距
    _ICON = 24
    _RADIUS = 5

    def __init__(self, project: str, is_current: bool, colors: dict, parent=None):
        super().__init__(parent)
        self._project = project
        self._is_current = is_current
        self._colors = colors
        self._initials = _extract_initials(project)
        # 当前项目色饱和度+15%（更亮）
        self._bg_color = _project_color(project, alpha=255 if is_current else 230)
        self._bg_color_normal = _project_color(project)
        self._hovered = False
        self.setFixedSize(self._SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def set_current(self, is_current: bool):
        if self._is_current != is_current:
            self._is_current = is_current
            self._bg_color = _project_color(self._project, alpha=255 if is_current else 230)
            self.update()

    def set_colors(self, colors: dict):
        self._colors = colors
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._project)
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(self._project, event.globalPos())
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = self.rect()
        # hover 背景：与主程序 ProjectItem hover 风格一致（圆角 6px）
        if self._hovered:
            bg = self._colors.get("card_bg", QColor(33, 33, 38))
            is_dark = self._colors.get("is_dark", True)
            hover_bg = bg.lighter(130) if is_dark else bg.darker(105)
            painter.setPen(Qt.NoPen)
            painter.setBrush(hover_bg)
            painter.drawRoundedRect(rect, 6, 6)

        # 当前项目：左侧 3px 强调条（与主程序 ✓ 位置对应）
        if self._is_current:
            accent = self._colors.get("accent", QColor(98, 160, 234))
            painter.setPen(Qt.NoPen)
            painter.setBrush(accent)
            painter.drawRoundedRect(2, 6, 3, 18, 1, 1)

        # icon squircle（24×24 居中），与主程序 _SquareAvatar 完全一致
        icon_size = self._ICON
        icon_x = (rect.width() - icon_size) // 2
        icon_y = (rect.height() - icon_size) // 2
        icon_rect = QRect(icon_x, icon_y, icon_size, icon_size)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._bg_color)
        painter.drawRoundedRect(icon_rect, self._RADIUS, self._RADIUS)

        painter.setPen(Qt.white)
        font = QFont(self._colors.get("font_family", "Microsoft YaHei"))
        font.setPixelSize(int(icon_size * 14 / 24))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(icon_rect, Qt.AlignCenter, self._initials)


# ══════════════════════════════════════════════════════════
# 窄模式 — 竖向 icon 列
# ══════════════════════════════════════════════════════════


class ProjectSideRailNarrow(QWidget):
    """窄模式：竖向 icon 列 + 顶部小标题 + 底部刷新按钮"""

    projectClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider: Optional[Callable[[], dict]] = None
        self._colors: dict = {}
        self._icons: Dict[str, _ProjectIcon] = {}
        self._current_project: str = ""
        self._workdirs: Dict[str, str] = {}
        self._setup_ui()

    def set_context_provider(self, provider: Callable[[], dict]):
        self._provider = provider
        self._refresh()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 4, 0, 4)
        root_layout.setSpacing(4)

        self._title_label = QLabel("项目", self)
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root_layout.addWidget(self._title_label)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.NoFrame)

        self._list_container = QWidget(self._scroll)
        self._list_container.setObjectName("projectSideRailListContainer")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 4, 0, 4)
        # 1px 间距对齐主程序 ProjectItem 视觉密度
        self._list_layout.setSpacing(1)
        self._list_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._list_container)
        root_layout.addWidget(self._scroll, 1)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)
        toolbar.setSpacing(0)
        toolbar.addStretch(1)
        # 新建项目按钮（替代原"刷新"按钮）：SVG 图标，点击弹输入框
        self._new_btn = QToolButton(self)
        self._new_btn.setFixedSize(28, 28)
        self._new_btn.setToolTip("新建项目")
        self._new_btn.setCursor(Qt.PointingHandCursor)
        self._new_btn.setIcon(QIcon(str(Path(__file__).resolve().parent.parent / "icons" / "add.svg")))
        self._new_btn.setIconSize(QSize(16, 16))
        self._new_btn.clicked.connect(self._on_new_project_clicked)
        toolbar.addWidget(self._new_btn)
        toolbar.addStretch(1)
        root_layout.addLayout(toolbar)

    def _on_new_project_clicked(self):
        """新建项目：弹主程序同款 SingleInputDialog（与项目卡片标题栏"+"完全等价）

        走与主程序 _on_header_new_project 完全等价的路径：完全匹配项目名 → 切换；
        空 → 无操作；否则 → 触发 _on_new_project_created。
        加载失败时回退到 QInputDialog（开发期 / 主程序缺 API）。
        """
        name = ""
        try:
            from app.widgets.cards.settings.memory_card import SingleInputDialog

            _captured: list = [""]
            _dialog = SingleInputDialog(
                title="📁 新建项目",
                hint="将在主程序项目中创建一个新项目",
                placeholder="项目名称",
                default_text="",
                confirm_text="创建",
                cancel_text="取消",
                # parent 取顶层窗口（Tab 模式下为 TabManagerWindow），与主程序一致
                parent=self.window().window() if self.window() else self.window(),
            )

            def _on_confirmed(text: str):
                _captured[0] = text

            _dialog.confirmed.connect(_on_confirmed)
            _dialog.exec_()
            name = _captured[0].strip() if _captured[0] else ""
        except Exception as e:
            logger.debug(f"[project-side-rail] SingleInputDialog unavailable, fallback to QInputDialog: {e}")
            from PyQt5.QtWidgets import QInputDialog

            name, ok = QInputDialog.getText(self, "新建项目", "项目名：", text="")
            name = name.strip() if (ok and name) else ""

        if not name:
            return
        # 完全匹配现有项目 → 切换；否则 → 新建
        existing = list(self._icons.keys())
        if name in existing:
            self.projectClicked.emit(name)
        else:
            if hasattr(self.parent(), "_on_project_signal"):
                self.parent()._on_project_signal("newProjectCreated", name)

    def apply_theme(self, colors: dict):
        self._colors = colors
        ff = colors.get("font_family", "Microsoft YaHei")
        fs = colors.get("font_size", 12)
        tc = colors.get("text", QColor(255, 255, 255))
        accent = colors.get("accent", QColor(98, 160, 234))
        self._title_label.setStyleSheet(
            f"color: {tc.name()}; background: transparent; font-family: '{ff}'; "
            f"font-size: {max(10, fs - 2)}px; font-weight: bold; padding: 4px 0;"
        )
        self._list_container.setStyleSheet("#projectSideRailListContainer { background: transparent; }")
        # 滚动条样式与主程序一致（窄模式垂直 4px、handle 圆角、悬停加宽）
        sb_w = 4
        sb_handle = tc.name()
        sb_hover = accent.name()
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: transparent; }}"
            f"QScrollBar:vertical {{ background: transparent; width: {sb_w}px; margin: 0; }}"
            f"QScrollBar::handle:vertical {{ background: {sb_handle}; "
            f"border-radius: {sb_w // 2}px; min-height: 30px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {sb_hover}; width: {sb_w + 2}px; }}"
            f"QScrollBar::handle:vertical:pressed {{ background: {sb_hover}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}"
        )
        self.setStyleSheet("ProjectSideRailNarrow { background: transparent; }")
        # 新建按钮：主题色 + hover 强调底
        self._new_btn.setStyleSheet(
            f"QToolButton {{ color: {tc.name()}; background: transparent; border: none; "
            f"border-radius: 4px; padding: 0; }}"
            f"QToolButton:hover {{ background: rgba({accent.red()}, {accent.green()}, {accent.blue()}, 80); }}"
            f"QToolButton:pressed {{ background: rgba({accent.red()}, {accent.green()}, {accent.blue()}, 120); }}"
        )
        for icon in self._icons.values():
            icon.set_colors(self._colors)

    def _refresh(self):
        if self._provider is None:
            return
        try:
            ctx = self._provider()
        except Exception as e:
            logger.debug(f"[project-side-rail] narrow _refresh: {e}")
            return
        mw = ctx.get("main_widget")
        if mw is None:
            return

        current = getattr(mw, "_current_project", "") or ""
        self._current_project = current

        projects: List[str] = []
        hm = getattr(mw, "history_manager", None)
        if hm is not None and hasattr(hm, "get_projects"):
            try:
                projects = list(hm.get_projects() or [])
            except Exception as e:
                logger.debug(f"[project-side-rail] get_projects failed: {e}")
        if current and current not in projects:
            projects.insert(0, current)
        # 与主程序 set_projects_data 一致：不再次去重（get_projects 已返回不重复列表）

        try:
            memory_mgr = getattr(mw.backend, "memory_manager", None) if getattr(mw, "backend", None) else None
            for p in projects:
                if p in self._workdirs:
                    continue
                wd = ""
                if memory_mgr is not None and hasattr(memory_mgr, "get_working_directory"):
                    try:
                        wd = memory_mgr.get_working_directory(p) or ""
                    except Exception:
                        wd = ""
                if not wd:
                    wd = getattr(mw, "_current_workdir", {}).get(p, "")
                self._workdirs[p] = wd
        except Exception as e:
            logger.debug(f"[project-side-rail] get_working_directory failed: {e}")

        self._rebuild_icons(projects)
        self._update_current_highlight()

    def _rebuild_icons(self, projects: List[str]):
        """按 projects 列表顺序重建 icon（与主程序 ProjectItem 顺序完全一致）

        实现要点：
        1. 不在用 takeAt(0) + deleteLater()（延迟删除 + 立刻复用会丢 widget）
        2. 从 layout 中取出所有 widget（不删），复用现有 / 创建缺失 / 丢弃多余
        3. 按 projects 顺序重新插入；复用时必须更新 is_current（避免高亮残留）
        4. 多余的 widget 才 deleteLater
        """
        # 把当前 layout 里的所有 widget 取出（包括 stretch 占位）
        # 注意：stretch 是 QSpacerItem，没有 widget()，靠 isEmpty() 跳过
        pulled: list = []
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                pulled.append(w)

        # pulled 里可能混有 stretch（无 widget，已被跳过）→ 现在剩下的全是 _ProjectIcon
        # 按 _project 属性建映射，方便按项目名复用
        existing_map: Dict[str, "_ProjectIcon"] = {}
        leftover: list = []
        for w in pulled:
            proj = getattr(w, "_project", None)
            if proj is not None and proj in self._icons:
                existing_map[proj] = w
            else:
                leftover.append(w)

        # 不在新 projects 中的 widget → 删除
        for w in leftover:
            try:
                w.setParent(None)
                w.deleteLater()
            except RuntimeError:
                pass

        # 清掉 self._icons（旧的引用，下文重建）
        self._icons = {}

        # 清掉 workdirs 缓存中不在新列表的
        new_set = set(projects)
        for p in list(self._workdirs.keys()):
            if p not in new_set:
                self._workdirs.pop(p, None)

        # 按 projects 顺序构建新图标列表（复用 or 新建）
        for p in projects:
            if p in existing_map:
                icon = existing_map.pop(p)
            else:
                icon = _ProjectIcon(
                    p,
                    is_current=(p == self._current_project),
                    colors=self._colors or {"card_bg": QColor(33, 33, 38), "is_dark": True},
                    parent=self._list_container,
                )
                icon.clicked.connect(self._on_icon_clicked)
                icon.rightClicked.connect(self._on_icon_right_clicked)
            # 关键：复用时也要刷新 is_current，否则高亮残留
            icon.set_current(p == self._current_project)
            self._set_tooltip(icon, p, self._workdirs.get(p, ""))
            self._list_layout.addWidget(icon)
            self._icons[p] = icon

        # 末尾 stretch（让图标顶部对齐）
        self._list_layout.addStretch(1)

    def _update_current_highlight(self):
        for p, icon in self._icons.items():
            icon.set_current(p == self._current_project)

    def _on_icon_clicked(self, project: str):
        if project != self._current_project:
            self.projectClicked.emit(project)

    def _on_icon_right_clicked(self, project: str, global_pos):
        menu = QMenu(self)
        workdir = self._workdirs.get(project, "")
        open_action = menu.addAction("📂 打开项目根目录")
        open_action.setEnabled(bool(workdir and os.path.isdir(workdir)))
        copy_action = menu.addAction("📋 复制根目录路径")
        copy_action.setEnabled(bool(workdir))
        menu.addSeparator()
        refresh_action = menu.addAction("↻ 刷新列表")
        chosen = menu.exec_(global_pos)
        if chosen is None:
            return
        if chosen == open_action and workdir:
            self._open_in_explorer(workdir)
        elif chosen == copy_action and workdir:
            self._copy_to_clipboard(workdir)
        elif chosen == refresh_action:
            self._workdirs.clear()
            self._refresh()

    def _set_tooltip(self, icon: _ProjectIcon, project: str, workdir: str):
        tip = project
        if workdir:
            tip += f"\n{workdir}"
        icon.setToolTip(tip)

    def _open_in_explorer(self, path: str):
        try:
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            logger.warning(f"[project-side-rail] open folder failed: {e}")

    def _copy_to_clipboard(self, text: str):
        try:
            QApplication.clipboard().setText(text)
        except Exception as e:
            logger.warning(f"[project-side-rail] copy clipboard failed: {e}")


# ══════════════════════════════════════════════════════════
# 宽模式 — 嵌入主程序既有 ProjectSelectorCardContent
# ══════════════════════════════════════════════════════════


class ProjectSideRailFull(QWidget):
    """宽模式：嵌入主程序既有 ProjectSelectorCardContent（信号透明转发）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider: Optional[Callable[[], dict]] = None
        self._content = None  # ProjectSelectorCardContent
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        try:
            from app.widgets.cards.settings.project_selector_card import (
                ProjectSelectorCardContent,
            )

            self._content = ProjectSelectorCardContent(self)
            self._content.setObjectName("projectSideRailFullContent")
            layout.addWidget(self._content, 1)
        except Exception as e:
            logger.warning(f"[project-side-rail] 无法加载 ProjectSelectorCardContent: {e}")
            placeholder = QLabel("项目选择器加载失败\n（请确认主程序版本兼容）", self)
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setWordWrap(True)
            layout.addWidget(placeholder, 1)
            self._content = None

    def set_context_provider(self, provider: Callable[[], dict]):
        self._provider = provider
        self._refresh()

    def content(self):
        """返回底层 ProjectSelectorCardContent（供外部连接信号）"""
        return self._content

    def apply_theme(self, colors: dict):
        # ProjectSelectorCardContent 自身处理主题，无需额外操作
        return

    def _refresh(self):
        if self._content is None or self._provider is None:
            return
        try:
            ctx = self._provider()
        except Exception as e:
            logger.debug(f"[project-side-rail] full _refresh: {e}")
            return
        mw = ctx.get("main_widget")
        if mw is None:
            return

        current = getattr(mw, "_current_project", "") or ""
        projects: List[str] = []
        hm = getattr(mw, "history_manager", None)
        if hm is not None and hasattr(hm, "get_projects"):
            try:
                projects = list(hm.get_projects() or [])
            except Exception:
                pass
        if current and current not in projects:
            projects.insert(0, current)
        # 与主程序 set_projects_data 一致：不再次去重（get_projects 已返回不重复列表）

        # meta_map
        meta_map: Dict[str, Dict[str, int]] = {p: {"sessions": 0, "worktrees": 0} for p in projects}
        try:
            backend = getattr(mw, "backend", None)
            if backend is not None:
                ss_store = getattr(backend, "session_store", None)
                if ss_store is not None and hasattr(ss_store, "get_session_counts"):
                    counts = ss_store.get_session_counts() or {}
                    for p, c in counts.items():
                        if p in meta_map:
                            meta_map[p]["sessions"] = c
                mm = getattr(backend, "memory_manager", None)
                if mm is not None and hasattr(mm, "get_worktree_counts"):
                    wts = mm.get_worktree_counts() or {}
                    for p, c in wts.items():
                        if p in meta_map:
                            meta_map[p]["worktrees"] = c
        except Exception as e:
            logger.debug(f"[project-side-rail] meta_map build failed: {e}")

        # root_dir_map
        root_dir_map: Dict[str, str] = {}
        try:
            mm = getattr(getattr(mw, "backend", None), "memory_manager", None)
            for p in projects:
                wd = ""
                if mm is not None and hasattr(mm, "get_working_directory"):
                    wd = mm.get_working_directory(p) or ""
                if not wd:
                    wd = getattr(mw, "_current_workdir", {}).get(p, "")
                if wd:
                    root_dir_map[p] = wd
        except Exception:
            pass

        try:
            self._content.set_projects_data(projects, current, meta_map, root_dir_map)
        except Exception as e:
            logger.debug(f"[project-side-rail] set_projects_data failed: {e}")


# ══════════════════════════════════════════════════════════
# 主控件 — 响应式容器：窄模式 / 宽模式 自动切换
# ══════════════════════════════════════════════════════════


class ProjectSideRailCard(QWidget):
    """项目侧栏卡片 — 响应式 dock widget

    - 宽度 < _MODE_THRESHOLD（默认 160px）显示窄模式（icon 列）
    - 宽度 >= _MODE_THRESHOLD 显示宽模式（嵌入 ProjectSelectorCardContent）
    - 通过 dockSplitter 拖拽宽度实时切换
    - 最小宽度 40px（仅显示一个 icon 列）
    """

    _MODE_THRESHOLD = 160  # 模式切换阈值

    # 信号透传（窄模式点击 / 宽模式 ProjectSelectorCardContent 统一发出）
    projectSelected = pyqtSignal(str)
    newProjectCreated = pyqtSignal(str)
    archiveProject = pyqtSignal(str)
    exportProject = pyqtSignal(str)
    importProjectRequested = pyqtSignal()
    projectFileDropped = pyqtSignal(str)
    openFolderRequested = pyqtSignal(str, str)
    folderDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider: Optional[Callable[[], dict]] = None
        self._colors: dict = {}
        self._mode: str = ""
        self._setup_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self._on_tick)
        self._refresh_timer.start()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack)

        # Page 0: 窄模式
        self._narrow = ProjectSideRailNarrow(self)
        self._narrow.projectClicked.connect(lambda p: self._on_project_signal("projectSelected", p))
        self._stack.addWidget(self._narrow)

        # Page 1: 宽模式
        self._full = ProjectSideRailFull(self)
        self._stack.addWidget(self._full)

        # 桥接宽模式底层信号
        content = self._full.content()
        if content is not None:
            try:
                # 全部信号走 _on_project_signal：动态解析当前活跃 Tab 的 main_widget
                content.projectSelected.connect(lambda p: self._on_project_signal("projectSelected", p))
                content.newProjectCreated.connect(lambda p: self._on_project_signal("newProjectCreated", p))
                content.archiveProject.connect(lambda p: self._on_project_signal("archiveProject", p))
                content.exportProject.connect(lambda p: self._on_project_signal("exportProject", p))
                content.importProjectRequested.connect(lambda: self._on_project_signal("importProjectRequested"))
                content.projectFileDropped.connect(lambda p: self._on_project_signal("projectFileDropped", p))
                content.openFolderRequested.connect(lambda n, d: self._on_project_signal("openFolderRequested", n, d))
                content.folderDropped.connect(lambda p: self._on_project_signal("folderDropped", p))
            except Exception as e:
                logger.warning(f"[project-side-rail] 信号桥接失败: {e}")

        # 关键：最小宽度设为 40px，让 dockSplitter 可以拖到只显示 icon 列
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self._apply_mode("narrow")

    # ── 拉模型上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._provider = provider
        self._narrow.set_context_provider(provider)
        self._full.set_context_provider(provider)
        self._refresh()

    def _dispatch_to_active_main_widget(self, method_name: str, *args):
        """动态调用当前活跃 main_widget 的方法（多 Tab 隔离）

        与 main_widget._build_ui_context 的动态解析一致：每次调用
        provider() 都返回当前活跃 Tab 的 main_widget，避免绑定到固定实例。
        """
        if self._provider is None:
            return False
        try:
            ctx = self._provider()
        except Exception as e:
            logger.debug(f"[project-side-rail] provider() failed: {e}")
            return False
        mw = ctx.get("main_widget")
        if mw is None:
            return False
        handler = getattr(mw, method_name, None)
        if handler is None:
            logger.debug(f"[project-side-rail] main_widget has no method {method_name}")
            return False
        try:
            handler(*args)
            return True
        except Exception as e:
            logger.debug(f"[project-side-rail] dispatch {method_name} failed: {e}")
            return False

    def _current_project(self) -> str:
        """从 ctx 读取当前活跃 Tab 的项目名"""
        if self._provider is None:
            return ""
        try:
            ctx = self._provider()
            mw = ctx.get("main_widget")
            return getattr(mw, "_current_project", "") or ""
        except Exception:
            return ""

    def _on_project_signal(self, signal_name: str, *args):
        """统一信号处理：派发到当前活跃 main_widget 并发出对外信号"""
        method_map = {
            "projectSelected": "_on_project_selected",
            "newProjectCreated": "_on_new_project_created",
            "archiveProject": "_on_archive_project",
            "exportProject": "_on_export_project",
            "importProjectRequested": "_on_import_project",
            "projectFileDropped": "_on_project_file_dropped",
            "openFolderRequested": "_on_project_folder",
            "folderDropped": "_on_project_folder_dropped",
        }
        method = method_map.get(signal_name)
        if method:
            self._dispatch_to_active_main_widget(method, *args)
        sig = getattr(self, signal_name, None)
        if sig is not None:
            try:
                sig.emit(*args)
            except Exception:
                pass

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()

    def _on_tick(self):
        """5s 周期同步：当前项目高亮（窄 + 宽）+ 项目列表变化

        修复原 bug：
        - 仅刷新窄模式 → 宽模式 ProjectSelectorCardContent 不会更新当前项目高亮
        - 项目列表变化时也不会重建宽模式的内容
        """
        if self._provider is None:
            return
        try:
            ctx = self._provider()
        except Exception:
            return
        mw = ctx.get("main_widget")
        if mw is None:
            return
        current = getattr(mw, "_current_project", "") or ""

        # 窄模式：当前项目变化时刷新（图标重建 + 高亮更新）
        if current != self._narrow._current_project or self._projects_signature_changed(mw):
            self._narrow._refresh()

        # 宽模式：当前项目变化 / 项目列表变化时刷新内容
        if self._mode == "full" or self._full._content is not None:
            self._maybe_refresh_full(current, mw)

    def _projects_signature_changed(self, mw) -> bool:
        """项目列表是否变化（用于触发窄模式重建）"""
        try:
            hm = getattr(mw, "history_manager", None)
            if hm is None or not hasattr(hm, "get_projects"):
                return False
            current = list(hm.get_projects() or [])
            existing = set(self._narrow._icons.keys())
            return set(current) != existing
        except Exception:
            return False

    def _maybe_refresh_full(self, current: str, mw):
        """宽模式刷新：set_projects_data 会被 ProjectSelectorCardContent 用于更新当前项目高亮"""
        if self._full._content is None:
            return
        # 用 ctx 项目名 与 wide._current_project 对比；不等则重灌数据
        content_current = getattr(self._full._content, "_current_project", "") or ""
        if content_current == current:
            # 即便 current 没变，也检查项目列表是否变了（增删）
            try:
                hm = getattr(mw, "history_manager", None)
                if hm is not None and hasattr(hm, "get_projects"):
                    listed = list(hm.get_projects() or [])
                    existing = set(getattr(self._full._content, "_projects", []) or [])
                    if set(listed) != existing:
                        self._full._refresh()
            except Exception:
                pass
            return
        self._full._refresh()

    # ── 主题 ──

    def _refresh(self):
        if self._provider is None:
            return
        try:
            ctx = self._provider()
        except Exception as e:
            logger.debug(f"[project-side-rail] _refresh: {e}")
            return
        try:
            self._colors = _make_colors_from_context(ctx)
        except Exception:
            self._colors = {}
        self._narrow.apply_theme(self._colors)
        self._full.apply_theme(self._colors)

    def _emit_project_selected(self, project: str):
        # 保留旧 API；推荐用 _on_project_signal("projectSelected", project)
        self._on_project_signal("projectSelected", project)

    # ── 响应式布局 ──

    def resizeEvent(self, event):
        super().resizeEvent(event)
        new_mode = "narrow" if self.width() < self._MODE_THRESHOLD else "full"
        if new_mode != self._mode:
            self._apply_mode(new_mode)

    def _apply_mode(self, mode: str):
        self._mode = mode
        if mode == "narrow":
            self._stack.setCurrentWidget(self._narrow)
        else:
            self._stack.setCurrentWidget(self._full)

    # ── 清理 ──

    def deleteLater(self):
        try:
            self._refresh_timer.stop()
        except Exception:
            pass
        super().deleteLater()
