# -*- coding: utf-8 -*-
"""交互控件 — 成员格 / 智能体库 / 团队面板 / 垃圾桶 / 流式布局（Qt 拖拽）

拖拽协议：
- MIME: application/x-pixel-agent
- 数据: JSON {"action": "add"|"remove", ...}
  - add:    {action, agent_name, run_id, team_label}
  - remove: {action, window_id}

操作（v0.2.0）：
- 成员格：双击 → 切到该成员窗口 tab；右键 → 菜单（切窗口 / 移除）；
  拖出团队面板释放或拖到垃圾桶 → 移除成员（窗口保留）
- 智能体库格：双击 → 加入当前激活团队；拖拽 → 加入指定团队
"""

import json
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QMimeData, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QPushButton,
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


def parse_drag_mime(mime: Optional[QMimeData]) -> Optional[dict]:
    """解析拖拽 MIME 数据（公开给卡片层空白区 drop 使用）"""
    if mime is None or not mime.hasFormat(MIME_PIXEL_AGENT):
        return None
    try:
        return json.loads(bytes(mime.data(MIME_PIXEL_AGENT)).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ── 流式布局（子项超宽自动换行）──────────────────────────


class FlowLayout(QLayout):
    """流式布局：成员格按行排列，卡片宽度变化时自动换行重排"""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 10):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items: List[Any] = []

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def insertWidget(self, index: int, w: QWidget):
        """在指定位置插入控件（-1 表示尾部）"""
        from PyQt5.QtWidgets import QWidgetItem

        self.addChildWidget(w)
        if index < 0:
            index = len(self._items)
        self._items.insert(index, QWidgetItem(w))
        self.update()

    def removeWidget(self, w: QWidget):
        for i, item in enumerate(self._items):
            if item.widget() is w:
                self.takeAt(i)
                w.setParent(None)
                return

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            wid = item.widget()
            if wid is not None and not wid.isVisibleTo(self.parentWidget()):
                continue
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            wid = item.widget()
            if wid is not None and not wid.isVisibleTo(self.parentWidget()):
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom() + 1


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
        return sprite.grab()

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
    """智能体库中的角色格：像素小人 + 角色名

    双击 → activated(agent_name)（加入激活团队）；拖拽 → 加入指定团队。
    """

    activated = pyqtSignal(str)

    def __init__(self, agent_name: str, description: str = "", palette: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.agent_name = agent_name
        self._description = description
        self._palette = palette or make_palette(None)
        self.setFixedSize(88, 112)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{agent_name}\n{description}\n\n双击加入激活团队 · 拖拽加入指定团队")
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 5)
        v.setSpacing(2)
        self._sprite = PixelSprite(self.agent_name, self)
        v.addWidget(self._sprite, 0, Qt.AlignHCenter)
        name_label = QLabel(self.agent_name, self)
        name_label.setObjectName("agentName")
        name_label.setAlignment(Qt.AlignCenter)
        v.addWidget(name_label)
        self._apply_base_style()

    def _apply_base_style(self):
        pal = self._palette
        fc = pal.get("font_css", "")
        self.setStyleSheet(
            f"AgentTile {{ border: 1px solid {rgba(pal['border'])}; border-radius: 10px; "
            f"background: {rgba(pal['card_bg'])}; {fc} }}"
            f"AgentTile:hover {{ border: 1px solid {rgba(pal['accent'], 190)}; "
            f"background: {rgba(pal['accent'], 26)}; }}"
            f"QLabel#agentName {{ color: {rgba(pal['text'])}; font-size: 12px; "
            f"font-weight: 600; background: transparent; }}"
        )
        self.update()

    def apply_palette(self, palette: dict):
        self._palette = palette
        self._apply_base_style()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.agent_name)
        super().mouseDoubleClickEvent(event)

    def _drag_data(self) -> dict:
        # 目标团队由 drop 到的 TeamPanel 自身决定（dropEvent 注入自身 run_id）
        return {"action": "add", "agent_name": self.agent_name}


