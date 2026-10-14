# -*- coding: utf-8 -*-
"""异步采集 — 全库扫描会话 messages 解压取 usage，QThread 执行

render_func 在主线程同步调用，而全库解压扫描约 0.6s（476 会话 / 85MB），
同步做必然卡 UI。做法与 project-dashboard 同款：模块级单例 worker，
首次打开显示「加载中」占位，采集完成自动通知欢迎卡片重渲染。

刷新策略：
- 自动刷新：db mtime 变化时下次打开页签重采（key 含 mtime_ns）
- 手动刷新：页签「刷新用量」动作强制丢弃缓存重采
- error 结果带 60s TTL，避免临时失败被永久固化
"""

import threading
import time
from datetime import date
from typing import Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from loguru import logger

_PLUGIN_NAME = "token-usage"
_MODE_KEY = "token-usage"
_ERROR_TTL = 60.0

# 模块级缓存（QThread 写、主线程读，用锁保护整份替换）
_lock = threading.Lock()
_cache: Optional[dict] = None
_cache_key: Optional[tuple] = None
_cache_ts: float = 0.0
_running = False


def build_cache_key() -> tuple:
    """缓存 key：(db mtime_ns, 当天日期)

    db mtime 变化 = 有新会话写入，下次打开页签自动重采。
    """
    from . import data as data_mod

    db_path = data_mod.find_db()
    try:
        mtime_ns = db_path.stat().st_mtime_ns if db_path else 0
    except OSError:
        mtime_ns = 0
    return (mtime_ns, date.today().isoformat())


def get_cached() -> Optional[dict]:
    """缓存命中返回 data；未命中或 error 过期返回 None"""
    with _lock:
        if _cache is None or _cache_key != build_cache_key():
            return None
        if _cache.get("error") and time.monotonic() - _cache_ts >= _ERROR_TTL:
            return None
        return _cache


class _CollectWorker(QObject):
    """后台采集 worker"""

    finished = pyqtSignal(object)

    def __init__(self, cache_key: tuple):
        super().__init__()
        self._cache_key = cache_key

    def run(self):
        from .data import collect

        try:
            data = collect()
        except Exception as e:  # 兜底：worker 绝不让线程静默死掉
            logger.error(f"[{_PLUGIN_NAME}] 采集异常: {e}")
            data = {"daily": {}, "sessions": 0, "error": str(e)}
        self.finished.emit(data)


class _Collector(QObject):
    """采集管理器（模块级单例，QThread 生命周期在此）"""

    def __init__(self):
        super().__init__()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_CollectWorker] = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, force: bool = False) -> bool:
        """启动后台采集

        Args:
            force: True 忽略缓存强制重采（「刷新用量」动作走这条）

        Returns:
            True 表示本次启动了新线程
        """
        global _running
        if self.is_running():
            return False
        if force:
            invalidate()
        elif get_cached() is not None:
            return False
        with _lock:
            if _running:
                return False
            _running = True

        worker = _CollectWorker(build_cache_key())
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_done)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        thread.start()
        logger.info(f"[{_PLUGIN_NAME}] 采集已启动")
        return True

    def _on_done(self, data: dict):
        """采集完成：写缓存 + 通知欢迎卡片重渲染"""
        global _cache, _cache_key, _cache_ts, _running
        with _lock:
            _cache = data
            _cache_key = build_cache_key()
            _cache_ts = time.monotonic()
            _running = False
        self._thread = None
        self._worker = None
        if data.get("error"):
            logger.warning(f"[{_PLUGIN_NAME}] 采集返回错误: {data['error']}")
        else:
            logger.info(
                f"[{_PLUGIN_NAME}] 采集完成: {data.get('sessions', 0)} 会话 / "
                f"{len(data.get('daily', {}))} 天有记录"
            )
        notify_refresh()


def invalidate() -> None:
    """丢弃缓存（手动刷新 / 热重载用）"""
    global _cache, _cache_key, _cache_ts
    with _lock:
        _cache = None
        _cache_key = None
        _cache_ts = 0.0


def notify_refresh() -> None:
    """通知各窗口欢迎卡片重渲染本页签

    优先走 UIEventBus（主程序 ≥ 0.5.0 通用机制），失败回退直接调
    set_welcome_mode（与 project-dashboard 同款兜底）。
    """
    try:
        from app.core.infra.ui_event_bus import EV_WELCOME_TAB_REFRESHED, UIEventBus

        UIEventBus.get_instance().publish(
            EV_WELCOME_TAB_REFRESHED, mode_key=_MODE_KEY, plugin_name=_PLUGIN_NAME
        )
        return
    except Exception as e:
        logger.debug(f"[{_PLUGIN_NAME}] UIEventBus 不可用，回退直接刷新: {e}")

    try:
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        reg = UIPluginRegistry.get_instance()
        for mw in list(reg._window_main_widgets.values()):
            wid = getattr(mw, "_window_id", None)
            card = getattr(mw, "_welcome_card_cache", {}).get(wid)
            if card is None:
                continue
            if getattr(card, "_welcome_mode", "") == _MODE_KEY:
                card.set_welcome_mode(_MODE_KEY)
    except Exception as e:
        logger.debug(f"[{_PLUGIN_NAME}] 欢迎卡片刷新失败: {e}")


_collector: Optional[_Collector] = None


def get_collector() -> _Collector:
    """采集管理器单例"""
    global _collector
    if _collector is None:
        _collector = _Collector()
    return _collector


def refresh(force: bool = True) -> None:
    """手动刷新入口：丢弃缓存 + 后台重采"""
    invalidate()
    get_collector().start(force=True)