# -*- coding: utf-8 -*-
"""speak-up 运行时单例 — runner 的唯一存放处。

为什么放 core 而不放 ui/speakup_ui.py：hook / tool / 设置页都要拿 runner，
但 `from ui.speakup_ui import ...` 依赖插件根排在 sys.path 最前——宿主会把
每个 UI 插件的 ui/ 目录 insert(0) 进 sys.path，晚加载且带 ui/__init__.py 的
插件（voice-input 等）会把 `ui` 包名顶掉，报 No module named 'ui.speakup_ui'。
speakup_core.* 是无同名冲突的顶层包，所有加载器下都能稳定解析，且同一
sys.modules 条目保证全进程只有一份 runner、一个定时器。
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from loguru import logger

from .config import load_config
from .runner import SpeakUpRunner

# 单例 runner（工具、hook、卡片共用同一个，避免多份定时器）
_runner: Optional[SpeakUpRunner] = None
_get_caps: Optional[Callable[[str], Any]] = None

def bind_caps(getter: Callable[[str], Any]) -> None:
    """宿主注入能力取值器（register_ui 时调用一次）。"""
    global _get_caps
    _get_caps = getter

def get_runner() -> SpeakUpRunner:
    """取（必要时创建）全局 runner。首次调用会启动定时器。"""
    global _runner
    if _runner is None:
        if _get_caps is None:
            raise RuntimeError("speak-up：能力取值器尚未注入（register_ui 未执行）")
        _runner = SpeakUpRunner(get_caps=_get_caps, get_config=load_config)
        if load_config().enabled:
            _runner.start()
    return _runner

def shutdown_runner() -> None:
    """插件卸载时停止定时器。"""
    global _runner
    if _runner is not None:
        try:
            _runner.stop()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[speak-up] 停止 runner 失败: {e}")
        _runner = None
