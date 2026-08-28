# -*- coding: utf-8 -*-
"""PixelTeamStudioCard — 像素智能体团队工作室浮动卡片

功能：
- 实时可视化全部智能体团队（竖排卡片列表）与成员像素小人
- 团队卡片头部：激活标 + 团队名 + 成员数/忙碌徽章 + run_id 缩写
- 快捷建团（模板菜单）/ 双击智能体加入激活团队 / 拖拽加入指定团队
- 成员格：双击切到成员窗口、右键菜单、拖出移除（窗口保留）
- 头部统计栏（团队数/成员数/忙碌数）+ 手动刷新
- 5 秒轮询刷新（与主程序上下文圆环同源）

设计约束（闭包）：
- 数据访问走 ui/team_data.py（延迟 import app.*）
- 不直接导入 app.core / app.widgets
"""

from typing import Callable, Optional

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
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
from qfluentwidgets import FluentIcon, IconWidget, TransparentToolButton

from . import team_data
from .palette import make_palette, rgba
from .widgets import AgentTile, TeamPanel, TrashZone

REFRESH_MS = 5000
ANIM_MS = 150
BUSY_STATES = ("busy", "streaming", "thinking")


class PixelTeamStudioCard(QWidget):
    """像素智能体团队工作室浮动卡片"""

    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._palette: Optional[dict] = None
        self._panels: dict = {}  # run_id -> TeamPanel（竖排显示）
        self._agent_tiles: dict = {}  # agent_name -> AgentTile
        self._header_icon: Optional[IconWidget] = None
        self._status_label: Optional[QLabel] = None
        self._stats_label: Optional[QLabel] = None
        self._empty_hint: Optional[QLabel] = None
        self._teams_scroll: Optional[QScrollArea] = None
        self._title: Optional[QLabel] = None
        self._teams_title: Optional[QLabel] = None
        self._shelf_title: Optional[QLabel] = None
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

        两种情况不隐藏：
        1. 添加成员/建团后的保护窗口内（spawn 后切 tab 触发 sync）
        2. 纯切 tab 投影（UIPluginRegistry._tab_sync_in_progress）——工作室
           卡片常驻所有 tab，切到成员窗口后仍在，方便继续管理。
        用户主动关闭（_on_close）不受拦截。
        """
        if self._suppress_hide_until > time.monotonic():
            logger.debug("[pixel-team-studio] 保护窗口内拦截隐藏（添加成员/建团）")
            return
        try:
            from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

            if getattr(UIPluginRegistry.get_instance(), "_tab_sync_in_progress", False):
                logger.debug("[pixel-team-studio] 拦截切 tab 投影隐藏（卡片常驻）")
                return
        except Exception:  # noqa: BLE001
            pass
        self.setVisible(False)

    def _apply_plugin_icon(self):
        if self._context_provider is None or self._header_icon is None:
            return
        try:
            from qfluentwidgets import isDarkTheme

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
        # 根级默认样式（组件内部由各自 apply_palette 管理，不再全局暴力覆盖）
        self.setStyleSheet(
            "PixelTeamStudioCard { background: transparent; }"
            "QLabel { background: transparent; }"
        )
        # cards 层自有 label 逐个上色
        for lbl, color, size, weight in (
            (self._title, pal["text"], max(fs + 2, 15), "bold"),
            (self._stats_label, pal["accent"], max(fs - 2, 11), "600"),
            (self._status_label, pal["text_secondary"], max(fs - 3, 10), "normal"),
            (self._teams_title, pal["text_secondary"], max(fs - 2, 11), "600"),
            (self._shelf_title, pal["text_secondary"], max(fs - 2, 11), "600"),
            (self._empty_hint, pal["text_secondary"], max(fs - 1, 12), "normal"),
        ):
            if lbl is not None:
                lbl.setStyleSheet(
                    f"color: {rgba(color)}; font-size: {size}px; font-weight: {weight}; "
                    f"font-family: '{ff}'; background: transparent;"
                )
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
        self.setMinimumWidth(600)
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("PixelTeamStudioCard { background: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(0)

        # ── 背景面板（跟随文字亮度自洽深浅 + 圆角边框）──
        self._panel = QFrame(self)
        self._panel.setObjectName("ptsPanel")
        root.addWidget(self._panel, 1)

        ply = QVBoxLayout(self._panel)
        ply.setContentsMargins(16, 12, 16, 12)
        ply.setSpacing(8)

        # ── 头部：图标 + 标题 + 统计 + 状态 + 刷新/关闭 ──
        header = QWidget(self._panel)
        header.setStyleSheet("background: transparent;")
        hly = QHBoxLayout(header)
        hly.setContentsMargins(0, 0, 0, 0)
        hly.setSpacing(8)

        self._header_icon = IconWidget(FluentIcon.ROBOT, header)
        self._header_icon.setFixedSize(22, 22)
        hly.addWidget(self._header_icon)

        self._title = QLabel("像素团队工作室", header)
        self._title.setObjectName("ptsTitle")
        hly.addWidget(self._title)

        self._stats_label = QLabel("", header)
        self._stats_label.setObjectName("ptsStats")
        hly.addWidget(self._stats_label)
        hly.addStretch(1)

        self._status_label = QLabel("", header)
        self._status_label.setObjectName("ptsStatus")
        hly.addWidget(self._status_label)

        refresh_btn = TransparentToolButton(FluentIcon.SYNC, header)
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setToolTip("立即刷新")
        refresh_btn.clicked.connect(self._on_manual_refresh)
        hly.addWidget(refresh_btn)

        close_btn = TransparentToolButton(FluentIcon.CLOSE, header)
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self._on_close)
        hly.addWidget(close_btn)
        ply.addWidget(header)

        # ── 团队区标题行 + 新建按钮 ──
        tabs_row = QWidget(self._panel)
        tabs_row.setStyleSheet("background: transparent;")
        trly = QHBoxLayout(tabs_row)
        trly.setContentsMargins(0, 0, 0, 0)
        trly.setSpacing(8)

        self._teams_title = QLabel("◆ 智能体团队（⭐ 激活 · 双击小人切窗口 · 拖拽加成员）", tabs_row)
        self._teams_title.setObjectName("ptsTeamsTitle")
        trly.addWidget(self._teams_title)
        trly.addStretch(1)

        self._new_team_btn = QPushButton("＋ 新建团队", tabs_row)
        self._new_team_btn.setCursor(Qt.PointingHandCursor)
        self._new_team_btn.setFixedHeight(28)
        self._new_team_btn.clicked.connect(self._on_new_team_clicked)
        trly.addWidget(self._new_team_btn)
        ply.addWidget(tabs_row)

        # ── 团队面板区（竖排列表，滚动）──
        self._teams_scroll = QScrollArea(self._panel)
        self._teams_scroll.setWidgetResizable(True)
        self._teams_scroll.setFrameShape(QFrame.NoFrame)
        self._teams_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        teams_host = QWidget()
        teams_host.setStyleSheet("background: transparent;")
        self._teams_layout = QVBoxLayout(teams_host)
        self._teams_layout.setContentsMargins(0, 0, 0, 0)
        self._teams_layout.setSpacing(10)
        self._teams_layout.addStretch(1)
        self._teams_scroll.setWidget(teams_host)
        ply.addWidget(self._teams_scroll, 1)

        # 无团队提示（有团队时与滚动区互斥隐藏）
        self._empty_hint = QLabel(
            "还没有团队\n\n点击右上角「＋ 新建团队」从模板创建，\n"
            "或从下方智能体库双击小人 / 拖拽小人快速组建",
            self._panel,
        )
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setWordWrap(True)
        ply.addWidget(self._empty_hint, 1)

        # ── 分隔线 ──
        sep = QFrame(self._panel)
        sep.setFixedHeight(1)
        sep.setObjectName("ptsSep")
        ply.addWidget(sep)

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
        self._shelf_title = QLabel("▦ 智能体库 — 双击加入激活团队 · 拖拽加入指定团队", shelf_host)
        self._shelf_title.setObjectName("ptsShelfTitle")
        sly.addWidget(self._shelf_title)

        shelf_scroll = QScrollArea(shelf_host)
        shelf_scroll.setWidgetResizable(True)
        shelf_scroll.setFrameShape(QFrame.NoFrame)
        shelf_scroll.setFixedHeight(128)
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

    # ── 背景面板/分隔线主题 ──

    def _apply_panel_style(self):
        if self._palette is None:
            return
        pal = self._palette
        self._panel.setStyleSheet(
            f"QFrame#ptsPanel {{ background: {rgba(pal['panel_bg'])}; "
            f"border: 1px solid {rgba(pal['panel_border'])}; border-radius: 14px; }}"
            f"QFrame#ptsSep {{ background: {rgba(pal['panel_border'])}; border: none; }}"
            f"QLabel {{ background: transparent; }}"
        )
        self.update()

    # ── 团队面板区 ──

    def _sync_teams(self, teams: list):
        """按 run_id diff 团队面板（竖排显示，无则新建，离开则移除）"""
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
                panel._on_remove = self._on_remove_member
                panel._on_activate = self._on_member_activated
                panel._on_message = self._on_member_message
                self._panels[rid] = panel
                self._teams_layout.insertWidget(self._teams_layout.count() - 1, panel)
            panel.set_team(rid, team.get("label", ""), team.get("is_active", False), len(team["members"]))
            panel.sync_members(team.get("members", []))
        if self._empty_hint is not None:
            has_teams = bool(teams)
            self._empty_hint.setVisible(not has_teams)
            self._teams_scroll.setVisible(has_teams)

    def _apply_new_team_btn_style(self):
        if self._palette is None:
            return
        pal = self._palette
        nb = getattr(self, "_new_team_btn", None)
        if nb is not None:
            nb.setStyleSheet(
                f"QPushButton {{ border: 1px solid {rgba(pal['accent'], 220)}; border-radius: 8px; "
                f"background: {rgba(pal['accent'], 30)}; color: {rgba(pal['text'])}; "
                f"padding: 0 14px; font-size: 12px; font-weight: 600; }}"
                f"QPushButton:hover {{ background: {rgba(pal['accent'], 60)}; }}"
                f"QPushButton:pressed {{ background: {rgba(pal['accent'], 90)}; }}"
            )

    # ── 新建团队 ──

    def _on_new_team_clicked(self):
        menu = QMenu(self.window())
        menu.setStyleSheet(
            f"QMenu {{ background: {rgba(self._palette['panel_bg'])}; "
            f"color: {rgba(self._palette['text'])}; border-radius: 8px; padding: 4px; }}"
            f"QMenu::item {{ padding: 6px 24px 6px 14px; border-radius: 6px; }}"
            f"QMenu::item:selected {{ background: {rgba(self._palette['accent'], 60)}; }}"
        )
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
        chosen = menu.exec(self._new_team_btn.mapToGlobal(self._new_team_btn.rect().bottomLeft()))
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

    # ── 智能体库双击：加入激活团队 ──

    def _on_agent_activated(self, agent_name: str):
        active = team_data.get_active_team()
        if not active:
            self._set_status("无激活团队：请先「＋ 新建团队」或拖拽小人到任意团队")
            return
        self._on_add_member(agent_name, active["run_id"], active["label"])

    # ── 成员操作 ──

    def _on_member_activated(self, window_id: str):
        """双击成员格：切到该成员窗口 tab"""
        if team_data.switch_to_window(window_id):
            self._set_status("已切换到成员窗口")
        else:
            self._set_status("切换失败：成员窗口可能已关闭")

    def _on_member_message(self, window_id: str, text: str):
        """右键发消息：直接送到成员会话（不切窗口）"""
        ok = team_data.send_member_message(window_id, text)
        preview = text if len(text) <= 18 else text[:17] + "…"
        self._set_status(f"已发送「{preview}」到成员会话" if ok else "发送失败：成员窗口可能已关闭/忙")

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
        """添加成员/建团后：武装隐藏保护 + 轮询霸屏切回发起窗口 tab

        主程序 _spawn_team_members 结束时会无条件切到首个新成员窗口；
        本轮询每次都强制切回原 tab（幂等），保证"添加成员/建团不跳走"，
        直到发起窗口 join 全部完成（_pending_arrange_count 归零）。
        """
        self._suppress_hide_until = time.monotonic() + shield_seconds
        win = getattr(self, "_origin_window_ref", None)
        self._origin_window_ref = None
        if win is None:
            return
        self._restore_win = win
        self._restore_attempts = 0
        QTimer.singleShot(100, self._poll_restore_tab)

    def _poll_restore_tab(self):
        """轮询：每次强制切回原 tab（对抗主程序 spawn 后的强制切 tab），
        直到 join 全部完成（_pending_arrange_count 归零）停止。

        缓冲 300ms 确保 join 补注册（chat_engine 就绪轮询最长 1.5s）收尾。
        超时 6s 兜底停止霸屏。
        """
        win = self._restore_win
        if win is None or getattr(win, "_is_destroyed", False):
            self._restore_win = None
            return
        self._restore_attempts += 1
        # 霸屏：主程序已同步切到新成员 tab，这里立刻切回（已激活时幂等无操作）
        self._force_activate_tab(win)
        pending = getattr(win, "_pending_arrange_count", 0) or 0
        if pending <= 0 or self._restore_attempts >= 40:
            self._restore_win = None
            if self._restore_attempts >= 40:
                logger.debug("[pixel-team-studio] 恢复 tab 轮询超时，停止霸屏")
            QTimer.singleShot(300, self._switch_back_origin)
        else:
            QTimer.singleShot(150, self._poll_restore_tab)

    def _force_activate_tab(self, win) -> bool:
        """把 TabManagerWindow 激活 tab 强制切到指定窗口（非当前激活时才切，幂等）"""
        try:
            from app.widgets.tab_manager_window import TabManagerWindow

            tmw = TabManagerWindow.get_instance()
            if tmw is None:
                return False
            idx = tmw._window_to_index.get(id(win), -1)
            if idx < 0:
                return False
            if tmw.get_current_window() is win:
                return True  # 已激活，无需切
            tmw._tab_panel.set_active_index(idx)
            return True
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[pixel-team-studio] 强制切 tab 失败: {e}")
            return False

    def _switch_back_origin(self):
        """收尾：切回发起操作的窗口 tab（卡片可见记录在 sync 投影下自动恢复显示）"""
        win = getattr(self, "_restore_win", None)
        self._restore_win = None
        if win is not None:
            self._force_activate_tab(win)

    def _on_add_member(self, agent_name: str, run_id: str, team_label: str):
        """拖放/双击添加成员（run_id/team_label 由目标团队面板注入）"""
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

    def _on_manual_refresh(self):
        self._refresh()
        self._set_status("已刷新")

    def _set_status(self, text: str):
        if self._status_label is not None:
            self._status_label.setText(text)

    def _refresh(self):
        if not self.isVisible():
            return
        try:
            teams = team_data.get_teams()
            self._sync_teams(teams)

            # 更新每个团队面板内成员的状态/上下文 + 统计忙碌数
            total_members = 0
            total_busy = 0
            for team in teams:
                panel = self._panels.get(team["run_id"])
                if panel is None:
                    continue
                busy = 0
                for m in team.get("members", []):
                    wid = m.get("window_id", "")
                    if not wid:
                        continue
                    state = team_data.get_member_state(m)
                    ctx = team_data.get_member_context(m)
                    tasks = team_data.get_member_task_count(m)
                    panel.update_tile_state(wid, state, tasks, ctx.get("percent", 0))
                    if state in BUSY_STATES:
                        busy += 1
                total_members += len(team.get("members", []))
                total_busy += busy
                panel.set_busy_count(busy)
            if self._stats_label is not None:
                self._stats_label.setText(
                    f"· {len(teams)} 团队 · {total_members} 成员 · {total_busy} 忙碌"
                )

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
                tile.activated.connect(self._on_agent_activated)
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
