# -*- coding: utf-8 -*-
"""ip-switcher 仪表盘浮动卡片（方案 B）

┌──────────────────────────────────────┐
│ IP 换绑监控                    [正常] │
│  103.216.72.14                        │
│ ┌──────┬──────┬──────┬──────┐        │
│ │总换绑 │ 今日 │成功率 │代理池 │        │
│ └──────┴──────┴──────┴──────┘        │
│ ── 换绑历史 ─────────────────        │
│ ● 12:03 限流触发 · 98.xx → 103.x     │
│ ● 11:47 手动切换 · 45.xx → 98.xx     │
│                                      │
│ [🔄 立即换 IP]   [⏸ 暂停自动]        │
└──────────────────────────────────────┘
"""

import re
import time
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from config import get_config
from proxy_pool import get_manager
from state import SwitchEvent, get_state


# ── 主题色辅助（对齐 templates.md 骨架） ──────────────────


def _text_color(secondary: bool = False) -> str:
    try:
        from qfluentwidgets import isDarkTheme

        if isDarkTheme():
            return "rgba(255,255,255,0.55)" if secondary else "rgba(255,255,255,0.9)"
    except Exception:
        pass
    return "rgba(0,0,0,0.45)" if secondary else "rgba(0,0,0,0.85)"


def _make_style(
    color: str, font_family: str = "", font_size: int = 0, extra: str = ""
) -> str:
    parts = [f"color: {color};"]
    if font_family:
        parts.append(f"font-family: '{font_family}'")
    if font_size:
        parts.append(f"font-size: {font_size}px;")
    if extra:
        parts.append(extra)
    return " ".join(parts)


