# -*- coding: utf-8 -*-
"""speak-up 设置页 — 独立设置大 tab（register_settings_tab）。

为什么不用 E1 自动卡：配置项 16 个，塞进「设置 → 插件」的卡片流会挤成一条长龙，
而且有「峰谷/时机/冷却」三组语义，需要分组与就地说明。

布局口径（对齐主程序设置卡）：
- 每行「定宽 label（120） + 控件撑满剩余宽度」
- 数值控件用 SpinBox，百分比用整数（qfluentwidgets SpinBox 只收 int）
- 分三组：基础 / 命中线 / 时机与冷却，每组一个 StrongBodyLabel 小节标题
- 底部动作行：左「演练一次」右「恢复默认」
- 保存即时生效（值变就写盘，不需要「保存」按钮）
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from loguru import logger  # noqa: E402

from speakup_core.config import DEFAULTS, FIELD_SPECS, load_config, reset_config, save_config  # noqa: E402

PLUGIN_NAME = "speak-up"
_LABEL_MIN_WIDTH = 120

_UI_AVAILABLE = False
try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
    from qfluentwidgets import (  # noqa: F401
        BodyLabel,
        CaptionLabel,
        PushButton,
        SpinBox,
        StrongBodyLabel,
        SwitchButton,
        TextEdit,
    )

    _UI_AVAILABLE = True
except Exception:  # noqa: BLE001 - 宿主缺 qfluentwidgets 时不注册
    QWidget = object  # type: ignore


if _UI_AVAILABLE:

    class _Row(QWidget):
        """字段行：定宽 label + 控件撑满。"""

        def __init__(self, label_text: str, control: Any, hint: str = "", parent=None):
            super().__init__(parent)
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 4, 0, 4)
            outer.setSpacing(2)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(12)
            label = BodyLabel(label_text, self)
            label.setMinimumWidth(_LABEL_MIN_WIDTH)
            row.addWidget(label, 0, Qt.AlignLeft | Qt.AlignVCenter)
            row.addWidget(control, 1)
            outer.addLayout(row)
            if hint:
                tip = CaptionLabel(hint, self)
                tip.setWordWrap(True)
                # 提示文字左侧留出 label 宽度，视觉上挂在控件下方
                indent = QHBoxLayout()
                indent.setContentsMargins(_LABEL_MIN_WIDTH + 12, 0, 0, 0)
                indent.addWidget(tip)
                outer.addLayout(indent)

    class SpeakUpSettingsPage(QWidget):
        """主动搭话完整配置页（宿主懒实例化，构造签名 (parent=None)）。"""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._controls: Dict[str, Any] = {}
            self._loading = False
            self._build_ui()
            self.reload()

        # ── 构建 ────────────────────────────────────

        def _build_ui(self) -> None:
            # 宿主已把本页放进 QScrollArea 的内容层（见 llm_settings_card._build_plugin_tab_page），
            # 这里不能再套一层滚动区，否则双层滚动条互相抢滚轮。
            layout = QVBoxLayout(self)
            layout.setContentsMargins(24, 16, 24, 16)
            layout.setSpacing(6)

            layout.addWidget(self._section("基础"))
            layout.addWidget(self._switch_row("enabled", "总开关", "关掉后定时器完全不动"))
            layout.addWidget(
                self._switch_row(
                    "dry_run",
                    "试运行（只记账不真发）",
                    "默认开着：掷中了也只记账。先看几轮记账确认口径再关掉",
                )
            )
            layout.addWidget(
                self._int_row("interval_minutes", "掷骰间隔（分钟）", "掷骰本身不花任何 token")
            )
            layout.addWidget(self._text_row("trigger_text", "触发文案", "真开口时送进会话的那句内心话"))

            layout.addSpacing(12)
            layout.addWidget(self._section("命中线"))
            layout.addWidget(
                self._int_row("peak_hit", "峰时命中线（%）", "工作日 09:00-12:00、14:00-18:00 用这一格")
            )
            layout.addWidget(self._int_row("valley_hit", "谷时命中线（%）", "其余时段（含周末全天）用这一格"))
            layout.addWidget(
                self._int_row("miss_bonus", "没中加成（%/次）", "每没掷中一次，下次命中线加这么多。0 = 关掉")
            )
            layout.addWidget(self._int_row("bonus_cap", "加成上限（%）", "攒的加成最多加到这么多"))

            layout.addSpacing(12)
            layout.addWidget(self._section("时机与冷却"))
            layout.addWidget(
                self._int_row("near_minutes", "近阈值（分钟）", "距用户上次说话小于此数，命中线乘近因子")
            )
            layout.addWidget(
                self._int_row("near_factor_pct", "近因子（%）", "15 表示 ×0.15。越小越不爱在用户刚说完时插话")
            )
            layout.addWidget(
                self._int_row("far_minutes", "远阈值（分钟）", "距用户上次说话大于此数，命中线乘远因子")
            )
            layout.addWidget(self._int_row("far_factor_pct", "远因子（%）", "150 表示 ×1.5"))
            layout.addWidget(
                self._int_row(
                    "cooldown_minutes", "搭话冷却（分钟）", "自己刚开过口之后的冷却。0 = 不冷却"
                )
            )

            layout.addSpacing(12)
            layout.addWidget(self._section("安静时段"))
            layout.addWidget(
                self._int_row("quiet_start_hour", "起（小时）", "含起不含止。起 = 止 表示不启用安静时段")
            )
            layout.addWidget(self._int_row("quiet_end_hour", "止（小时）", "可跨午夜（23~7）"))

            layout.addSpacing(16)
            actions = QHBoxLayout()
            actions.setContentsMargins(0, 0, 0, 0)
            actions.setSpacing(8)
            self._dry_btn = PushButton("演练一次", self)
            self._dry_btn.clicked.connect(lambda: self._manual("演练"))
            self._real_btn = PushButton("真发一次", self)
            self._real_btn.clicked.connect(lambda: self._manual("真发"))
            actions.addWidget(self._dry_btn)
            actions.addWidget(self._real_btn)
            actions.addStretch(1)
            reset_btn = PushButton("恢复默认", self)
            reset_btn.setFixedWidth(120)
            reset_btn.clicked.connect(self._on_reset)
            actions.addWidget(reset_btn)
            layout.addLayout(actions)

            self._status = CaptionLabel("", self)
            self._status.setWordWrap(True)
            layout.addWidget(self._status)
            layout.addStretch(1)

        @staticmethod
        def _section(title: str) -> Any:
            label = StrongBodyLabel(title)
            label.setContentsMargins(0, 8, 0, 0)
            return label

        def _switch_row(self, key: str, label: str, hint: str) -> Any:
            switch = SwitchButton(self)
            switch.setOnText("开")
            switch.setOffText("关")
            switch.checkedChanged.connect(lambda _v, _k=key: self._save_field(_k))
            self._controls[key] = switch
            return _Row(label, switch, hint, self)

        def _int_row(self, key: str, label: str, hint: str) -> Any:
            spec = FIELD_SPECS.get(key)
            spin = SpinBox(self)
            if spec is not None:
                _kind, low, high = spec
                spin.setRange(int(low), int(high))
            spin.valueChanged.connect(lambda _v, _k=key: self._save_field(_k))
            self._controls[key] = spin
            return _Row(label, spin, hint, self)

        def _text_row(self, key: str, label: str, hint: str) -> Any:
            edit = TextEdit(self)
            edit.setMinimumHeight(72)
            edit.setPlaceholderText("改成你自己的口吻")
            edit.textChanged.connect(lambda _k=key: self._save_field(_k))
            self._controls[key] = edit
            return _Row(label, edit, hint, self)

        # ── 回显与保存 ───────────────────────────────

        def reload(self) -> None:
            """把存储值写回控件（blockSignals 防回显触发保存）。"""
            config = load_config()
            self._loading = True
            try:
                for key, control in self._controls.items():
                    control.blockSignals(True)
                    try:
                        if key in ("enabled", "dry_run"):
                            control.setChecked(bool(getattr(config, key)))
                        elif key == "trigger_text":
                            control.setPlainText(str(getattr(config, key)))
                            control.moveCursor(control.textCursor().Start)
                        elif key in FIELD_SPECS:
                            control.setValue(int(getattr(config, key)))
                    finally:
                        control.blockSignals(False)
            finally:
                self._loading = False
            self._refresh_status()

        def _save_field(self, key: str) -> None:
            if self._loading:
                return
            control = self._controls.get(key)
            if control is None:
                return
            try:
                if key in ("enabled", "dry_run"):
                    value: Any = bool(control.isChecked())
                elif key == "trigger_text":
                    value = control.toPlainText().strip()
                else:
                    value = int(control.value())
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[speak-up] 读控件 {key} 失败: {e}")
                return
            save_config({key: value})
            self._refresh_status(f"已保存 {key} = {value}")

        def _on_reset(self) -> None:
            reset_config()
            self.reload()
            self._refresh_status("已恢复默认")

        # ── 手动触发 ─────────────────────────────────

        def _manual(self, mode: str) -> None:
            try:
                from speakup_core.runtime import get_runner  # type: ignore

                runner = get_runner()
                result = runner.roll(source="手动", mode=mode)
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[speak-up] 手动 {mode} 失败: {e}")
                self._refresh_status(f"{mode}失败：{e}")
                return
            self._refresh_status(result.get("text", ""))

        def _refresh_status(self, message: Optional[str] = None) -> None:
            try:
                from speakup_core.runtime import get_runner  # type: ignore

                snap = get_runner().state_snapshot()
                parts = [
                    f"{'运行中' if snap['running'] else '已停止'}",
                    f"间隔 {snap['interval_seconds'] // 60} 分钟"
                    if snap["interval_seconds"]
                    else "间隔未起算",
                    f"连没中 {snap['misses']} 次",
                ]
                base = " · ".join(parts)
            except Exception:  # noqa: BLE001
                base = "运行时未就绪"
            self._status.setText(f"{message}　{base}" if message else base)


def get_settings_page_class():
    """返回设置页类；UI 栈不可用时返回 None（宿主据此跳过注册）。"""
    return SpeakUpSettingsPage if _UI_AVAILABLE else None
