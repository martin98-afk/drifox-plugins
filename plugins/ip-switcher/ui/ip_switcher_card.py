# -*- coding: utf-8 -*-
"""ip-switcher 仪表盘浮动卡片（对齐系统插件 UI 规范）

┌──────────────────────────────────────────┐
│ [🌐] IP 换绑监控              [正常][×]  │  ← 头部：svg 图标 + 徽章(固定高) + 关闭
├──────────────────────────────────────────┤
│ 当前出口 IP                              │
│  103.216.72.14                           │  ← 大字等宽
│ [总换绑] [今日] [成功率] [代理池]         │  ← 统计格 ×4
│ [立即换 IP] [暂停自动]                   │  ← 操作按钮（上移）
├──────────────────────────────────────────┤
│ 换绑历史（占满剩余空间，ScrollArea）      │
│  ● 12:03 限流触发 · 98.xx → 103.x        │
│  ● 11:47 手动切换 · 45.xx → 98.xx        │
└──────────────────────────────────────────┘

设计约束：
- 主题色/字体 100% 走 context 注入（ctx.colors / font_family / font_size），
  不依赖 isDarkTheme()（浮动卡片背景偏暗，text 固定用 ctx 或白色 fallback）
- 图标用 qfluentwidgets FluentIcon（svg），不用 emoji
- 信号连接保存引用，销毁时断开（防 lambda 访问已删控件）
"""

import time
from typing import Callable, Optional

from PyQt5.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon,
    IconWidget,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
)
from loguru import logger

from config import get_config
from proxy_pool import get_manager
from state import SwitchEvent, get_state


# ── 主题色/字体辅助（对齐 system-cleaner 模式） ────────────


def _ctx_font(ctx: dict) -> tuple:
    ff = ctx.get("font_family", "Microsoft YaHei")
    fs = ctx.get("font_size", 14)
    return ff, fs


def _ctx_text_color(ctx: dict, secondary: bool = False) -> str:
    colors = ctx.get("colors", {}) or {}
    key = "text_secondary" if secondary else "text_primary"
    val = colors.get(key, "")
    if val:
        return val
    # fallback：浮动卡片背景偏暗，固定白色/浅色文字
    if isDarkTheme():
        return "rgba(255,255,255,0.55)" if secondary else "rgba(255,255,255,0.9)"
    return "rgba(0,0,0,0.45)" if secondary else "rgba(0,0,0,0.85)"


def _ctx_color(ctx: dict, key: str, fallback: str) -> str:
    return (ctx.get("colors", {}) or {}).get(key, "") or fallback


