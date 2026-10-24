# -*- coding: utf-8 -*-
"""中国象棋设置卡 — 我方控制方式 / 红方模型 / 黑方模型

对齐 voice-reply 自绘设置卡范式（qfluentwidgets 控件主题自适应）：
旧实现用原生 QLabel/QComboBox 且标签硬编码白色文字，浅色主题下标签不可见、
下拉渲染成黑条；⚠️ hint 也是开发期遗留，一并移除。

模型列表来源：扫描 DriFox 主配置 LLM.SavedProviders → provider_name + 模型列表。
AI 决策走宿主 EngineSession（ui/ai_engine.py），模型值格式 "Provider:Model"，
空 = 沿用主程序当前会话模型。

UI 即时保存：任一控件变化 → PluginConfigStore().set_values() → 落盘 + 回调
ChessCard.update_config() 让对局立刻按新配置执行（无需重启插件）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

try:  # 宿主必然装有 qfluentwidgets；缺失时降级不注册卡
    from qfluentwidgets import (
        BodyLabel,
        ComboBox,
        ExpandSettingCard,
        FluentIcon,
        RadioButton,
    )
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore

try:
    from app.plugins.managers.plugin_config_store import (  # type: ignore
        PluginConfigStore,
    )
except Exception:  # noqa: BLE001
    PluginConfigStore = None  # type: ignore

PLUGIN_NAME = "chinese-chess"

DEFAULT_RED_CONTROL = "manual"

# 字段行宽度（模型串「Provider:model」较长，显式放宽防截断）
_FIELD_MIN_WIDTH = 320
_LABEL_MIN_WIDTH = 120


# ── 系统配置定位（参考 ip-switcher/ui/config.py discover_system_providers）──
def _get_drifox_root() -> Path:
    """定位 DriFox 应用根目录（.drifox/app.config 所在层）。"""
    candidates = []
    env = os.environ.get("DRIFOX_ROOT")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.home() / ".drifox")
    for c in candidates:
        if (c / "app.config").exists():
            return c
    return candidates[0]


def discover_system_providers() -> List[Dict[str, Any]]:
    """扫描 DriFox 主配置的 LLM.SavedProviders，返回 provider 信息列表。

    返回：[{provider_name, url, models: [str, ...]}, ...]
    失败（无主程序 / 解析异常）返回空列表。
    """
    cfg_path = _get_drifox_root() / "app.config"
    if not cfg_path.exists():
        return []
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        providers = (data.get("LLM", {}) or {}).get("SavedProviders", {}) or {}
        result: List[Dict[str, Any]] = []
        for _cid, p in providers.items():
            if not isinstance(p, dict):
                continue
            name = p.get("provider_name") or p.get("name") or ""
            url = p.get("API_URL") or ""
            models = list(p.get("模型列表") or []) or (
                [p.get("模型名称")] if p.get("模型名称") else []
            )
            if name:
                result.append({"provider_name": name, "url": url, "models": models})
        return result
    except (OSError, ValueError) as e:
        logger.debug(f"[chinese-chess] 系统模型发现失败: {e}")
        return []


def format_model_options(providers: List[Dict[str, Any]]) -> List[str]:
    """构造 'Provider:Model' 选项列表 + 占位（空 = 默认/主程序当前模型）。"""
    opts: List[str] = [""]
    for p in providers:
        pname = p.get("provider_name") or ""
        for m in p.get("models") or []:
            opts.append(f"{pname}:{m}")
    return opts


# ── 字段行：左侧标签 + 右侧控件（对齐主程序 PluginConfigCard._FieldRow）──


def _field_row(label_text: str, control, parent=None):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHBoxLayout, QWidget

    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(12)
    label = BodyLabel(label_text, row)
    label.setMinimumWidth(_LABEL_MIN_WIDTH)
    layout.addWidget(label, 0, Qt.AlignLeft | Qt.AlignVCenter)
    control.setMinimumWidth(_FIELD_MIN_WIDTH)
    layout.addWidget(control, 1, Qt.AlignRight)
    return row


# ── 设置卡本体 ──

_CardBase = ExpandSettingCard if ExpandSettingCard is not None else object  # type: ignore


class _ChessConfigCard(_CardBase):
    """中国象棋设置卡 — 我方控制方式 + 红方/对方模型选择

    构造签名 (parent=None) 满足 register_settings_card 的 widget_class 约定。
    """

    def __init__(self, parent: Optional[Any] = None) -> None:
        if ExpandSettingCard is None:
            raise RuntimeError("qfluentwidgets 不可用，无法构建中国象棋设置卡")
        icon = FluentIcon.GAME if hasattr(FluentIcon, "GAME") else FluentIcon.SETTING
        super().__init__(icon, "中国象棋", "控制方式 + 红黑方模型（立即生效）", parent)

        self.viewLayout.setContentsMargins(48, 8, 48, 8)
        self.viewLayout.setSpacing(4)

        self._on_change_external: Optional[Callable[[dict], None]] = None
        self._providers = discover_system_providers()
        opts = format_model_options(self._providers)

        # ── 我方控制方式（单选）──
        control_row_widget = None
        from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QWidget

        control_row_widget = QWidget(self.view)
        ctrl_layout = QHBoxLayout(control_row_widget)
        ctrl_layout.setContentsMargins(0, 4, 0, 4)
        ctrl_layout.setSpacing(12)
        self._rb_manual = RadioButton("🖱 手动操作", control_row_widget)
        self._rb_ai = RadioButton("🤖 AI 控制", control_row_widget)
        self._rb_manual.setChecked(DEFAULT_RED_CONTROL == "manual")
        self._rb_ai.setChecked(DEFAULT_RED_CONTROL == "ai")
        self._control_group = QButtonGroup(self)
        self._control_group.addButton(self._rb_manual, id=0)
        self._control_group.addButton(self._rb_ai, id=1)
        ctrl_layout.addWidget(self._rb_manual)
        ctrl_layout.addWidget(self._rb_ai)
        ctrl_layout.addStretch(1)
        self.viewLayout.addWidget(_field_row("我方控制方式", control_row_widget, self.view))

        # ── 模型选择（填充与回显期间 blockSignals，避免误触发 _save）──
        from PySide6.QtCore import QSignalBlocker

        self._red_model_combo = ComboBox(self.view)
        self._black_model_combo = ComboBox(self.view)
        for combo in (self._red_model_combo, self._black_model_combo):
            with QSignalBlocker(combo):
                combo.addItems(opts)
                combo.setCurrentIndex(0)
        self._red_model_combo.currentIndexChanged.connect(self._on_red_model_changed)
        self._black_model_combo.currentIndexChanged.connect(self._on_black_model_changed)

        self.viewLayout.addWidget(_field_row("我方模型（红方）", self._red_model_combo, self.view))
        self.viewLayout.addWidget(_field_row("对方模型（黑方）", self._black_model_combo, self.view))

        # 回显当前生效配置
        self._echo()

    # ── 折叠动画（对齐主程序 PluginConfigCard 的处理，防卡片关不上）──

    def _adjustViewSize(self):
        h = self.viewLayout.sizeHint().height()
        try:
            self.spaceWidget.setFixedHeight(0)
        except Exception:  # noqa: BLE001 — 旧版宿主无该成员时跳过
            pass
        self.setFixedHeight(self.card.height() + (h if self.isExpand else 0))

    def setExpand(self, isExpand: bool):
        if self.isExpand == isExpand:
            return
        from PySide6.QtWidgets import QApplication

        self.isExpand = isExpand
        self.setProperty("isExpand", isExpand)
        self.setStyle(QApplication.style())
        self.card.expandButton.setExpand(isExpand)
        self._adjustViewSize()

    # ── 对外 ──

    def register_change_callback(self, cb: Callable[[dict], None]) -> None:
        """注册外部回调（ChessCard.update_config）。"""
        self._on_change_external = cb

    def _echo(self) -> None:
        """从 PluginConfigStore 回显当前生效配置（blockSignals 防回环保存）。"""
        if PluginConfigStore is None:
            return
        try:
            from PySide6.QtCore import QSignalBlocker

            store = PluginConfigStore()
            v = store.get(PLUGIN_NAME, "red_control")
            if v not in ("manual", "ai"):
                v = DEFAULT_RED_CONTROL
            self._rb_manual.setChecked(v == "manual")
            self._rb_ai.setChecked(v == "ai")

            with QSignalBlocker(self._red_model_combo):
                red_model = str(store.get(PLUGIN_NAME, "red_model") or "").replace("__default__", "")
                idx = self._red_model_combo.findText(red_model)
                self._red_model_combo.setCurrentIndex(idx if idx >= 0 else 0)

            with QSignalBlocker(self._black_model_combo):
                black_model = str(store.get(PLUGIN_NAME, "black_model") or "").replace("__default__", "")
                idx = self._black_model_combo.findText(black_model)
                self._black_model_combo.setCurrentIndex(idx if idx >= 0 else 0)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[chinese-chess] 设置卡回显失败: {e}")

    def _save(self, partial: Dict[str, Any]) -> None:
        """落盘 + 通知外部回调。"""
        if PluginConfigStore is None:
            logger.warning("[chinese-chess] PluginConfigStore 未注入，仅通知回调")
        else:
            try:
                PluginConfigStore().set_values(PLUGIN_NAME, partial)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[chinese-chess] 配置保存失败: {e}")
        if self._on_change_external is not None:
            try:
                self._on_change_external(partial)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[chinese-chess] 配置变更回调失败: {e}")

    # 槽函数 ──

    def _on_control_changed(self, _btn) -> None:
        v = "ai" if self._rb_ai.isChecked() else "manual"
        self._save({"red_control": v})

    def _on_red_model_changed(self, index: int) -> None:
        self._save({"red_model": self._red_model_combo.itemText(index) or ""})

    def _on_black_model_changed(self, index: int) -> None:
        self._save({"black_model": self._black_model_combo.itemText(index) or ""})


# ── 注册入口 ──

def _register_chess_config_card(registry) -> None:
    """注册中国象棋设置卡。失败时优雅降级（警告日志）。"""
    try:
        registry.register_settings_card(
            PLUGIN_NAME,
            f"{PLUGIN_NAME}-config",
            "中国象棋",
            _ChessConfigCard,
            priority=1,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[chinese-chess] 设置卡注册失败（降级 E1 自动卡）: {e}")
