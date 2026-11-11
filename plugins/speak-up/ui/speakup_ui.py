# -*- coding: utf-8 -*-
"""speak-up UI — 浮动卡（状态 + 记账 + 三个手动按钮）。

设计口径：
- **只做观察与手动触发**，所有配置项走 E1 自动卡（plugin.json 的 config_schema）。
  自绘卡不接管配置，避免「priority 覆盖后 config_schema 里的入口消失」这个坑。
- 卡片是纯展示 + 三个按钮。不画图、不碰 QWebEngine，规避渲染管线风险。
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from loguru import logger  # noqa: E402

from speakup_core.config import load_config  # noqa: E402
from speakup_core.runtime import bind_caps, get_runner, shutdown_runner  # noqa: E402,F401

PLUGIN_NAME = "speak-up"

_UI_AVAILABLE = False
try:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
    from qfluentwidgets import (  # noqa: F401
        BodyLabel,
        CaptionLabel,
        PushButton,
        StrongBodyLabel,
        TextEdit,
    )

    _UI_AVAILABLE = True
except Exception:  # noqa: BLE001 - 宿主缺 qfluentwidgets 时整个卡不注册
    QWidget = object  # type: ignore

# runner 单例与 bind_caps/get_runner/shutdown_runner 实体在 speakup_core.runtime，
# 全进程一份；此处只导入转发，勿在模块内另存引用。


if _UI_AVAILABLE:

    class SpeakUpCard(QWidget):
        """主动搭话状态卡。"""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._build_ui()
            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._refresh)
            self._timer.start()
            self._refresh()

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 12, 16, 12)
            layout.setSpacing(8)

            self._title = StrongBodyLabel("主动搭话", self)
            layout.addWidget(self._title)

            self._status = BodyLabel("正在读取状态…", self)
            self._status.setWordWrap(True)
            layout.addWidget(self._status)

            buttons = QHBoxLayout()
            buttons.setSpacing(8)
            self._dry_btn = PushButton("演练一次", self)
            self._dry_btn.clicked.connect(self._on_dry)
            self._real_btn = PushButton("真发一次", self)
            self._real_btn.clicked.connect(self._on_real)
            buttons.addWidget(self._dry_btn)
            buttons.addWidget(self._real_btn)
            buttons.addStretch(1)
            layout.addLayout(buttons)

            hint = CaptionLabel("配置项在「设置 → 插件 → 主动搭话」里改", self)
            layout.addWidget(hint)

            self._log = TextEdit(self)
            self._log.setReadOnly(True)
            self._log.setMinimumHeight(180)
            layout.addWidget(self._log, 1)

        # ── 刷新 ────────────────────────────────────

        def _refresh(self) -> None:
            try:
                runner = get_runner()
            except Exception as e:  # noqa: BLE001
                self._status.setText(f"运行时未就绪：{e}")
                return
            snap = runner.state_snapshot()
            config = load_config()
            parts = [
                f"{'运行中' if snap['running'] else '已停止'}",
                f"间隔 {snap['interval_seconds'] // 60} 分钟" if snap["interval_seconds"] else "间隔未起算",
                f"连没中 {snap['misses']} 次",
            ]
            if config.dry_run:
                parts.append("试运行中（只记账）")
            if not config.enabled:
                parts.append("总开关已关")
            self._status.setText(" · ".join(parts))

            lines = [f"{e.at}  {e.text}" for e in runner.recent_entries()[-20:]]
            self._log.setPlainText("\n".join(lines) if lines else "（还没有记账）")
            self._log.moveCursor(self._log.textCursor().End)

        # ── 按钮 ────────────────────────────────────

        def _on_dry(self) -> None:
            self._run("演练")

        def _on_real(self) -> None:
            self._run("真发")

        def _run(self, mode: str) -> None:
            try:
                runner = get_runner()
            except Exception as e:  # noqa: BLE001
                self._status.setText(f"运行时不可用：{e}")
                return
            try:
                runner.roll(source="手动", mode=mode)
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[speak-up] 手动 {mode} 失败: {e}")
            self._refresh()


def register_ui(registry):
    """注册卡片与设置页（能力取值器 + 定时器启动）。"""
    # 热重载时摘除旧 speakup_core.*，让 UI 侧重新拿到最新代码
    # （ui/speakup_ui 等宿主按 ui_plugin_speak_up 前缀自行 purge，裸前缀永不命中）
    for key in list(sys.modules):
        if key == "speakup_core" or key.startswith("speakup_core."):
            sys.modules.pop(key, None)

    from app.plugins.capabilities.resolve import caps_for

    def _getter(cap_id: str):
        try:
            return caps_for(cap_id, plugin=PLUGIN_NAME, surface="ui")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[speak-up] 取能力 {cap_id} 失败: {e}")
            return None

    bind_caps(_getter)

    # 独立设置大 tab（复杂配置页，不挤进「设置 → 插件」卡片流）
    try:
        from .settings_page import get_settings_page_class

        page_class = get_settings_page_class()
        if page_class is None:
            logger.warning("[speak-up] 宿主缺 qfluentwidgets，跳过设置页注册")
        else:
            registry.register_settings_tab(
                PLUGIN_NAME, "config", "主动搭话", page_class, icon="说话", priority=0
            )
            logger.info("[speak-up] 设置页已注册")
    except AttributeError:
        # 旧宿主没有 register_settings_tab（0.6.14 之前）：降级，只留浮动卡
        logger.warning("[speak-up] 宿主不支持 register_settings_tab，跳过设置页")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[speak-up] 注册设置页失败: {e}")

    if not _UI_AVAILABLE:
        logger.warning("[speak-up] 宿主缺 qfluentwidgets，跳过卡片注册（定时器仍可用）")
        try:
            get_runner()
        except Exception:  # noqa: BLE001
            pass
        return

    registry.register_floating_card(
        plugin_name=PLUGIN_NAME,
        card_id="speak-up",
        widget_class=SpeakUpCard,
        container="right",
        title="主动搭话",
        default_visible=False,
    )

    # 卡片默认不可见，但定时器必须随插件加载就起来
    try:
        get_runner()
        logger.info("[speak-up] UI 已注册，定时器已启动")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[speak-up] 启动定时器失败: {e}")


def unload_ui(registry):
    """卸载回调：停定时器，清单例。"""
    shutdown_runner()
    logger.info("[speak-up] unload_ui：定时器已停止")
