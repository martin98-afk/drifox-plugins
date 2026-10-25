# -*- coding: utf-8 -*-
"""中国象棋设置卡 — 我方控制方式 / 红黑方服务商与模型（两级下拉）

对齐 voice-reply 自绘设置卡范式（qfluentwidgets 控件主题自适应）：
旧实现用原生 QLabel/QComboBox 且标签硬编码白色文字，浅色主题下标签不可见、
下拉渲染成黑条；⚠️ hint 也是开发期遗留，一并移除。

服务商/模型分开选（对齐 vision-proxy）：数据源首选 provider.list /
model.enumerate 能力（内存态，随选随取），能力不可用回退扫描主配置
LLM.SavedProviders 非密钥字段。AI 决策走宿主 EngineSession（ui/ai_engine.py），
红黑方各自存 provider/model 两键，均空 = 沿用主程序当前会话模型。

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


def _caps(name: str) -> Any:
    """取宿主能力（设置卡无 ctx，走 caps_for 按插件名解析到活跃窗口）。"""
    try:
        from app.plugins.sdk import caps_for

        return caps_for(name, plugin=PLUGIN_NAME, surface="ui")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[chinese-chess] 取能力 {name} 失败: {e}")
        return None


def _load_provider_entries() -> List[Dict[str, Any]]:
    """内存态服务商清单（provider.list 能力）；不可用返回 []（调用方回退磁盘扫描）。"""
    fn = _caps("provider.list")
    if not callable(fn):
        return []
    try:
        items = fn() or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[chinese-chess] provider.list 调用失败: {e}")
        return []
    return [p for p in items if isinstance(p, dict)]


def _load_models_of(provider_id: str) -> List[str]:
    """指定服务商的模型名列表（model.enumerate 能力）；不可用返回 []。"""
    if not provider_id:
        return []
    fn = _caps("model.enumerate")
    if not callable(fn):
        return []
    try:
        items = fn(provider_id) or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[chinese-chess] model.enumerate 调用失败: {e}")
        return []
    return [str(m.get("name") or "") for m in items if isinstance(m, dict) and m.get("name")]


def _load_provider_tree() -> List[tuple]:
    """服务商两级下拉第一级选项：[(display, key)]。

    首选 provider.list（内存态，key=config_id）；能力不可用回退
    discover_system_providers 磁盘扫描（key=provider_name，五级解析均可吃）。
    """
    out: List[tuple] = []
    for p in _load_provider_entries():
        pid = str(p.get("id") or "")
        if not pid:
            continue
        label = str(p.get("display_name") or pid)
        if p.get("is_current"):
            label = f"{label}（当前）"
        out.append((label, pid))
    if out:
        return out
    seen: set = set()
    for p in discover_system_providers():
        name = str(p.get("provider_name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append((name, name))
    return out


def _load_models_by_tree(provider_key: str) -> List[str]:
    """服务商两级下拉第二级选项：模型名列表。首选 model.enumerate，回退磁盘。"""
    models = _load_models_of(provider_key)
    if models:
        return models
    for p in discover_system_providers():
        if str(p.get("provider_name") or "") != provider_key:
            continue
        return [str(m) for m in (p.get("models") or []) if str(m).strip()]
    return []


# ── 字段行：左侧标签 + 右侧控件（对齐主程序 PluginConfigCard._FieldRow）──


def _field_row(label_text: str, control, parent=None):
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QHBoxLayout, QWidget

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

        # ── 我方控制方式（单选）──
        control_row_widget = None
        from PyQt5.QtWidgets import QButtonGroup, QHBoxLayout, QWidget

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

        # ── 红黑方服务商/模型两级下拉（对齐 vision-proxy：换服务商重填模型）──
        from PyQt5.QtCore import QSignalBlocker

        self._providers = _load_provider_tree()
        self._red_provider_combo = ComboBox(self.view)
        self._red_model_combo = ComboBox(self.view)
        self._black_provider_combo = ComboBox(self.view)
        self._black_model_combo = ComboBox(self.view)
        for combo, tip in (
            (self._red_provider_combo, "红方 AI 服务商。两键均空 = 沿用主程序当前会话模型。"),
            (self._red_model_combo, "红方 AI 模型（清单随上方服务商联动）。"),
            (self._black_provider_combo, "黑方 AI 服务商。两键均空 = 沿用主程序当前会话模型。"),
            (self._black_model_combo, "黑方 AI 模型（清单随上方服务商联动）。"),
        ):
            combo.setMaxVisibleItems(10)
            combo.setToolTip(tip)
        for combo in (self._red_provider_combo, self._black_provider_combo):
            with QSignalBlocker(combo):
                for label, key in self._providers:
                    combo.addItem(label, userData=key)
        self._red_provider_combo.currentIndexChanged.connect(self._on_red_provider_changed)
        self._red_model_combo.currentIndexChanged.connect(self._on_red_model_changed)
        self._black_provider_combo.currentIndexChanged.connect(self._on_black_provider_changed)
        self._black_model_combo.currentIndexChanged.connect(self._on_black_model_changed)

        self.viewLayout.addWidget(_field_row("我方服务商（红方）", self._red_provider_combo, self.view))
        self.viewLayout.addWidget(_field_row("我方模型（红方）", self._red_model_combo, self.view))
        self.viewLayout.addWidget(_field_row("对方服务商（黑方）", self._black_provider_combo, self.view))
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
        from PyQt5.QtWidgets import QApplication

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
            from PyQt5.QtCore import QSignalBlocker

            store = PluginConfigStore()
            v = store.get(PLUGIN_NAME, "red_control")
            if v not in ("manual", "ai"):
                v = DEFAULT_RED_CONTROL
            self._rb_manual.setChecked(v == "manual")
            self._rb_ai.setChecked(v == "ai")

            # 旧格式兼容：「服务商:模型」合并值存过 → 拆开回显，不丢用户配置
            red_provider = str(store.get(PLUGIN_NAME, "red_provider") or "").replace("__default__", "")
            red_model = str(store.get(PLUGIN_NAME, "red_model") or "").replace("__default__", "")
            if not red_provider and ":" in red_model:
                red_provider, red_model = red_model.split(":", 1)
                red_provider, red_model = red_provider.strip(), red_model.strip()
            black_provider = str(store.get(PLUGIN_NAME, "black_provider") or "").replace("__default__", "")
            black_model = str(store.get(PLUGIN_NAME, "black_model") or "").replace("__default__", "")
            if not black_provider and ":" in black_model:
                black_provider, black_model = black_model.split(":", 1)
                black_provider, black_model = black_provider.strip(), black_model.strip()

            with QSignalBlocker(self._red_provider_combo):
                idx = self._red_provider_combo.findData(red_provider)
                if idx < 0 and red_provider:
                    # 已存值不在清单里（服务商被删/能力降级）：插到首位保住它
                    self._red_provider_combo.insertItem(0, red_provider, userData=red_provider)
                    idx = 0
                self._red_provider_combo.setCurrentIndex(max(0, idx))
            self._fill_models(self._red_model_combo, str(self._red_provider_combo.currentData() or ""), red_model)

            with QSignalBlocker(self._black_provider_combo):
                idx = self._black_provider_combo.findData(black_provider)
                if idx < 0 and black_provider:
                    self._black_provider_combo.insertItem(0, black_provider, userData=black_provider)
                    idx = 0
                self._black_provider_combo.setCurrentIndex(max(0, idx))
            self._fill_models(self._black_model_combo, str(self._black_provider_combo.currentData() or ""), black_model)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[chinese-chess] 设置卡回显失败: {e}")

    @staticmethod
    def _fill_models(model_combo, provider_key: str, selected: str = "") -> None:
        """按服务商重填模型下拉；首项「当前模型」= 空。selected 不在清单时插到其后保住。"""
        from PyQt5.QtCore import QSignalBlocker

        with QSignalBlocker(model_combo):
            model_combo.clear()
            model_combo.addItem("当前模型", userData="")
            for name in _load_models_by_tree(provider_key):
                model_combo.addItem(name, userData=name)
            idx = model_combo.findData(selected)
            if idx < 0 and selected:
                model_combo.insertItem(1, selected, userData=selected)
                idx = 1
            model_combo.setCurrentIndex(max(0, idx))

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

    def _on_red_provider_changed(self, _index: int) -> None:
        key = str(self._red_provider_combo.currentData() or "")
        self._save({"red_provider": key})
        # 换服务商后模型清单全变，清空模型值避免指向不存在的模型
        self._save({"red_model": ""})
        self._fill_models(self._red_model_combo, key)

    def _on_red_model_changed(self, index: int) -> None:
        self._save({"red_model": self._red_model_combo.itemData(index) or ""})

    def _on_black_provider_changed(self, _index: int) -> None:
        key = str(self._black_provider_combo.currentData() or "")
        self._save({"black_provider": key})
        self._save({"black_model": ""})
        self._fill_models(self._black_model_combo, key)

    def _on_black_model_changed(self, index: int) -> None:
        self._save({"black_model": self._black_model_combo.itemData(index) or ""})


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
