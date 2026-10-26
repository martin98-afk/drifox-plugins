# -*- coding: utf-8 -*-
"""异步采集 — 全库扫描会话 messages 解压取 usage，QThread 执行

render_func 在主线程同步调用，而全库解压扫描约 0.6s（476 会话 / 85MB），
同步做必然卡 UI。做法与 project-dashboard 同款：模块级单例 worker，
首次打开显示「加载中」占位，采集完成自动通知欢迎卡片重渲染。

刷新策略：
- 自动刷新：db mtime 变化时下次打开页签重采（key 含 mtime_ns）；正常结果
  不设 TTL，db 没变就永远复用（采集本身是会话级增量，重采代价小，见 data.collect）
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
    """缓存命中返回 data；未命中或 error 过期返回 None

    正常结果不设 TTL：新鲜度完全由 db mtime 判定（start() 里比对
    _is_stale），db 没变就永远复用，避免「过 60 秒重开页签就白付
    一次扫描」。

    ⚠️ 不用 db mtime 做读取判据（踩过的坑）：mtime 会因为**采集期间**新会话
    写入而变化，导致「写缓存时算一次 key、读缓存时又算一次」两次 key 不等，
    缓存永远判定为未命中 —— 表现是页签永远停在「加载中」：
    每次都重新起线程，采集完 mtime 又变了，永远追不上。
    正确做法：写入时把 key 一起存下，读取时只比采集自否成功。
    """
    with _lock:
        if _cache is None:
            return None
        if _cache.get("error"):
            # 错误结果短 TTL：避免临时失败被永久固化
            if time.monotonic() - _cache_ts >= _ERROR_TTL:
                return None
        return _cache


def _is_stale() -> bool:
    """采集结果是否已过期（db 在采集完成后又变了 → 数据不全）"""
    with _lock:
        return _cache is not None and _cache_key != build_cache_key()


class _CollectWorker(QObject):
    """后台采集 worker

    收尾职责在 run() 内自主完成（写缓存/日志/状态清理/线程退出），
    不依赖 finished 信号的跨线程投递——原因见 _finalize_collect docstring。
    """

    finished = pyqtSignal(object)

    def __init__(self, cache_key: tuple, collector: "_Collector"):
        super().__init__()
        self._cache_key = cache_key
        self._collector = collector

    def run(self):
        from .data import collect

        try:
            data = collect()
        except Exception as e:  # 兜底：worker 绝不让线程静默死掉
            logger.error(f"[{_PLUGIN_NAME}] 采集异常: {e}")
            data = {"daily": {}, "sessions": 0, "error": str(e)}
        _finalize_collect(data)
        # 释放管理器引用：此后 is_running() 立即为 False，新采集不被旧线程阻拦
        self._collector._thread = None
        self._collector._worker = None
        # 退出本采集线程的事件循环：quit() 线程安全，退出事件由本线程 exec 消费。
        # 不能依赖 worker.finished -> thread.quit 信号连接：queued 投给 receiver
        # 线程，receiver 线程已死时事件永久滞留，线程泄漏（见 _finalize_collect）。
        QThread.currentThread().quit()
        self.finished.emit(data)
        # 数据就绪后的 UI 通知：UIEventBus（宿主主线程单例）从任意线程发布安全；
        # 无 UIEventBus 的旧宿主在非主线程触发时守卫跳过——缓存已写入，下次
        # 打开页签 get_cached() 直接命中。
        notify_refresh()


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
        else:
            if get_cached() is not None and not _is_stale():
                return False
        with _lock:
            if _running:
                return False
            _running = True

        worker = _CollectWorker(build_cache_key(), self)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_done)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        thread.start()
        logger.info(f"[{_PLUGIN_NAME}] 采集已启动")
        return True

    def _on_done(self, data: dict):
        """信号回调兜底（幂等）：缓存写入/状态清理已前移到 worker 线程的
        _finalize_collect，这里只负责 receiver 线程存活场景下的重复通知。
        receiver 线程已死时本方法不会执行，也不影响数据就绪。
        """
        self._thread = None
        self._worker = None
        notify_refresh()


def _finalize_collect(data: dict) -> None:
    """采集收尾：写缓存 + 日志 + 清运行态。在 worker 线程内直接调用。

    ⚠️ 不能依赖 _on_done 信号回调做这件事（打包版踩过的死线程坑）：
    _collector 的线程亲和 = 首次 get_collector() 的调用线程。市场安装流程中
    register_ui 的预热 start() 经 QTimer.singleShot 在安装 worker 线程执行，
    _collector 随之诞生在该线程；安装任务完成、worker 线程 exec() 退出后，
    queued 给死线程的 finished 事件永不消费——缓存永不写入、_running 永不
    清零，页签永远停在「正在统计 API 用量…」。
    修法：缓存写入（锁保护，线程安全）与日志在 worker 线程就地完成，
    不经任何跨线程信号。
    """
    global _cache, _cache_key, _cache_ts, _running
    with _lock:
        _cache = data
        _cache_key = build_cache_key()
        _cache_ts = time.monotonic()
        _running = False
    if data.get("error"):
        logger.warning(f"[{_PLUGIN_NAME}] 采集返回错误: {data['error']}")
    else:
        logger.info(
            f"[{_PLUGIN_NAME}] 采集完成: {data.get('sessions', 0)} 会话 / "
            f"{len(data.get('daily', {}))} 天有记录"
        )


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

    # 回退分支直接摸 Qt UI，只允许主线程执行；worker 线程触发时跳过
    # （缓存已写好，下次打开页签 get_cached() 命中即有数据）。
    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None and QThread.currentThread() is not app.thread():
            return
    except Exception:
        pass

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