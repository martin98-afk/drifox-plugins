# -*- coding: utf-8 -*-
"""PixelTeamStudioCard — 像素智能体团队工作室浮动卡片

功能：
- 实时可视化全部智能体团队（run_id 分组）与成员像素小人
- 团队标签切换 / 从模板一键新建团队
- 智能体库拖拽添加成员，拖入垃圾桶移除成员（窗口保留）
- 每个小人展示工作状态（空闲/忙碌/思考/输出/提问/异常）+ 上下文负荷进度条
- 5 秒轮询刷新（与主程序上下文圆环同源）

设计约束（闭包）：
- 数据访问走 ui/team_data.py（延迟 import app.*）
- 不直接导入 app.core / app.widgets
"""

from typing import Callable, Optional

import time

from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from loguru import logger
from qfluentwidgets import FluentIcon, IconWidget, TransparentToolButton, isDarkTheme

from . import team_data
from .palette import make_palette, rgba
from .widgets import AgentTile, TeamPanel, TrashZone

REFRESH_MS = 5000
ANIM_MS = 300


class PixelTeamStudioCard(QWidget):
    """像素智能体团队工作室浮动卡片"""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._palette: Optional[dict] = None
        self._panels: dict = {}  # run_id -> TeamPanel（并排显示）
        self._agent_tiles: dict = {}  # agent_name -> AgentTile
        self._header_icon: Optional[IconWidget] = None
        self._status_label: Optional[QLabel] = None
        self._empty_hint: Optional[QLabel] = None
        # 隐藏保护：添加成员/建团后短暂窗口内拒绝被切 tab 隐藏（monotonic 截止时刻）
        self._suppress_hide_until: float = 0.0
        # 恢复 tab 轮询状态
        self._restore_win = None
        self._restore_attempts = 0
        self._setup_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(REFRESH_MS)
        self._refresh_timer.timeout.connect(self._refresh)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(ANIM_MS)
        self._anim_timer.timeout.connect(self._advance_anim)

    # ── 拉模型上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        self._apply_latest_theme()
        self._apply_plugin_icon()
        self._refresh()
        self._refresh_timer.start()
        self._anim_timer.start()
        self.setVisible(True)

    def hide_card(self):
        """CardManager 隐藏卡片时调用（切 tab 投影 / 互斥）

        添加成员/建团后的保护窗口内拒绝隐藏——
        _spawn_team_members 会强制切 tab 到新成员窗口，触发 sync 隐藏；
        保护窗口内拦截后卡片保持可见，之后恢复 tab 再回到工作室。
        """
        if self._suppress_hide_until > time.monotonic():
            logger.debug("[pixel-team-studio] 保护窗口内拦截隐藏（添加成员/建团）")
            return
        self.setVisible(False)

    def _apply_plugin_icon(self):
        if self._context_provider is None or self._header_icon is None:
            return
        try:
            ctx = self._context_provider()
            icon_info = ctx.get("plugin_icon", {})
            theme = "dark" if isDarkTheme() else "light"
            icon_path = icon_info.get(theme, "")
            if icon_path:
                self._header_icon.setIcon(QIcon(icon_path))
        except Exception:  # noqa: BLE001
            pass

    def _apply_latest_theme(self):
        ctx = {}
        try:
            if self._context_provider is not None:
                ctx = self._context_provider() or {}
        except Exception:  # noqa: BLE001
            ctx = {}
        self._palette = make_palette(ctx)

        pal = self._palette
        ff = pal["font_family"]
        fs = pal["font_size"]
        self.setStyleSheet(
            f"PixelTeamStudioCard {{ background: transparent; }}"
            f"QLabel {{ background: transparent; }}"
        )
        for child in self.findChildren(QLabel):
            try:
                current = child.styleSheet()
                weight = "font-weight: bold;" if "font-weight" in current else ""
                child.setStyleSheet(
                    f"color: {rgba(pal['text_secondary'])}; font-size: {max(fs - 2, 11)}px; "
                    f"font-family: '{ff}'; {weight} background: transparent;"
                )
            except RuntimeError:
                pass
        # 面板/垃圾桶/成员格跟随主题
        self._apply_panel_style()
        for panel in self._panels.values():
            panel.apply_palette(pal)
        self._trash_zone.apply_palette(pal)
        for tile in self._agent_tiles.values():
            tile.apply_palette(pal)
        self._apply_new_team_btn_style()

    # ── 界面搭建 ──

    def _setup_ui(self):
        self.setMinimumWidth(560)
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("PixelTeamStudioCard { background: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(0)

        # ── 背景面板（像素风深色半透明 + 圆角边框）──
        self._panel = QFrame(self)
        self._panel.setObjectName("ptsPanel")
        root.addWidget(self._panel, 1)

        ply = QVBoxLayout(self._panel)
        ply.setContentsMargins(18, 14, 18, 14)
        ply.setSpacing(10)

        # ── 头部 ──
        header = QWidget(self._panel)
        header.setStyleSheet("background: transparent;")
        hly = QHBoxLayout(header)
        hly.setContentsMargins(0, 0, 0, 0)
        hly.setSpacing(8)

        self._header_icon = IconWidget(FluentIcon.ROBOT, header)
        self._header_icon.setFixedSize(22, 22)
        hly.addWidget(self._header_icon)

        title = QLabel("像素团队工作室", header)
        title.setStyleSheet("font-size: 16px; font-weight: bold; background: transparent;")
        hly.addWidget(title)

        self._status_label = QLabel("", header)
        hly.addWidget(self._status_label)
        hly.addStretch(1)

        close_btn = TransparentToolButton(FluentIcon.CLOSE, header)
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self._on_close)
        hly.addWidget(close_btn)
        ply.addWidget(header)

        # ── 团队区标题行 + 新建按钮 ──
        tabs_row = QWidget(self._panel)
        tabs_row.setStyleSheet("background: transparent;")
        trly = QHBoxLayout(tabs_row)
        trly.setContentsMargins(0, 0, 0, 0)
        trly.setSpacing(8)

        teams_title = QLabel("◆ 智能体团队（并排显示，⭐=激活，拖入小人添加成员）", tabs_row)
        teams_title.setObjectName("ptsTeamsTitle")
        trly.addWidget(teams_title)
        trly.addStretch(1)

        self._new_team_btn = QPushButton("＋ 新建团队", tabs_row)
        self._new_team_btn.setCursor(Qt.PointingHandCursor)
        self._new_team_btn.setFixedHeight(30)
        self._new_team_btn.clicked.connect(self._on_new_team_clicked)
        trly.addWidget(self._new_team_btn)
        ply.addWidget(tabs_row)

        # ── 团队面板区（横向并排，滚动）──
        teams_scroll = QScrollArea(self._panel)
        teams_scroll.setWidgetResizable(True)
        teams_scroll.setFrameShape(QFrame.NoFrame)
        teams_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        teams_host = QWidget()
        teams_host.setStyleSheet("background: transparent;")
        self._teams_layout = QHBoxLayout(teams_host)
        self._teams_layout.setContentsMargins(0, 0, 0, 0)
        self._teams_layout.setSpacing(10)
        self._teams_layout.addStretch(1)
        teams_scroll.setWidget(teams_host)
        ply.addWidget(teams_scroll, 1)

        # 无团队提示（有团队时隐藏）
        self._empty_hint = QLabel("还没有团队\n\n点击右上角「＋ 新建团队」从模板创建，\n或从下方智能体库拖拽像素小人到空白处", self._panel)
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setWordWrap(True)
        ply.addWidget(self._empty_hint, 1)

        # ── 底部：智能体库 + 垃圾桶 ──
        bottom = QWidget(self._panel)
        bottom.setStyleSheet("background: transparent;")
        bly = QHBoxLayout(bottom)
        bly.setContentsMargins(0, 0, 0, 0)
        bly.setSpacing(10)

        shelf_host = QWidget(bottom)
        shelf_host.setStyleSheet("background: transparent;")
        sly = QVBoxLayout(shelf_host)
        sly.setContentsMargins(0, 0, 0, 0)
        sly.setSpacing(6)
        shelf_title = QLabel("▦ 智能体库 — 拖拽像素小人到上方团队添加成员", shelf_host)
        shelf_title.setObjectName("ptsShelfTitle")
        sly.addWidget(shelf_title)

        shelf_scroll = QScrollArea(shelf_host)
        shelf_scroll.setWidgetResizable(True)
        shelf_scroll.setFrameShape(QFrame.NoFrame)
        shelf_scroll.setFixedHeight(126)
        shelf_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        shelf_host2 = QWidget()
        shelf_host2.setStyleSheet("background: transparent;")
        self._shelf_layout = QHBoxLayout(shelf_host2)
        self._shelf_layout.setContentsMargins(0, 0, 0, 0)
        self._shelf_layout.setSpacing(8)
        self._shelf_layout.addStretch(1)
        shelf_scroll.setWidget(shelf_host2)
        sly.addWidget(shelf_scroll)
        bly.addWidget(shelf_host, 1)

        self._trash_zone = TrashZone(self._palette)
        self._trash_zone._on_remove = self._on_remove_member
        bly.addWidget(self._trash_zone, 0, Qt.AlignBottom)
        ply.addWidget(bottom)

    # ── 背景面板主题 ──

    def _apply_panel_style(self):
        if self._palette is None:
            return
        pal = self._palette
        if pal["is_dark"]:
            bg = "rgba(18, 20, 32, 0.82)"
            border = "rgba(255, 255, 255, 0.14)"
        else:
            bg = "rgba(252, 252, 254, 0.92)"
            border = "rgba(0, 0, 0, 0.12)"
        self._panel.setStyleSheet(
            f"QFrame#ptsPanel {{ background: {bg}; border: 2px solid {border}; "
            f"border-radius: 14px; }}"
            f"QLabel {{ background: transparent; }}"
        )
        self.update()

    # ── 团队面板区 ──

    def _sync_teams(self, teams: list):
        """按 run_id diff 团队面板（并排显示，无则新建，离开则移除）"""
        current_ids = set(self._panels.keys())
        new_ids = {t["run_id"] for t in teams}
        for rid in current_ids - new_ids:
            panel = self._panels.pop(rid)
            self._teams_layout.removeWidget(panel)
            panel.deleteLater()
        for team in teams:
            rid = team["run_id"]
            panel = self._panels.get(rid)
            if panel is None:
                panel = TeamPanel(self._palette)
                panel._on_add = self._on_add_member
                self._panels[rid] = panel
                self._teams_layout.insertWidget(self._teams_layout.count() - 1, panel)
            panel.set_team(rid, team.get("label", ""), team.get("is_active", False), len(team["members"]))
            panel.sync_members(team.get("members", []))
        if self._empty_hint is not None:
            self._empty_hint.setVisible(not teams)

    def _apply_new_team_btn_style(self):
        if self._palette is None:
            return
        pal = self._palette
        nb = getattr(self, "_new_team_btn", None)
        if nb is not None:
            nb.setStyleSheet(
                f"QPushButton {{ border: 1px solid {rgba(pal['accent'], 220)}; border-radius: 8px; "
                f"background: {rgba(pal['accent'], 30)}; color: {rgba(pal['text'])}; padding: 0 14px; font-size: 12px; }}"
                f"QPushButton:hover {{ background: {rgba(pal['accent'], 60)}; }}"
            )

    # ── 新建团队 ──

    def _on_new_team_clicked(self):
        menu = QMenu(self.window())
        templates = team_data.list_templates()
        if not templates:
            act = menu.addAction("无可用团队模板")
            if act is not None:
                act.setEnabled(False)
        for t in templates:
            count = t.get("agent_count", 0)
            act = menu.addAction(f"「{t.get('name', '?')}」 — {count} 个角色")
            if act is None:
                continue
            act.setToolTip(t.get("description", ""))
            act._template_name = t.get("name", "")
        chosen = menu.exec_(self._new_team_btn.mapToGlobal(self._new_team_btn.rect().bottomLeft()))
        if chosen is None or not getattr(chosen, "_template_name", ""):
            return
        name = chosen._template_name
        self._snapshot_origin()
        count = team_data.create_team_from_template(name)
        if count > 0:
            self._set_status(f"已创建团队「{name}」({count} 个成员窗口)")
            self._restore_origin_tab(shield_seconds=5.0)
        else:
            self._set_status("创建团队失败：请确认主窗口已就绪")
        self._refresh()

    # ── 成员操作 ──

    def _snapshot_origin(self):
        """记录当前激活窗口（添加成员/建团后恢复，避免 full 卡片被切走关闭）"""
        self._origin_window_ref = None
        try:
            from app.widgets.tab_manager_window import TabManagerWindow

            tmw = TabManagerWindow.get_instance()
            if tmw is not None:
                win = tmw.get_current_window()
                if win is not None and not getattr(win, "_is_destroyed", False):
                    self._origin_window_ref = win
        except Exception:  # noqa: BLE001
            pass

    def _restore_origin_tab(self, shield_seconds: float = 2.5):
        """添加成员/建团后：武装隐藏保护 + 轮询等待 join 完成再切回发起窗口 tab"""
        self._suppress_hide_until = time.monotonic() + shield_seconds
        win = getattr(self, "_origin_window_ref", None)
        self._origin_window_ref = None
        if win is None:
            return
        self._restore_win = win
        self._restore_attempts = 0
        QTimer.singleShot(200, self._poll_restore_tab)

    def _poll_restore_tab(self):
        """轮询：发起窗口 join 全部完成（_pending_arrange_count 归零）后切回

        缓冲 300ms 确保 join 补注册（chat_engine 就绪轮询最长 1.5s）收尾。
        超时 6s 兜底强制切回。
        """
        win = self._restore_win
        if win is None or getattr(win, "_is_destroyed", False):
            self._restore_win = None
            return
        self._restore_attempts += 1
        pending = getattr(win, "_pending_arrange_count", 0) or 0
        if pending <= 0 or self._restore_attempts >= 30:
            self._restore_win = None
            if self._restore_attempts >= 30:
                logger.debug("[pixel-team-studio] 恢复 tab 轮询超时，强制切回")
            QTimer.singleShot(300, self._switch_back_origin)
        else:
            QTimer.singleShot(200, self._poll_restore_tab)

    def _switch_back_origin(self):
        """切回发起操作的窗口 tab（卡片可见记录在 sync 投影下自动恢复显示）"""
        win = getattr(self, "_restore_win", None)
        self._restore_win = None
        if win is None:
            return
        try:
            from app.widgets.tab_manager_window import TabManagerWindow

            tmw = TabManagerWindow.get_instance()
            if tmw is None:
                return
            idx = tmw._window_to_index.get(id(win), -1)
            if idx >= 0:
                tmw._tab_panel.set_active_index(idx)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[pixel-team-studio] 切回原 tab 失败: {e}")

    def _on_add_member(self, agent_name: str, run_id: str, team_label: str):
        """拖放添加成员（run_id/team_label 由 drop 到的团队面板注入）"""
        if not agent_name or not run_id:
            return
        self._snapshot_origin()
        ok = team_data.add_member(agent_name, run_id, team_label)
        self._set_status(f"已添加成员 {agent_name} 到「{team_label or run_id[:8]}」" if ok else f"添加成员 {agent_name} 失败")
        if ok:
            self._restore_origin_tab(shield_seconds=2.5)
        self._refresh()

    def _on_remove_member(self, window_id: str):
        ok = team_data.remove_member(window_id)
        self._set_status("成员已离开团队（窗口保留）" if ok else "移除成员失败")
        self._refresh()

    # ── 刷新 ──

    def _set_status(self, text: str):
        if self._status_label is not None:
            self._status_label.setText(text)

    def _refresh(self):
        if not self.isVisible():
            return
        try:
            teams = team_data.get_teams()
            self._sync_teams(teams)

            # 更新每个团队面板内成员的状态/上下文
            for team in teams:
                panel = self._panels.get(team["run_id"])
                if panel is None:
                    continue
                for m in team.get("members", []):
                    wid = m.get("window_id", "")
                    if not wid:
                        continue
                    state = team_data.get_member_state(m)
                    ctx = team_data.get_member_context(m)
                    tasks = team_data.get_member_task_count(m)
                    panel.update_tile_state(wid, state, tasks, ctx.get("percent", 0))

            self._sync_agents()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[pixel-team-studio] 刷新失败: {e}")

    def _sync_agents(self):
        """智能体库 diff 刷新（角色增删时重建，静态则复用 tile 保持动画）"""
        agents = team_data.list_agents()
        current_names = set(self._agent_tiles.keys())
        new_names = {a["name"] for a in agents}
        for name in current_names - new_names:
            tile = self._agent_tiles.pop(name)
            self._shelf_layout.removeWidget(tile)
            tile.deleteLater()
        for a in agents:
            name = a["name"]
            tile = self._agent_tiles.get(name)
            if tile is None:
                tile = AgentTile(name, a.get("description", ""), self._palette)
                self._agent_tiles[name] = tile
                self._shelf_layout.insertWidget(self._shelf_layout.count() - 1, tile)

    def _advance_anim(self):
        if not self.isVisible():
            return
        for panel in self._panels.values():
            for tile in panel._tiles.values():
                tile.advance_bounce()

    # ── 关闭 ──

    def _on_close(self):
        # 用户主动关闭：解除隐藏保护（否则 closed→hide_card 会被拦截）
        self._suppress_hide_until = 0.0
        self._refresh_timer.stop()
        self._anim_timer.stop()
        self.setVisible(False)
        self.closed.emit()

    def deleteLater(self):
        try:
            self._refresh_timer.stop()
            self._anim_timer.stop()
        except RuntimeError:
            pass
        super().deleteLater()
