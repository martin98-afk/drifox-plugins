# -*- coding: utf-8 -*-
"""采集循环单例 — 插件内唯一一份。

为什么放在 core 而不是 ui：see-now 的主体是一个工具，界面只是可选观察窗口。
线程生命周期由本模块自己管（atexit 兜底），不依赖宿主回调——tools 组件没有
`on_unload` 钩子，只有 ui 组件有 `unload_ui`，把线程挂在 ui 上等于「工具栏加载
不了就没有采集」。

空闲自停：最后一次取图后超过 IDLE_STOP_SECONDS 没有新的调用，线程自己退出并
释放 mss 句柄；下一次工具调用 `get_loop()` 重新拉起。这样既不用靠 unload 钩子
收尾，也不会留下一个常驻吃 10% 单核的后台线程。
"""

from __future__ import annotations

import atexit
import threading
from typing import Optional

from loguru import logger

from .config import load_config
from .pipeline import CaptureLoop

# 空闲多久自停（秒）。取图时刷新，watch 期间每 0.25 秒刷新一次，不会中途被杀。
IDLE_STOP_SECONDS = 180.0

_loop: Optional[CaptureLoop] = None
_lock = threading.Lock()


def get_loop() -> CaptureLoop:
    """取（必要时创建）全局采集循环。已停止会重新启动。"""
    global _loop
    with _lock:
        if _loop is None:
            config = load_config()
            _loop = CaptureLoop(
                fps=config.fps,
                threshold=config.threshold,
                fallback_seconds=config.fallback_seconds,
                max_frames=config.max_frames,
                idle_seconds=IDLE_STOP_SECONDS,
            )
            logger.info("[see-now] 采集循环已创建")
        loop = _loop
    if not loop.is_running():
        loop.start()
    return loop


def shutdown() -> None:
    """停止并丢弃单例（进程退出 / 测试用）。"""
    global _loop
    with _lock:
        loop, _loop = _loop, None
    if loop is not None:
        try:
            loop.stop()
        except Exception as e:  # noqa: BLE001 - 收尾失败不该影响退出
            logger.warning(f"[see-now] 停止采集循环失败: {e}")


def _atexit_stop() -> None:
    try:
        shutdown()
    except Exception:  # noqa: BLE001
        pass


atexit.register(_atexit_stop)