# ── 团队成员格（拖拽源：remove）──────────────────────────


class MemberTile(_DragSource):
    """团队成员格：像素小人 + 角色名 + 状态 + 任务徽章

    双击 → activated(window_id)（切到该成员窗口）；
    右键 → 菜单（切到窗口 / 移除成员）；
    拖出面板释放或拖到垃圾桶 → drag_out_requested（移除，窗口保留）。
    """

    activated = pyqtSignal(str)  # window_id（双击切窗口）
    drag_out_requested = pyqtSignal(str)  # window_id（拖出面板释放）
    message_requested = pyqtSignal(str, str)  # (window_id, text)（右键发消息）

    def __init__(self, member: dict, palette: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.member = member
        self.window_id = member.get("window_id", "")
        self.agent_name = member.get("agent_name", "?")
        self._palette = palette or make_palette(None)
        self._state = "idle"
        self._task_count = 0
        self._panel_ref = None  # 所属 TeamPanel（拖出判定用）
        self.setFixedSize(88, 122)
        self.setCursor(Qt.PointingHandCursor)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 5, 6, 4)
        v.setSpacing(1)
        self._sprite = PixelSprite(self.agent_name, self, salt=self.window_id)
        v.addWidget(self._sprite, 0, Qt.AlignHCenter)
        self._name_label = QLabel(self.agent_name, self)
        self._name_label.setObjectName("memberName")
        self._name_label.setAlignment(Qt.AlignCenter)
        self._state_label = QLabel("", self)
        self._state_label.setObjectName("memberState")
        self._state_label.setAlignment(Qt.AlignCenter)
        v.addWidget(self._name_label)
        v.addWidget(self._state_label)
        # 快捷发消息按钮（常显右上角，点击弹输入框）
        self._msg_btn = QPushButton("✉", self)
        self._msg_btn.setObjectName("msgBtn")
        self._msg_btn.setFixedSize(24, 24)
        self._msg_btn.setCursor(Qt.PointingHandCursor)
        self._msg_btn.setToolTip("给这个成员发消息（不切窗口）")
        self._msg_btn.clicked.connect(self._prompt_message)
        self._apply_base_style()
        self.apply_state(self._state, 0)

    def resizeEvent(self, event):
        """✉ 按钮钉在右上角"""
        super().resizeEvent(event)
        btn = getattr(self, "_msg_btn", None)
        if btn is not None:
            btn.move(self.width() - btn.width() - 4, 4)

    def _apply_base_style(self):
        pal = self._palette
        fc = pal.get("font_css", "")
        self.setStyleSheet(
            f"MemberTile {{ border: 1px solid {rgba(pal['border'])}; border-radius: 10px; "
            f"background: {rgba(pal['card_bg'])}; {fc} }}"
            f"MemberTile:hover {{ border: 1px solid {rgba(pal['accent'], 170)}; "
            f"background: {rgba(pal['hover_bg'])}; }}"
            f"QLabel#memberName {{ color: {rgba(pal['text'])}; font-size: 12px; "
            f"font-weight: 600; background: transparent; }}"
            f"QLabel#memberState {{ color: {rgba(pal['text_secondary'])}; font-size: 11px; "
            f"background: transparent; }}"
            f"QPushButton#msgBtn {{ border: none; border-radius: 12px; "
            f"background: transparent; color: {rgba(pal['accent'], 140)}; "
            f"font-size: 13px; }}"
            f"MemberTile:hover QPushButton#msgBtn {{ background: {rgba(pal['accent'], 46)}; "
            f"color: {rgba(pal['accent'])}; }}"
        )
        self.update()

    def apply_palette(self, palette: dict):
        self._palette = palette
        self._refresh_labels()
        self._apply_base_style()

    def _state_color_hex(self) -> str:
        """状态色：深浅底两套，高饱和高区分度"""
        dark = self._palette["is_dark"]
        table = {
            # (深底色, 浅底色)
            "streaming": ("#2DD4BF", "#0D9488"),  # 青绿
            "thinking": ("#5CA9FF", "#1D4ED8"),  # 亮蓝
            "question": ("#FFC53D", "#B45309"),  # 琥珀
            "error": ("#FF7A70", "#DC2626"),  # 红
            "busy": ("#FF9838", "#EA580C"),  # 橙
            "idle": ("#4ADE80", "#15803D"),  # 绿
        }
        pair = table.get(self._state, ("#C8CEDA", "#475569"))
        return pair[0] if dark else pair[1]

    def _refresh_labels(self):
        state_txt = state_cn(self._state)
        if self._task_count > 0:
            state_txt = f"{state_txt} · {self._task_count}任务"
        self._state_label.setText(state_txt)
        self._state_label.setStyleSheet(
            f"QLabel#memberState {{ color: {self._state_color_hex()}; font-size: 11px; "
            f"font-weight: 600; background: transparent; "
            f"{self._palette.get('font_css', '')} }}"
        )

    def apply_state(self, state: str, task_count: int, context_percent: float = 0.0):
        """刷新状态（卡片轮询调用）"""
        self._state = state or "idle"
        self._task_count = task_count
        self._sprite.set_state(self._state)
        self._sprite.set_context(context_percent)
        self._refresh_labels()
        self.setToolTip(
            f"角色: {self.agent_name}\n"
            f"状态: {state_cn(self._state)}\n"
            f"未完成任务: {task_count}\n"
            f"窗口: {self.window_id}\n\n"
            "双击切到该窗口 · 点✉直接发消息\n拖出面板或拖到垃圾桶可移除（同时关闭其窗口）"
        )

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.window_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {rgba(self._palette['panel_bg'])}; "
            f"color: {rgba(self._palette['text'])}; border-radius: 8px; padding: 4px; }}"
            f"QMenu::item {{ padding: 5px 22px 5px 14px; border-radius: 6px; }}"
            f"QMenu::item:selected {{ background: {rgba(self._palette['accent'], 60)}; }}"
        )
        act_open = menu.addAction("切到该成员窗口")
        act_msg = menu.addAction("✉ 给这个成员发消息…")
        menu.addSeparator()
        act_remove = menu.addAction("移除成员（窗口保留）")
        chosen = menu.exec_(event.globalPos())
        if chosen is act_open:
            self.activated.emit(self.window_id)
        elif chosen is act_msg:
            self._prompt_message()
        elif chosen is act_remove:
            self.drag_out_requested.emit(self.window_id)

    def _prompt_message(self):
        """弹多行输入框，确认后发射 message_requested(window_id, text)"""
        from qfluentwidgets import MessageBoxBase, SubtitleLabel, PlainTextEdit, BodyLabel

        dlg = MessageBoxBase(self.window())
        title = SubtitleLabel(f"给 {self.agent_name} 发消息", dlg)
        dlg.viewLayout.addWidget(title)
        hint = BodyLabel("消息将直接发送到该成员会话（不切换窗口）", dlg)
        dlg.viewLayout.addWidget(hint)
        editor = PlainTextEdit(dlg)
        editor.setPlaceholderText("输入要发给该成员的消息…")
        editor.setFixedHeight(120)
        editor.setStyleSheet(
            f"PlainTextEdit {{ background: {rgba(self._palette['card_bg'])}; "
            f"color: {rgba(self._palette['text'])}; border: 1px solid {rgba(self._palette['border'])}; "
            f"border-radius: 8px; padding: 6px; {self._palette.get('font_css', '')} }}"
        )
        dlg.viewLayout.addWidget(editor)
        dlg.yesButton.setText("发送")
        dlg.cancelButton.setText("取消")
        editor.setFocus()
        if dlg.exec():
            text = editor.toPlainText().strip()
            if text:
                self.message_requested.emit(self.window_id, text)

    def _on_drag_finished(self, result):
        """拖拽结束：释放到无效区域（未 drop 到任何接受点）且鼠标在团队面板外 → 移除"""
        if result != Qt.IgnoreAction:
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


