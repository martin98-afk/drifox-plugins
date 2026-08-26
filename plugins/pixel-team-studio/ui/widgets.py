# -*- coding: utf-8 -*-
"""交互控件 — 成员格 / 智能体库 / 团队面板 / 垃圾桶（Qt 拖拽）

拖拽协议：
- MIME: application/x-pixel-agent
- 数据: JSON {"action": "add"|"remove", ...}
  - add:    {action, agent_name, run_id, team_label}
  - remove: {action, window_id}
"""

import json
from typing import Callable, Dict, List, Optional, Any

from PyQt5.QtCore import QMimeData, QPoint, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QDrag, QPainter
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .palette import make_palette, rgba
from .sprites import PixelSprite, state_cn

MIME_PIXEL_AGENT = "application/x-pixel-agent"


def _make_mime(data: dict) -> QMimeData:
    mime = QMimeData()
    mime.setData(MIME_PIXEL_AGENT, json.dumps(data, ensure_ascii=False).encode("utf-8"))
    return mime


def _parse_mime(mime: Optional[QMimeData]) -> Optional[dict]:
    if mime is None or not mime.hasFormat(MIME_PIXEL_AGENT):
        return None
    try:
        return json.loads(bytes(mime.data(MIME_PIXEL_AGENT)).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ── 拖拽源基类 ───────────────────────────────────────────


class _DragSource(QFrame):
    """可拖拽的像素格基类（子类提供 _drag_data() 与 _drag_pixmap()）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start: Optional[QPoint] = None

    def _drag_data(self) -> dict:
        raise NotImplementedError

    def _drag_pixmap(self):
        """拖拽跟随的像素小人缩影（子类可覆写；默认无）"""
        sprite = getattr(self, "_sprite", None)
        if sprite is None:
            return None
        pm = sprite.grab()
        return pm

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is None or not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
            return
        data = self._drag_data()
        if not data:
            return
        drag = QDrag(self)
        drag.setMimeData(_make_mime(data))
        pm = self._drag_pixmap()
        if pm is not None:
            drag.setPixmap(pm)
            drag.setHotSpot(QPoint(pm.width() // 2, pm.height() // 2))
        result = drag.exec_(Qt.CopyAction | Qt.MoveAction)
        self._drag_start = None
        self._on_drag_finished(result)

    def _on_drag_finished(self, result):
        """拖拽结束后回调（子类可覆写）"""
        pass


# ── 智能体库格（拖拽源：add）─────────────────────────────


class AgentTile(_DragSource):
    """智能体库中的角色格：像素小人 + 角色名，仅拖拽添加成员（不支持点击）"""

    def __init__(self, agent_name: str, description: str = "", palette: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.agent_name = agent_name
        self._description = description
        self._palette = palette or make_palette(None)
        self.setFixedSize(84, 108)
        self.setCursor(Qt.PointingHandCursor)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4)
        v.setSpacing(2)
        self._sprite = PixelSprite(self.agent_name, self)
        v.addWidget(self._sprite, 0, Qt.AlignHCenter)
        name_label = QLabel(self.agent_name, self)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(
            f"color: {rgba(self._palette['text'])}; font-size: 12px; background: transparent;"
        )
        v.addWidget(name_label)
        if self._description:
            self.setToolTip(self._description)
        self._apply_base_style()

    def _apply_base_style(self):
        pal = self._palette
        self.setStyleSheet(
            f"AgentTile {{ border: 1px solid {rgba(pal['border'])}; border-radius: 10px; "
            f"background: {rgba(pal['card_bg'])}; }}"
            f"AgentTile:hover {{ border: 1px solid {rgba(pal['accent'], 180)}; "
            f"background: {rgba(pal['hover_bg'])}; }}"
        )
        self.update()

    def apply_palette(self, palette: dict):
        self._palette = palette
        for label in self.findChildren(QLabel):
            label.setStyleSheet(
                f"color: {rgba(palette['text'])}; font-size: 12px; background: transparent;"
            )
        self._apply_base_style()

    def _drag_data(self) -> dict:
        # 目标团队由 drop 到的 TeamPanel 自身决定（dropEvent 注入自身 run_id）
        return {"action": "add", "agent_name": self.agent_name}

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)


# ── 团队成员格（拖拽源：remove）──────────────────────────


class MemberTile(_DragSource):
    """团队成员格：像素小人 + 角色名 + 状态文字，拖出面板或拖到垃圾桶=移除"""

    drag_out_requested = pyqtSignal(str)  # window_id（拖出面板释放）

    def __init__(self, member: dict, palette: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.member = member
        self.window_id = member.get("window_id", "")
        self.agent_name = member.get("agent_name", "?")
        self._palette = palette or make_palette(None)
        self._state = "idle"
        self._task_count = 0
        self._panel_ref = None  # 所属 TeamPanel（拖出判定用）
        self.setFixedSize(84, 118)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4)
        v.setSpacing(2)
        self._sprite = PixelSprite(self.agent_name, self, salt=self.window_id)
        v.addWidget(self._sprite, 0, Qt.AlignHCenter)
        self._name_label = QLabel(self.agent_name, self)
        self._name_label.setAlignment(Qt.AlignCenter)
        self._state_label = QLabel(state_cn(self._state), self)
        self._state_label.setAlignment(Qt.AlignCenter)
        for lbl in (self._name_label, self._state_label):
            v.addWidget(lbl)
        self._apply_base_style()
        self.apply_state(self._state, 0)

    def _apply_base_style(self):
        pal = self._palette
        self.setStyleSheet(
            f"MemberTile {{ border: 1px solid {rgba(pal['border'])}; border-radius: 10px; "
            f"background: {rgba(pal['card_bg'])}; }}"
            f"MemberTile:hover {{ border: 1px solid {rgba(pal['danger'], 150)}; "
            f"background: {rgba(pal['hover_bg'])}; }}"
        )
        self.update()

    def apply_palette(self, palette: dict):
        self._palette = palette
        self._refresh_labels()
        self._apply_base_style()

    def _refresh_labels(self):
        state_color = {
            "streaming": "#50E3C2",
            "thinking": "#62A0EA",
            "question": "#FFC107",
            "error": "#FF6B6B",
            "busy": "#FFA726",
            "idle": "#50C878",
        }.get(self._state, "#AAAAAA")
        self._name_label.setStyleSheet(
            f"color: {rgba(self._palette['text'])}; font-size: 12px; background: transparent;"
        )
        self._state_label.setStyleSheet(
            f"color: {state_color}; font-size: 11px; background: transparent;"
        )

    def apply_state(self, state: str, task_count: int, context_percent: float = 0.0):
        """刷新状态（卡片轮询调用）"""
        self._state = state or "idle"
        self._task_count = task_count
        self._sprite.set_state(self._state)
        self._sprite.set_context(context_percent)
        self._state_label.setText(state_cn(self._state))
        self._refresh_labels()
        tip = (
            f"角色: {self.agent_name}\n"
            f"状态: {state_cn(self._state)}\n"
            f"窗口: {self.window_id}\n"
            f"任务: {task_count}\n"
            "拖出面板或拖到垃圾桶可移除（窗口保留）"
        )
        self.setToolTip(tip)

    def _on_drag_finished(self, result):
        """拖拽结束：释放到无效区域（未 drop 到任何接受点）且鼠标在团队面板外 → 移除"""
        from PyQt5.QtCore import Qt as _Qt

        if result != _Qt.IgnoreAction:
            return  # 已 drop 到垃圾桶等有效目标，由目标处理
        panel = self._panel_ref
        if panel is None:
            return
        try:
            from PyQt5.QtGui import QCursor

            pos = panel.mapFromGlobal(QCursor.pos())
            if not panel.rect().contains(pos):
                self.drag_out_requested.emit(self.window_id)
        except Exception:  # noqa: BLE001
            pass

    def advance_bounce(self):
        self._sprite.advance_bounce()

    def _drag_data(self) -> dict:
        return {"action": "remove", "window_id": self.window_id}

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)


# ── 垃圾桶（拖放目标：remove）────────────────────────────


class TrashZone(QFrame):
    """垃圾桶：接受 remove 拖放，成员拖入即离开团队"""

    def __init__(self, palette: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._palette = palette or make_palette(None)
        self.setAcceptDrops(True)
        self.setFixedSize(110, 90)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self._label = QLabel("🗑 移除成员\n拖入后离开团队\n(窗口保留)", self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        lay.addWidget(self._label)
        self._apply_style(False)

    def _apply_style(self, hover: bool):
        border = rgba(self._palette["danger"], 200 if hover else 90)
        bg = rgba(self._palette["danger"], 26 if hover else 10)
        self.setStyleSheet(
            f"TrashZone {{ border: 2px dashed {border}; border-radius: 10px; background: {bg}; }}"
            f"TrashZone QLabel {{ color: {rgba(self._palette['danger'], 220)}; font-size: 11px; background: transparent; }}"
        )

    def apply_palette(self, palette: dict):
        self._palette = palette
        self._apply_style(False)

    def dragEnterEvent(self, event):
        data = _parse_mime(event.mimeData())
        if data and data.get("action") == "remove":
            event.acceptProposedAction()
            self._apply_style(True)

    def dragLeaveEvent(self, event):
        self._apply_style(False)

    def dropEvent(self, event):
        self._apply_style(False)
        data = _parse_mime(event.mimeData())
        if not data or data.get("action") != "remove":
            event.ignore()
            return
        event.acceptProposedAction()
        # 延迟执行，避免拖拽循环内调用主窗口方法（拖拽源仍持有鼠标）
        from PyQt5.QtCore import QTimer

        wid = data.get("window_id", "")
        QTimer.singleShot(0, lambda: self._on_remove(wid))

    _on_remove: Any = lambda self, wid: None


# ── 团队面板（拖放目标：add，团队自身绑定 run_id）────────


class TeamPanel(QFrame):
    """单个团队面板：标题（⭐ 团队名 + 成员数）+ 成员像素格横向排布

    接受 add 拖放——drop 到本面板即添加到本团队（run_id 由面板自身持有）。
    """

    def __init__(self, palette: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._palette = palette or make_palette(None)
        self._run_id = ""
        self._label = ""
        self.setAcceptDrops(True)
        self.setMinimumWidth(280)
        self.setMinimumHeight(150)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(10, 8, 10, 8)
        self._lay.setSpacing(6)

        self._title_label = QLabel("团队", self)
        self._title_label.setStyleSheet("font-weight: bold; background: transparent;")
        self._lay.addWidget(self._title_label)

        # 成员区（横向排布）
        self._members_host = QWidget(self)
        self._members_host.setStyleSheet("background: transparent;")
        self._members_lay = QHBoxLayout(self._members_host)
        self._members_lay.setContentsMargins(0, 0, 0, 0)
        self._members_lay.setSpacing(8)
        self._members_lay.addStretch(1)
        self._lay.addWidget(self._members_host, 1)

        # 空团队提示（有成员时隐藏）
        self._empty_label = QLabel("拖入智能体小人\n添加成员", self._members_host)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._members_lay.insertWidget(0, self._empty_label)

        self._tiles: Dict[str, MemberTile] = {}
        self._apply_style()

    def set_team(self, run_id: str, label: str, is_active: bool = False, member_count: int = 0):
        """绑定团队信息并刷新标题"""
        self._run_id = run_id or ""
        self._label = label or (run_id[:8] if run_id else "未分组")
        prefix = "⭐ " if is_active else ""
        self._title_label.setText(f"{prefix}{self._label} ({member_count})")

    def _apply_style(self):
        pal = self._palette
        border = rgba(pal["accent"], 110)
        self.setStyleSheet(
            f"TeamPanel {{ border: 1px solid {border}; border-radius: 12px; "
            f"background: {rgba(pal['card_bg'])}; }}"
            f"TeamPanel QLabel {{ background: transparent; }}"
        )
        self.update()

    def apply_palette(self, palette: dict):
        self._palette = palette
        self._apply_style()
        for tile in self._tiles.values():
            tile.apply_palette(palette)

    # ── 成员 diff 刷新 ──

    def sync_members(self, members: List[dict]):
        """按 window_id diff：新增/移除/更新 tile（保持动画连续）"""
        current_ids = set(self._tiles.keys())
        new_ids = {m.get("window_id", "") for m in members if m.get("window_id")}
        for wid in current_ids - new_ids:
            tile = self._tiles.pop(wid)
            self._members_lay.removeWidget(tile)
            tile.deleteLater()
        for m in members:
            wid = m.get("window_id", "")
            if not wid:
                continue
            tile = self._tiles.get(wid)
            if tile is None:
                tile = MemberTile(m, self._palette)
                tile._panel_ref = self
                tile.drag_out_requested.connect(lambda w: self._on_remove(w))
                self._tiles[wid] = tile
                self._members_lay.insertWidget(self._members_lay.count() - 1, tile)
            else:
                tile.member = m
        self._empty_label.setVisible(not self._tiles)

    def update_tile_state(self, window_id: str, state: str, task_count: int, context_percent: float):
        tile = self._tiles.get(window_id)
        if tile is not None:
            tile.apply_state(state, task_count, context_percent)

    def clear(self):
        for wid in list(self._tiles.keys()):
            tile = self._tiles.pop(wid)
            self._members_lay.removeWidget(tile)
            tile.deleteLater()
        self._empty_label.setVisible(True)

    # ── 拖放（add → 本团队）──

    def dragEnterEvent(self, event):
        data = _parse_mime(event.mimeData())
        if data and data.get("action") == "add":
            event.acceptProposedAction()
            self.setStyleSheet(
                f"TeamPanel {{ border: 2px dashed {rgba(self._palette['success'], 200)}; "
                f"border-radius: 12px; background: {rgba(self._palette['success'], 30)}; }}"
            )

    def dragLeaveEvent(self, event):
        self._apply_style()

    def dropEvent(self, event):
        self._apply_style()
        data = _parse_mime(event.mimeData())
        if not data or data.get("action") != "add":
            event.ignore()
            return
        event.acceptProposedAction()
        from PyQt5.QtCore import QTimer

        agent = data.get("agent_name", "")
        QTimer.singleShot(0, lambda: self._on_add(agent, self._run_id, self._label))

    _on_add: Any = lambda self, a, r, l: None
