# -*- coding: utf-8 -*-
"""调度器生命周期：register_ui 启动、unload_ui 停表（热重载安全）。"""
from __future__ import annotations

from loguru import logger


def ensure_scheduler():
    from biliscroll_core.scheduler import get_scheduler

    get_scheduler().start()


def release_scheduler():
    from biliscroll_core import scheduler as _mod

    sched = _mod._scheduler
    if sched is not None:
        try:
            sched.stop()
        except RuntimeError:
            pass  # Qt 对象已随热重载析构
        _mod._scheduler = None
        logger.info("[bili-scroll] 峰谷调度器已停")
