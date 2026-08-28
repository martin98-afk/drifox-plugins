# -*- coding: utf-8 -*-
"""中国象棋设置卡 — 我方控制方式 / 红方模型 / 黑方模型

注册时机：register_ui() 时调 _register_chess_config_card()，
注册失败（旧版主程序无此扩展点）时 print 警告降级。

模型列表来源：参照 plugins/ip-switcher/ui/config.py:123 discover_system_providers()
扫描 DriFox 主应用配置 LLM.SavedProviders → {provider_name, models, ...}

UI 即时保存：任一控件变化 → PluginConfigStore().set_values() → 落盘 + 回调
ChessCard.update_config() 让对局立刻按新配置执行（无需重启插件）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

# ── 模块级 try/except：qfluentwidgets / 主程序 API 容错 ──
try:
    from qfluentwidgets import ExpandSettingCard  # type: ignore
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


# ── 系统配置定位（参考 ip-switcher/ui/config.py:101 discover_system_providers）──
def _get_drifox_root() -> Path:
    """定位 DriFox 应用根目录（.drifox/app.config 所在层）。"""
    candidates = []
    env = os.environ.get("DRIFOX_ROOT")
    if env:
        candidates.append(Path(env))
    # Windows 常见位置
    candidates.append(Path.home() / ".drifox")
    # Linux/Mac 也用 ~/.drifox（上面已包含）
    for c in candidates:
        if (c / "app.config").exists():
            return c
    # 回退到第一个候选，调用方会判定文件不存在
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
    """构造 'Provider:Model' 选项列表 + 占位 ('默认 / 系统当前模型')。"""
    opts: List[str] = [""]  # 占位：空 = 默认/主程序当前模型
    for p in providers:
        pname = p.get("provider_name") or ""
        for m in p.get("models") or []:
            opts.append(f"{pname}:{m}")
    return opts


# ── 设置卡本体 ──

_CardBase = ExpandSettingCard if ExpandSettingCard is not None else object  # type: ignore


class _ChessConfigCard(_CardBase):
    """中国象棋设置卡 — 我方控制方式 + 红方/对方模型选择

    构造签名 (parent=None) 满足 register_settings_card 的 widget_class 约定。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        if ExpandSettingCard is not None:
            try:
                from qfluentwidgets import FluentIcon  # type: ignore

                super().__init__(
                    FluentIcon.GAME if hasattr(FluentIcon, "GAME") else FluentIcon.SETTING,
                    "中国象棋",
                    "控制方式 + 红黑方模型（立即生效）",
                    parent,
                )
            except Exception:
                try:
                    super().__init__("中国象棋", "控制方式 + 红黑方模型（立即生效）", parent)
                except Exception:
                    pass

        # 嵌入式子面板
        if ExpandSettingCard is not None and hasattr(self, "viewLayout"):
            try:
                self.viewLayout.setContentsMargins(36, 8, 36, 8)
                self.viewLayout.setSpacing(8)
            except Exception:
                pass

        # 前置初始化：必须在任何信号连接/_echo 之前（_echo 可能触发 _save）
        self._on_change_external: Optional[Callable[[dict], None]] = None

        self._providers = discover_system_providers()
        opts = format_model_options(self._providers)

        # ── 我方控制方式（单选）──
        self._red_control_label = QLabel("我方控制方式")
        try:
            self._red_control_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px;")
        except Exception:
            pass

        control_row = QWidget()
        ctrl_layout = QHBoxLayout(control_row)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(12)
        self._rb_manual = QRadioButton("🖱 手动操作")
        self._rb_ai = QRadioButton("🤖 AI 控制")
        self._rb_manual.setChecked(DEFAULT_RED_CONTROL == "manual")
        self._rb_ai.setChecked(DEFAULT_RED_CONTROL == "ai")
        self._control_group = QButtonGroup(self)
        self._control_group.addButton(self._rb_manual, id=0)
        self._control_group.addButton(self._rb_ai, id=1)
        self._control_group.buttonClicked.connect(self._on_control_changed)
        ctrl_layout.addWidget(self._rb_manual)
        ctrl_layout.addWidget(self._rb_ai)
        ctrl_layout.addStretch(1)

        # ── 模型选择 ──
        self._red_model_label = QLabel("我方模型（红方）")
        self._black_model_label = QLabel("对方模型（黑方）")
        try:
            self._red_model_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px;")
            self._black_model_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 12px;")
        except Exception:
            pass

        self._red_model_combo = QComboBox()
        self._red_model_combo.addItems(opts)
        self._red_model_combo.setCurrentText("")
        self._red_model_combo.currentTextChanged.connect(self._on_red_model_changed)

        self._black_model_combo = QComboBox()
        self._black_model_combo.addItems(opts)
        self._black_model_combo.setCurrentText("")
        self._black_model_combo.currentTextChanged.connect(self._on_black_model_changed)

        # 顶部说明
        self._hint_label = QLabel("⚠️ 模型列表来自主程序 LLM.SavedProviders；为空时回退到主程序当前会话模型")
        try:
            self._hint_label.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 11px;")
        except Exception:
            pass
        self._hint_label.setWordWrap(True)

        # ── 组装（兼容 ExpandSettingCard.viewLayout 与独立面板）──
        if ExpandSettingCard is not None and hasattr(self, "viewLayout"):
            container = self.view
        else:
            container = self

        v = QVBoxLayout(container) if container.layout() is None else container.layout()
        try:
            v.setContentsMargins(8, 8, 8, 8)
            v.setSpacing(6)
        except Exception:
            pass
        v.addWidget(self._hint_label)
        v.addWidget(self._red_control_label)
        v.addWidget(control_row)
        v.addWidget(self._red_model_label)
        v.addWidget(self._red_model_combo)
        v.addWidget(self._black_model_label)
        v.addWidget(self._black_model_combo)
        v.addStretch(1)

        # 回显当前生效配置
        self._echo()

    def register_change_callback(self, cb: Callable[[dict], None]) -> None:
        """注册外部回调（ChessCard.update_config）。"""
        self._on_change_external = cb

    def _echo(self) -> None:
        """从 PluginConfigStore 回显当前生效配置。"""
        if PluginConfigStore is None:
            return
        try:
            store = PluginConfigStore()
            v = store.get(PLUGIN_NAME, "red_control")
            if v not in ("manual", "ai"):
                v = DEFAULT_RED_CONTROL
            self._rb_manual.setChecked(v == "manual")
            self._rb_ai.setChecked(v == "ai")

            red_model = str(store.get(PLUGIN_NAME, "red_model") or "").replace("__default__", "")
            if red_model:
                idx = self._red_model_combo.findText(red_model)
                if idx >= 0:
                    self._red_model_combo.setCurrentIndex(idx)

            black_model = str(store.get(PLUGIN_NAME, "black_model") or "").replace("__default__", "")
            if black_model:
                idx = self._black_model_combo.findText(black_model)
                if idx >= 0:
                    self._black_model_combo.setCurrentIndex(idx)
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

    def _on_red_model_changed(self, text: str) -> None:
        self._save({"red_model": text or ""})

    def _on_black_model_changed(self, text: str) -> None:
        self._save({"black_model": text or ""})


# ── 注册入口 ──

def _register_chess_config_card(registry) -> None:
    """注册中国象棋设置卡。失败时优雅降级（print 警告）。"""
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