# ── 垃圾桶（拖放目标：remove）────────────────────────────


class TrashZone(QFrame):
    """垃圾桶：接受 remove 拖放，成员拖入即离开团队"""

    def __init__(self, palette: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._palette = palette or make_palette(None)
        self.setAcceptDrops(True)
        self.setFixedSize(120, 96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self._label = QLabel("🗑 移除成员\n拖入后离开团队\n（同时关闭其窗口）", self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        lay.addWidget(self._label)
        self._apply_style(False)

    def _apply_style(self, hover: bool):
        border = rgba(self._palette["danger"], 200 if hover else 90)
        bg = rgba(self._palette["danger"], 26 if hover else 10)
        self.setStyleSheet(
            f"TrashZone {{ border: 2px dashed {border}; border-radius: 10px; "
            f"background: {bg}; {self._palette.get('font_css', '')} }}"
            f"TrashZone QLabel {{ color: {rgba(self._palette['danger'], 220)}; font-size: 11px; "
            f"background: transparent; }}"
        )

    def apply_palette(self, palette: dict):
        self._palette = palette
        self._apply_style(False)

    def dragEnterEvent(self, event):
        data = parse_drag_mime(event.mimeData())
        if data and data.get("action") == "remove":
            event.acceptProposedAction()
            self._apply_style(True)

    def dragLeaveEvent(self, event):
        self._apply_style(False)

    def dropEvent(self, event):
        self._apply_style(False)
        data = parse_drag_mime(event.mimeData())
        if not data or data.get("action") != "remove":
            event.ignore()
            return
        event.acceptProposedAction()
        # 延迟执行，避免拖拽循环内调用主窗口方法（拖拽源仍持有鼠标）
        from PyQt5.QtCore import QTimer

        wid = data.get("window_id", "")
        QTimer.singleShot(0, lambda: self._on_remove(wid))

    _on_remove: Any = lambda self, wid: None  # noqa: E731


# ── 团队面板（拖放目标：add，团队自身绑定 run_id）────────


class TeamPanel(QFrame):
    """单个团队卡片（竖排列表中一行）：标题行 + 成员流式网格

    标题行：激活标(⭐/◇) + 团队名 + 成员数徽章 + 忙碌统计徽章 + run_id 缩写
    + 折叠箭头。
    成员区 FlowLayout 自动换行；接受 add 拖放——drop 到本卡片即加入本团队；
    右键标题行 → 团队级操作（广播消息 / 解散团队）。
    """

    broadcast_requested = pyqtSignal(str, str)  # (run_id, team_label)
    dissolve_requested = pyqtSignal(str, str)  # (run_id, team_label)

    def __init__(self, palette: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._palette = palette or make_palette(None)
        self._run_id = ""
        self._label = ""
        self._is_active = False
        self._busy_count = 0
        self._member_count = 0
        self._collapsed = False
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # ── 标题行 ──
        head = QWidget(self)
        head.setStyleSheet("background: transparent;")
        hly = QHBoxLayout(head)
        hly.setContentsMargins(0, 0, 0, 0)
        hly.setSpacing(8)

        self._mark_label = QLabel("◇", head)
        self._mark_label.setObjectName("teamMark")
        self._mark_label.setFixedWidth(18)
        hly.addWidget(self._mark_label)

        self._title_label = QLabel("团队", head)
        self._title_label.setObjectName("teamTitle")
        hly.addWidget(self._title_label)

        self._count_badge = QLabel("0", head)
        self._count_badge.setObjectName("teamBadge")
        hly.addWidget(self._count_badge)
        hly.addStretch(1)

        self._busy_badge = QLabel("", head)
        self._busy_badge.setObjectName("teamBadge")
        self._busy_badge.setVisible(False)
        hly.addWidget(self._busy_badge)

        self._run_label = QLabel("", head)
        self._run_label.setObjectName("teamRun")
        hly.addWidget(self._run_label)

        self._fold_btn = QPushButton("▾", head)
        self._fold_btn.setObjectName("foldBtn")
        self._fold_btn.setFixedSize(22, 22)
        self._fold_btn.setCursor(Qt.PointingHandCursor)
        self._fold_btn.setToolTip("折叠/展开成员区")
        self._fold_btn.clicked.connect(self.toggle_collapsed)
        hly.addWidget(self._fold_btn)

        lay.addWidget(head)

        # ── 成员区（流式换行）──
        self._members_host = QWidget(self)
        self._members_host.setStyleSheet("background: transparent;")
        self._flow = FlowLayout(self._members_host, margin=0, spacing=8)
        self._members_host.setLayout(self._flow)
        lay.addWidget(self._members_host, 1)

        # 空团队提示（有成员时隐藏；FlowLayout 排版时自动跳过隐藏项）
        self._empty_label = QLabel("拖入智能体小人添加成员", self._members_host)
        self._empty_label.setObjectName("teamEmpty")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._flow.insertWidget(0, self._empty_label)

        self._tiles: Dict[str, MemberTile] = {}
        self._apply_style()

    # ── 数据绑定 ──

    def set_team(self, run_id: str, label: str, is_active: bool = False, member_count: int = 0):
        """绑定团队信息并刷新标题"""
        self._run_id = run_id or ""
        self._label = label or (run_id[:8] if run_id else "未分组")
        self._is_active = bool(is_active)
        self._member_count = member_count
        self._refresh_head()

    def set_busy_count(self, busy: int):
        if busy != self._busy_count:
            self._busy_count = busy
            self._refresh_head()

    def _refresh_head(self):
        self._mark_label.setText("⭐" if self._is_active else "◇")
        self._title_label.setText(self._label)
        self._count_badge.setText(f"{self._member_count} 成员")
        if self._busy_count > 0:
            self._busy_badge.setText(f"⚡ {self._busy_count} 忙碌")
            self._busy_badge.setObjectName("teamBusyBadge")
            self._busy_badge.setVisible(True)
        else:
            self._busy_badge.setVisible(False)
        self._run_label.setText(f"#{self._run_id[:8]}" if self._run_id else "")
        self._apply_style()

    # ── 样式 ──

    def _panel_qss(self, border: str, bg: str, left_bar: str = "") -> str:
        """面板整表 QSS 构建器（_apply_style 与拖拽 hover 共用，避免子控件规则丢失）"""
        pal = self._palette
        fc = pal.get("font_css", "")
        bar = f" border-left: 3px solid {left_bar};" if left_bar else ""
        return (
            f"TeamPanel {{ border: 1px solid {border};{bar} "
            f"border-radius: 12px; background: {bg}; {fc} }}"
            f"QLabel {{ background: transparent; }}"
            f"QLabel#teamTitle {{ color: {rgba(pal['text'])}; font-size: 13px; "
            f"font-weight: 700; }}"
            f"QLabel#teamMark {{ color: {rgba(pal['accent'])}; font-size: 14px; }}"
            f"QLabel#teamRun {{ color: {rgba(pal['text_secondary'])}; font-size: 10px; }}"
            f"QLabel#teamEmpty {{ color: {rgba(pal['text_secondary'])}; font-size: 11px; }}"
            f"QLabel#teamBadge {{ color: {rgba(pal['text_secondary'])}; font-size: 10px; "
            f"background: {rgba(pal['badge_bg'])}; border-radius: 8px; padding: 2px 8px; }}"
            f"QLabel#teamBusyBadge {{ color: {rgba(pal['warning'])}; font-size: 10px; "
            f"font-weight: 600; background: {rgba(pal['warning'], 36)}; "
            f"border-radius: 8px; padding: 2px 8px; }}"
            f"QPushButton#foldBtn {{ border: none; border-radius: 6px; "
            f"background: transparent; color: {rgba(pal['text_secondary'])}; "
            f"font-size: 12px; }}"
            f"QPushButton#foldBtn:hover {{ background: {rgba(pal['hover_bg'])}; "
            f"color: {rgba(pal['text'])}; }}"
        )

    def _apply_style(self):
        pal = self._palette
        if self._is_active:
            border = rgba(pal["accent"], 170)
            bg = rgba(pal["card_bg_active"])
            left = rgba(pal["accent"])  # 激活团队左侧竖条强化辨识
        else:
            border = rgba(pal["border"])
            bg = rgba(pal["card_bg"])
            left = ""
        self.setStyleSheet(self._panel_qss(border, bg, left))
        self.update()

    # ── 折叠/展开 ──

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._members_host.setVisible(not collapsed)
        self._fold_btn.setText("▸" if collapsed else "▾")
        self._fold_btn.setToolTip("展开成员区" if collapsed else "折叠成员区")

    def contextMenuEvent(self, event):
        """标题区右键：团队级操作（广播消息 / 解散团队）"""
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {rgba(self._palette['panel_bg'])}; "
            f"color: {rgba(self._palette['text'])}; border-radius: 8px; padding: 4px; }}"
            f"QMenu::item {{ padding: 5px 22px 5px 14px; border-radius: 6px; }}"
            f"QMenu::item:selected {{ background: {rgba(self._palette['accent'], 60)}; }}"
        )
        act_broadcast = menu.addAction(f"📣 广播消息到 {self._member_count} 个成员…")
        act_broadcast.setEnabled(self._member_count > 0)
        menu.addSeparator()
        act_dissolve = menu.addAction("解散团队（逐成员移除并关闭窗口）")
        act_dissolve.setEnabled(self._member_count > 0)
        chosen = menu.exec_(event.globalPos())
        if chosen is act_broadcast:
            self.broadcast_requested.emit(self._run_id, self._label)
        elif chosen is act_dissolve:
            self.dissolve_requested.emit(self._run_id, self._label)

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
            self._flow.removeWidget(tile)
            tile.deleteLater()
        for m in members:
            wid = m.get("window_id", "")
            if not wid:
                continue
            tile = self._tiles.get(wid)
            if tile is None:
                tile = MemberTile(m, self._palette)
                tile._panel_ref = self
                tile.activated.connect(self._on_activate)
                tile.drag_out_requested.connect(self._on_remove)
                tile.message_requested.connect(self._on_message)
                self._tiles[wid] = tile
                self._flow.insertWidget(self._flow.count() - 1, tile)
            else:
                tile.member = m
        self._empty_label.setVisible(not self._tiles)
        self._members_host.updateGeometry()

    def update_tile_state(self, window_id: str, state: str, task_count: int, context_percent: float):
        tile = self._tiles.get(window_id)
        if tile is not None:
            tile.apply_state(state, task_count, context_percent)

    def clear(self):
        for wid in list(self._tiles.keys()):
            tile = self._tiles.pop(wid)
            self._flow.removeWidget(tile)
            tile.deleteLater()
        self._empty_label.setVisible(True)

    # ── 拖放（add → 本团队）──

    def dragEnterEvent(self, event):
        data = parse_drag_mime(event.mimeData())
        if data and data.get("action") == "add":
            event.acceptProposedAction()
            self._apply_drop_hover_style()

    def dragLeaveEvent(self, event):
        self._apply_style()

    def dropEvent(self, event):
        self._apply_style()
        data = parse_drag_mime(event.mimeData())
        if not data or data.get("action") != "add":
            event.ignore()
            return
        event.acceptProposedAction()
        from PyQt5.QtCore import QTimer

        agent = data.get("agent_name", "")
        QTimer.singleShot(0, lambda: self._on_add(agent, self._run_id, self._label))

    def _apply_drop_hover_style(self):
        """拖拽悬停高亮（与 _apply_style 共用构建器，保留子控件规则）"""
        pal = self._palette
        self.setStyleSheet(
            self._panel_qss(rgba(pal["success"], 200), rgba(pal["success"], 30), rgba(pal["success"]))
        )

    _on_add: Any = lambda self, a, rid, lb: None  # noqa: E731
    _on_remove: Any = lambda self, w: None  # noqa: E731
    _on_activate: Any = lambda self, w: None  # noqa: E731
    _on_message: Any = lambda self, w, t: None  # noqa: E731