def _adjust_color(hex_color: str, amount: int) -> str:
    """简单地调亮/调暗一个 hex 颜色"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return hex_color
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = max(0, min(255, r + amount))
        g = max(0, min(255, g + amount))
        b = max(0, min(255, b + amount))
        return f"#{r:02x}{g:02x}{b:02x}"
    except ValueError:
        return hex_color


# ── 状态徽章映射（色值 + 标签） ──
_BADGE = {
    "ok": ("正常", "#22c55e"),
    "switching": ("限流切换中", "#eab308"),
    "error": ("代理池异常", "#ef4444"),
    "paused": ("已暂停", "#6b7280"),
    "stopped": ("代理池未启动", "#9ca3af"),
}

# 历史条目触发类型 → 色点颜色（svg 风格：纯色圆点，不用 emoji）
_TRIGGER_COLOR = {"ratelimit": "#ef4444", "manual": "#3b82f6"}


class IPSwitcherCard(QWidget):
    """IP 换绑监控仪表盘浮动卡片"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._is_busy = False
        self._state = get_state()
        self._config = get_config()

        # 缓存的上下文主题（供动态创建控件使用）
        self._cached_ff = "Microsoft YaHei"
        self._cached_fs = 14
        self._cached_tc = "rgba(255,255,255,0.9)"
        self._cached_tcs = "rgba(255,255,255,0.55)"
        self._cached_border = "rgba(128,128,128,0.15)"
        self._cached_accent = "#62a0ea"

        self._setup_ui()
        self._connect_signals()

    # ── 拉模型上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        self._apply_latest_theme()
        self._apply_plugin_icon()
        self._refresh_all()
        self.setVisible(True)

    def _apply_plugin_icon(self):
        if self._context_provider is None or self._header_icon is None:
            return
        try:
            from PyQt5.QtGui import QIcon

            ctx = self._context_provider()
            icon_info = ctx.get("plugin_icon", {})
            theme = "dark" if isDarkTheme() else "light"
            icon_path = icon_info.get(theme, "")
            if icon_path:
                self._header_icon.setIcon(QIcon(icon_path))
        except Exception:
            pass

    # ── 主题（ctx.colors 注入，深浅模式适配） ──

    def _apply_latest_theme(self):
        ctx = None
        if self._context_provider is not None:
            try:
                ctx = self._context_provider()
            except Exception:
                ctx = None

        # 缓存上下文值（供动态创建的历史行使用）
        if ctx is not None:
            self._cached_ff, self._cached_fs = _ctx_font(ctx)
            self._cached_tc = _ctx_text_color(ctx)
            self._cached_tcs = _ctx_text_color(ctx, secondary=True)
            self._cached_border = _ctx_color(ctx, "border", "rgba(128,128,128,0.15)")
            self._cached_accent = _ctx_color(ctx, "accent", "#62a0ea")
        ff, fs = self._cached_ff, self._cached_fs
        tc, tcs = self._cached_tc, self._cached_tcs
        border_c = self._cached_border
        accent = self._cached_accent

        # 第 1 层：QFont 级联
        if ff:
            self.setFont(QFont(ff, fs if fs else 14))

        # 第 2 层：刷新所有 QLabel 颜色（保留 font-weight）
        for lb in self.findChildren(QLabel):
            try:
                ss = lb.styleSheet()
                if not ss:
                    continue
                import re

                new_ss = re.sub(r"color:\s*[^;]+;", f"color: {tc};", ss)
                lb.setStyleSheet(new_ss)
            except RuntimeError:
                pass

        # 关键控件专属样式
        try:
            self._header_title.setStyleSheet(
                f"color: {tc}; background: transparent; font-family: '{ff}';"
                f" font-size: {max(12, fs + 1)}px; font-weight: 600;"
            )
            self._header_title.setFont(QFont(ff, max(12, fs + 1)))
        except RuntimeError:
            pass
        try:
            self._ip_label.setStyleSheet(
                f"color: {tc}; background: transparent; font-family: '{ff}';"
                f" font-size: {fs + 6}px; font-weight: 600;"
            )
        except RuntimeError:
            pass
        try:
            self._badge_label.setStyleSheet(self._badge_style())
        except RuntimeError:
            pass
        try:
            self._ip_hint.setStyleSheet(
                f"color: {tcs}; background: transparent; font-family: '{ff}';"
                f" font-size: {max(10, fs - 2)}px;"
            )
        except RuntimeError:
            pass
        try:
            self._hist_hint.setStyleSheet(
                f"color: {tcs}; background: transparent; font-family: '{ff}';"
                f" font-size: {max(10, fs - 3)}px; letter-spacing: 2px;"
                f" padding: 10px 16px 4px;"
            )
        except RuntimeError:
            pass
        try:
            self._sep.setStyleSheet(f"background: {border_c}; max-height: 1px;")
        except RuntimeError:
            pass
        try:
            self._switch_btn.setStyleSheet(self._switch_btn_style(accent, fs, ff))
        except RuntimeError:
            pass
        try:
            self._auto_btn.setStyleSheet(self._auto_btn_style(fs, ff))
        except RuntimeError:
            pass
        # 统计格
        for cell, val_lb, name_lb in self._stat_cells:
            try:
                cell.setStyleSheet(
                    "background: rgba(128,128,128,0.08); border-radius: 6px;"
                )
                val_lb.setStyleSheet(
                    f"color: {tc}; background: transparent; font-family: '{ff}';"
                    f" font-size: {fs}px; font-weight: 600;"
                )
                name_lb.setStyleSheet(
                    f"color: {tcs}; background: transparent; font-family: '{ff}';"
                    f" font-size: {max(9, fs - 4)}px;"
                )
            except RuntimeError:
                pass

    # ── 徽章 ──

    def _badge_state(self):
        pool = self._state.pool_state()
        if pool == "error":
            return _BADGE["error"]
        if pool == "stopped":
            return _BADGE["stopped"]
        if not self._state.is_auto_switch():
            return _BADGE["paused"]
        return _BADGE["ok"]

    def _badge_style(self) -> str:
        _, color = self._badge_state()
        ff, fs = self._cached_ff, self._cached_fs
        return (
            f"color: {color}; background: {color}22; border: 1px solid {color}55;"
            f" border-radius: 11px; padding: 0 10px; font-family: '{ff}';"
            f" font-size: {max(10, fs - 2)}px;"
        )

    # ── 按钮样式（对齐 system-cleaner 渐变按钮） ──

    def _switch_btn_style(self, accent: str, fs: int, ff: str = "") -> str:
        font_qss = f"font-family: '{ff}';" if ff else ""
        return (
            f"QPushButton {{ background: qlineargradient("
            f"x1:0, y1:0, x2:1, y2:1, stop:0 {accent}, stop:1 {_adjust_color(accent, -20)}"
            "); color: white; border: none; border-radius: 6px;"
            f" {font_qss} font-size: {max(10, fs - 2)}px; font-weight: 600; padding: 0 10px; }}"
            "QPushButton:hover { background: qlineargradient("
            f"x1:0, y1:0, x2:1, y2:1, stop:0 {_adjust_color(accent, 10)}, stop:1 {accent}"
            "); }"
            "QPushButton:disabled { background: rgba(128,128,128,0.3); color: rgba(255,255,255,0.5); }"
        )

    def _auto_btn_style(self, fs: int, ff: str = "") -> str:
        dark = isDarkTheme()
        bg = "rgba(255,255,255,0.08)" if dark else "rgba(0,0,0,0.06)"
        color = "rgba(255,255,255,0.85)" if dark else "rgba(0,0,0,0.85)"
        border = "rgba(255,255,255,0.12)" if dark else "rgba(0,0,0,0.12)"
        hover_bg = "rgba(255,255,255,0.14)" if dark else "rgba(0,0,0,0.10)"
        font_qss = f"font-family: '{ff}';" if ff else ""
        return (
            f"QPushButton {{ background: {bg}; color: {color};"
            f" border: 1px solid {border}; border-radius: 6px;"
            f" {font_qss} font-size: {max(10, fs - 2)}px; font-weight: 500; padding: 0 10px; }}"
            f"QPushButton:hover {{ background: {hover_bg}; }}"
        )

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumSize(360, 320)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("IPSwitcherCard { background: transparent; }")
        self._history_labels: list = []
        self._stat_cells: list = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_header(root)

        self._sep = QFrame(self)
        self._sep.setFrameShape(QFrame.HLine)
        self._sep.setStyleSheet("background: rgba(128,128,128,0.15); max-height: 1px;")
        root.addWidget(self._sep)

        self._build_ip_section(root)
        self._build_stats_section(root)
        self._build_actions_section(root)
        self._build_history_section(root)

    def _build_header(self, root: QVBoxLayout):
        header = QWidget(self)
        header.setStyleSheet("background: transparent;")
        hly = QHBoxLayout(header)
        hly.setContentsMargins(16, 12, 16, 4)
        hly.setSpacing(8)

        self._header_icon = IconWidget(FluentIcon.GLOBE, header)
        self._header_icon.setFixedSize(22, 22)
        hly.addWidget(self._header_icon)

        self._header_title = StrongBodyLabel("IP 换绑监控", header)
        self._header_title.setStyleSheet(
            f"color: {self._cached_tc}; background: transparent;"
            f" font-family: '{self._cached_ff}';"
            f" font-size: {max(12, self._cached_fs + 1)}px; font-weight: 600;"
        )
        hly.addWidget(self._header_title)

        hly.addStretch(1)

        # 状态徽章（固定高度修复右上角高度异常）
        self._badge_label = QLabel("正常", header)
        self._badge_label.setFixedHeight(22)
        self._badge_label.setAlignment(Qt.AlignCenter)
        self._badge_label.setStyleSheet(self._badge_style())
        hly.addWidget(self._badge_label)

        close_btn = TransparentToolButton(FluentIcon.CLOSE, header)
        close_btn.setFixedSize(24, 24)
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self._on_close)
        hly.addWidget(close_btn)

        root.addWidget(header)

    def _build_ip_section(self, root: QVBoxLayout):
        ip_wrap = QWidget(self)
        ip_wrap.setStyleSheet("background: transparent;")
        ily = QVBoxLayout(ip_wrap)
        ily.setContentsMargins(16, 10, 16, 2)
        ily.setSpacing(0)
        self._ip_hint = QLabel("当前出口 IP", ip_wrap)
        self._ip_hint.setStyleSheet(
            f"color: {self._cached_tcs}; background: transparent;"
            f" font-size: {max(10, self._cached_fs - 2)}px;"
        )
        ily.addWidget(self._ip_hint)
        self._ip_label = QLabel("未使用", ip_wrap)
        self._ip_label.setStyleSheet(
            f"color: {self._cached_tc}; background: transparent;"
            f" font-size: {self._cached_fs + 6}px; font-weight: 600;"
        )
        ily.addWidget(self._ip_label)
        root.addWidget(ip_wrap)

    def _build_stats_section(self, root: QVBoxLayout):
        stats = QWidget(self)
        stats.setStyleSheet("background: transparent;")
        sly = QHBoxLayout(stats)
        sly.setContentsMargins(16, 6, 16, 4)
        sly.setSpacing(8)
        self._stat_labels = {}
        for key, name in (
            ("total_switches", "总换绑"),
            ("today_switches", "今日"),
            ("success_rate", "成功率"),
            ("pool_size", "代理池"),
        ):
            cell = QFrame(stats)
            cell.setStyleSheet(
                "background: rgba(128,128,128,0.08); border-radius: 6px;"
            )
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(6, 6, 6, 6)
            cl.setAlignment(Qt.AlignCenter)
            val = QLabel("0", cell)
            val.setAlignment(Qt.AlignCenter)
            val.setStyleSheet(
                f"color: {self._cached_tc}; background: transparent; font-weight: 600;"
            )
            name_lb = QLabel(name, cell)
            name_lb.setAlignment(Qt.AlignCenter)
            name_lb.setStyleSheet(
                f"color: {self._cached_tcs}; background: transparent;"
                f" font-size: {max(9, self._cached_fs - 4)}px;"
            )
            cl.addWidget(val)
            cl.addWidget(name_lb)
            self._stat_labels[key] = val
            self._stat_cells.append((cell, val, name_lb))
            sly.addWidget(cell, 1)
        root.addWidget(stats)

    def _build_actions_section(self, root: QVBoxLayout):
        """操作按钮（上移：统计格下方、历史上方）"""
        btns = QWidget(self)
        btns.setStyleSheet("background: transparent;")
        bly = QHBoxLayout(btns)
        bly.setContentsMargins(16, 6, 16, 4)
        bly.setSpacing(8)
        self._switch_btn = QPushButton("立即换 IP", btns)
        self._switch_btn.setCursor(Qt.PointingHandCursor)
        self._switch_btn.setMinimumHeight(32)
        self._switch_btn.setStyleSheet(
            self._switch_btn_style(
                self._cached_accent, self._cached_fs, self._cached_ff
            )
        )
        self._switch_btn.clicked.connect(self._on_manual_switch)
        bly.addWidget(self._switch_btn, 1)
        self._auto_btn = QPushButton("暂停自动", btns)
        self._auto_btn.setCursor(Qt.PointingHandCursor)
        self._auto_btn.setMinimumHeight(32)
        self._auto_btn.setStyleSheet(
            self._auto_btn_style(self._cached_fs, self._cached_ff)
        )
        self._auto_btn.clicked.connect(self._on_toggle_auto)
        bly.addWidget(self._auto_btn, 1)
        root.addWidget(btns)

    def _build_history_section(self, root: QVBoxLayout):
        """换绑历史（占满剩余空间：ScrollArea + stretch）"""
        self._hist_hint = QLabel("换绑历史", self)
        self._hist_hint.setStyleSheet(
            f"color: {self._cached_tcs}; background: transparent;"
            f" font-size: {max(10, self._cached_fs - 3)}px; letter-spacing: 2px;"
            f" padding: 10px 16px 2px;"
        )
        root.addWidget(self._hist_hint)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical {"
            " background: rgba(128,128,128,0.25); border-radius: 3px; min-height: 30px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._history_box = QWidget(self._scroll)
        self._history_box.setStyleSheet("background: transparent;")
        self._history_layout = QVBoxLayout(self._history_box)
        self._history_layout.setContentsMargins(16, 0, 16, 8)
        self._history_layout.setSpacing(2)
        self._history_layout.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._history_box)
        root.addWidget(self._scroll, 1)  # stretch=1 占满剩余

    # ── 信号连接 ──

    def _connect_signals(self):
        self._signal_conns = [
            (self._state.switched, lambda _ev: self._refresh_all()),
            (self._state.status_changed, lambda _f, _v: self._refresh_all()),
            (self._state.pool_state_changed, lambda _s: self._refresh_all()),
        ]
        for sig, slot in self._signal_conns:
            sig.connect(slot)

    def _disconnect_signals(self):
        """断开 state 信号（卡片销毁前调用，防 lambda 访问已删控件）"""
        for sig, slot in getattr(self, "_signal_conns", []):
            try:
                sig.disconnect(slot)
            except Exception:
                pass
        self._signal_conns = []

    # ── 刷新 ──

    def _refresh_all(self):
        # Qt 生命周期防护：卡片已被销毁时控件可能已 C++ 删除
        try:
            import sip

            if sip.isdeleted(self._badge_label):
                return
        except Exception:
            pass
        st = self._state
        # 徽章
        text, _ = self._badge_state()
        self._badge_label.setText(text)
        self._badge_label.setStyleSheet(self._badge_style())
        # 当前 IP
        self._ip_label.setText(st.current_ip())
        # 统计
        stats = st.stats()
        self._stat_labels["total_switches"].setText(str(stats["total_switches"]))
        self._stat_labels["today_switches"].setText(str(stats["today_switches"]))
        total = stats["total_switches"]
        success = stats["success_count"]
        rate = f"{int(success * 100 / total)}%" if total else "-"
        self._stat_labels["success_rate"].setText(rate)
        manager = get_manager()
        pool_stats = manager.get_stats()
        pool_size = pool_stats.get("pool_size", "-") if pool_stats else "-"
        self._stat_labels["pool_size"].setText(str(pool_size))
        # 历史（最近 8 条，占满区域可滚动）
        self._render_history(st.history()[:8])
        # 按钮
        self._auto_btn.setText("恢复自动" if not st.is_auto_switch() else "暂停自动")

    def _render_history(self, events):
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._history_labels = []
        if not events:
            empty = QLabel("暂无换绑记录", self._history_box)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"color: {self._cached_tcs}; background: transparent;"
                f" font-size: {max(10, self._cached_fs - 2)}px; padding: 30px;"
            )
            self._history_layout.addWidget(empty)
            return
        for ev in events:
            row = self._make_history_row(ev)
            self._history_layout.addWidget(row)
            self._history_labels.append(row)

    def _make_history_row(self, ev: SwitchEvent) -> QWidget:
        t = time.strftime("%H:%M", time.localtime(ev.timestamp))
        trigger = "限流触发" if ev.trigger == "ratelimit" else "手动切换"
        color = _TRIGGER_COLOR.get(ev.trigger, "#9ca3af")

        row = QWidget(self._history_box)
        row.setStyleSheet("background: transparent;")
        rly = QHBoxLayout(row)
        rly.setContentsMargins(0, 2, 0, 2)
        rly.setSpacing(8)

        # 色点（svg 风格：纯色圆点，不用 emoji）
        dot = QLabel("●", row)
        dot.setStyleSheet(f"color: {color}; background: transparent; font-size: 9px;")
        dot.setFixedWidth(10)
        rly.addWidget(dot)

        text = f"{t}  {trigger}  ·  {ev.old_ip} → {ev.new_ip}"
        lb = QLabel(text, row)
        lb.setStyleSheet(
            f"color: {self._cached_tcs}; background: transparent;"
            f" font-family: '{self._cached_ff}'; font-size: {max(10, self._cached_fs - 2)}px;"
        )
        lb.setToolTip(
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ev.timestamp))}\n"
            f"触发: {trigger}\n{ev.note or ''}"
        )
        rly.addWidget(lb)
        rly.addStretch(1)
        return row

    # ── 操作 ──

    def _on_manual_switch(self):
        if self._is_busy:
            return
        self._is_busy = True
        self._switch_btn.setEnabled(False)
        self._switch_btn.setText("切换中…")
        try:
            from ip_redirect import _switch_ip_threadsafe

            new_ip = _switch_ip_threadsafe()
            if new_ip:
                self._switch_btn.setText("已切换")
            else:
                self._switch_btn.setText("切换失败")
        except Exception:
            logger.exception("[ip-switcher] 手动换 IP 异常")
            self._switch_btn.setText("切换失败")
        finally:
            QTimer.singleShot(2000, self._reset_btn)

    def _reset_btn(self):
        if not self._is_busy:
            return
        self._is_busy = False
        self._switch_btn.setEnabled(True)
        self._switch_btn.setText("立即换 IP")

    def _on_toggle_auto(self):
        st = self._state
        st.set_auto_switch(not st.is_auto_switch())
        self._config.set("auto_switch", st.is_auto_switch())
        self._refresh_all()

    # ── 比例高度（与系统卡片一致） ──

    def sizeHint(self):
        base = super().sizeHint()
        win = self.window()
        if win and win.height() > 0:
            return QSize(max(base.width(), 200), int(win.height() * 0.85))
        return base

    def showEvent(self, event):
        super().showEvent(event)
        win = self.window()
        if win:
            win.installEventFilter(self)
            self.updateGeometry()

    def eventFilter(self, obj, event):
        if obj is self.window() and event.type() == QEvent.Resize:
            self.updateGeometry()
        return super().eventFilter(obj, event)

    # ── 生命周期 ──

    def deleteLater(self):
        self._disconnect_signals()
        super().deleteLater()

    def _on_close(self):
        self._disconnect_signals()
        self.setVisible(False)
        self.closed.emit()