class IPSwitcherCard(QWidget):
    """IP 换绑监控仪表盘浮动卡片"""

    closed = pyqtSignal()

    # ── 状态徽章映射 ──
    _BADGE = {
        "ok": ("正常", "#22c55e"),
        "switching": ("限流切换中", "#eab308"),
        "error": ("代理池异常", "#ef4444"),
        "paused": ("已暂停", "#6b7280"),
        "stopped": ("代理池未启动", "#9ca3af"),
    }

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._is_busy = False
        self._state = get_state()
        self._config = get_config()
        self._setup_ui()
        self._connect_signals()

    # ── 上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        self._apply_latest_theme()
        self._refresh_all()
        self.setVisible(True)

    def _apply_latest_theme(self):
        if self._context_provider is None:
            return
        try:
            ctx = self._context_provider()
        except Exception:
            return
        try:
            ff = ctx.get("font_family", "Microsoft YaHei")
            fs = ctx.get("font_size", 14)
            tc = ctx.get("colors", {}).get("text_primary", "") or _text_color()
            tcs = ctx.get("colors", {}).get("text_secondary", "") or _text_color(
                secondary=True
            )
            self.setFont(QFont(ff, fs if fs else 14))
            # 刷新所有 QLabel 颜色（保留原有 font-size）
            for lb in self.findChildren(QLabel):
                try:
                    ss = lb.styleSheet()
                    if not ss:
                        continue
                    new_ss = re.sub(r"color:\s*[^;]+;", f"color: {tc};", ss)
                    lb.setStyleSheet(new_ss)
                except RuntimeError:
                    pass
            self._ip_label.setStyleSheet(
                _make_style(tc, ff, (fs or 14) + 6, "font-weight: 700;")
            )
            self._badge_label.setStyleSheet(self._badge_style())
            # 历史行使用次级色
            for lb in self._history_labels:
                try:
                    lb.setStyleSheet(_make_style(tcs, ff, max(fs - 2, 10)))
                except RuntimeError:
                    pass
            self._switch_btn.setStyleSheet(self._switch_btn_style())
            self._auto_btn.setStyleSheet(self._auto_btn_style())
        except Exception:
            logger.exception("[ip-switcher] 主题应用异常")

    # ── 样式 ──

    def _badge_state(self):
        pool = self._state.pool_state()
        if pool == "error":
            return self._BADGE["error"]
        if pool == "stopped":
            return self._BADGE["stopped"]
        if not self._state.is_auto_switch():
            return self._BADGE["paused"]
        return self._BADGE["ok"]

    def _badge_style(self) -> str:
        _, color = self._badge_state()
        return (
            f"background: {color}22; color: {color}; border-radius: 10px;"
            f" padding: 2px 10px; font-size: 12px;"
        )

    def _switch_btn_style(self) -> str:
        return (
            "QPushButton { background: #4f46e5; color: white; border: none;"
            " border-radius: 6px; padding: 0 10px; min-height: 32px; }"
            "QPushButton:hover { background: #6366f1; }"
            "QPushButton:disabled { background: #a5b4fc; }"
        )

    def _auto_btn_style(self) -> str:
        return (
            "QPushButton { background: rgba(128,128,128,0.12); color: "
            + _text_color()
            + "; border: 1px solid rgba(128,128,128,0.2); border-radius: 6px;"
            " padding: 0 10px; min-height: 32px; }"
        )

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumSize(360, 320)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("IPSwitcherCard { background: transparent; }")
        self._history_labels: list = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 头部 ──
        header = QWidget(self)
        hly = QHBoxLayout(header)
        hly.setContentsMargins(16, 12, 16, 4)
        title = QLabel("🌐 IP 换绑监控", header)
        title.setStyleSheet(_make_style(_text_color(), extra="font-weight: 600;"))
        hly.addWidget(title)
        hly.addStretch(1)
        self._badge_label = QLabel("", header)
        hly.addWidget(self._badge_label)
        root.addWidget(header)

        # 分隔线
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: rgba(128,128,128,0.15); max-height: 1px;")
        root.addWidget(sep)

        # ── 当前出口 IP ──
        ip_wrap = QWidget(self)
        ily = QVBoxLayout(ip_wrap)
        ily.setContentsMargins(16, 10, 16, 4)
        ip_hint = QLabel("当前出口 IP", ip_wrap)
        ip_hint.setStyleSheet(_make_style(_text_color(secondary=True), font_size=11))
        ily.addWidget(ip_hint)
        self._ip_label = QLabel("未使用", ip_wrap)
        self._ip_label.setStyleSheet(
            _make_style(_text_color(), font_size=20, extra="font-weight: 700;")
        )
        ily.addWidget(self._ip_label)
        root.addWidget(ip_wrap)

        # ── 统计格 ×4 ──
        stats = QWidget(self)
        sly = QHBoxLayout(stats)
        sly.setContentsMargins(16, 8, 16, 4)
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
            val.setStyleSheet(_make_style(_text_color(), extra="font-weight: 700;"))
            name_lb = QLabel(name, cell)
            name_lb.setAlignment(Qt.AlignCenter)
            name_lb.setStyleSheet(
                _make_style(_text_color(secondary=True), font_size=10)
            )
            cl.addWidget(val)
            cl.addWidget(name_lb)
            self._stat_labels[key] = val
            sly.addWidget(cell, 1)
        root.addWidget(stats)

        # ── 换绑历史 ──
        hist_hint = QLabel("换绑历史", self)
        hist_hint.setContentsMargins(16, 8, 16, 2)
        hist_hint.setStyleSheet(_make_style(_text_color(secondary=True), font_size=11))
        root.addWidget(hist_hint)

        self._history_box = QWidget(self)
        self._history_layout = QVBoxLayout(self._history_box)
        self._history_layout.setContentsMargins(16, 0, 16, 4)
        self._history_layout.setSpacing(2)
        root.addWidget(self._history_box)

        # ── 操作按钮 ──
        btns = QWidget(self)
        bly = QHBoxLayout(btns)
        bly.setContentsMargins(16, 8, 16, 12)
        bly.setSpacing(8)
        self._switch_btn = QPushButton("🔄 立即换 IP", btns)
        self._switch_btn.setCursor(Qt.PointingHandCursor)
        self._switch_btn.setStyleSheet(self._switch_btn_style())
        self._switch_btn.clicked.connect(self._on_manual_switch)
        bly.addWidget(self._switch_btn, 1)
        self._auto_btn = QPushButton("⏸ 暂停自动", btns)
        self._auto_btn.setCursor(Qt.PointingHandCursor)
        self._auto_btn.setStyleSheet(self._auto_btn_style())
        self._auto_btn.clicked.connect(self._on_toggle_auto)
        bly.addWidget(self._auto_btn, 1)
        root.addWidget(btns)

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
        # 历史（最近 6 条）
        self._render_history(st.history()[:6])
        # 按钮
        self._auto_btn.setText(
            "▶ 恢复自动" if not st.is_auto_switch() else "⏸ 暂停自动"
        )

    def _render_history(self, events):
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._history_labels = []
        if not events:
            empty = QLabel("暂无换绑记录", self._history_box)
            empty.setStyleSheet(_make_style(_text_color(secondary=True), font_size=12))
            self._history_layout.addWidget(empty)
            return
        for ev in events:
            lb = self._make_history_row(ev)
            self._history_layout.addWidget(lb)
            self._history_labels.append(lb)

    def _make_history_row(self, ev: SwitchEvent) -> QLabel:
        t = time.strftime("%H:%M", time.localtime(ev.timestamp))
        trigger = "限流触发" if ev.trigger == "ratelimit" else "手动切换"
        dot = "🔴" if ev.trigger == "ratelimit" else "🔵"
        text = f"{dot} {t} {trigger} · {ev.old_ip} → {ev.new_ip}"
        lb = QLabel(text, self._history_box)
        lb.setStyleSheet(_make_style(_text_color(secondary=True), font_size=12))
        lb.setToolTip(
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ev.timestamp))}\n"
            f"触发: {trigger}\n{ev.note or ''}"
        )
        return lb

    # ── 操作 ──

    def _on_manual_switch(self):
        if self._is_busy:
            return
        self._is_busy = True
        self._switch_btn.setEnabled(False)
        self._switch_btn.setText("🔄 切换中…")
        try:
            from ip_redirect import _switch_ip_threadsafe

            new_ip = _switch_ip_threadsafe()
            if new_ip:
                self._switch_btn.setText("✅ 已切换")
            else:
                self._switch_btn.setText("❌ 切换失败")
        except Exception:
            logger.exception("[ip-switcher] 手动换 IP 异常")
            self._switch_btn.setText("❌ 切换失败")
        finally:
            QTimer.singleShot(2000, self._reset_btn)

    def _reset_btn(self):
        if not self._is_busy:
            return
        self._is_busy = False
        self._switch_btn.setEnabled(True)
        self._switch_btn.setText("🔄 立即换 IP")

    def _on_toggle_auto(self):
        st = self._state
        st.set_auto_switch(not st.is_auto_switch())
        self._config.set("auto_switch", st.is_auto_switch())
        self._refresh_all()

    # ── 生命周期 ──

    def deleteLater(self):
        self._disconnect_signals()
        super().deleteLater()

    def _on_close(self):
        self._disconnect_signals()
        self.setVisible(False)
        self.closed.emit()
