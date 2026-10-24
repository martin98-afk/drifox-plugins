# -*- coding: utf-8 -*-
"""project-dashboard 异步采集 — QThread worker + 模块级缓存 + 欢迎卡片重渲染

render_func 主线程同步调用，git/文件采集耗时（数百 ms）必须后台执行：
- 模块级单例 worker，避免重复启动
- 采集完成 → 缓存写入 + 触发欢迎卡片重渲染（UIEventBus / set_welcome_mode）
- 缓存 key = (git_root, HEAD, 当天日期)：HEAD 变化自动失效重采

⚠️ 线程生命周期约束（踩过的坑，勿回退）：
1. QThread 的退出必须由 worker.run() 内的 ``QThread.currentThread().quit()``
   负责，不能用 ``worker.finished -> thread.quit`` 的 queued 连接。
2. 缓存写入必须在 worker 线程就地完成（``_finalize_collect``），不依赖任何
   跨线程信号投递 —— 见该函数文档。
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal
from loguru import logger

if TYPE_CHECKING:  # 仅类型标注用，避免运行时前向引用
    from . import _Collector

_PLUGIN_NAME = "project-dashboard"
_MODE_KEY = "project-dashboard"

# HEAD 查询 TTL（秒）：build_cache_key 主线程同步跑 git，短 TTL 缓存避免每次渲染都起子进程
_HEAD_TTL = 5.0
_head_cache: dict = {}  # project_root -> (ts, head)
# error 结果缓存 TTL（秒）：避免错误被永久固定（如 root 解析暂时失败），过期自动重采
_ERROR_TTL = 60.0

_collector: Optional["_Collector"] = None


class _CollectWorker(QObject):
    """后台采集 worker

    收尾职责在 run() 内自主完成（写缓存 / 清运行态 / 线程退出），
    不依赖 finished 信号的跨线程投递 —— 原因见 _finalize_collect 文档。
    """

    finished = Signal(object)  # dict
    error = Signal(str)

    def __init__(self, project_root: str, is_dark: bool, collector: "_Collector"):
        super().__init__()
        self._root = project_root
        self._is_dark = is_dark
        self._collector = collector

    def run(self):
        from .dashboard import collect_data

        thread = QThread.currentThread()
        try:
            data = collect_data(self._root)
            data["is_dark"] = self._is_dark
        except Exception as e:
            err = f"采集失败: {e}"
            _finalize_collect({"error": err}, self._collector)
            self._release()
            thread.quit()
            self.error.emit(err)
            return
        _finalize_collect(data, self._collector)
        self._release()
        # 退出本采集线程的事件循环。quit() 线程安全，退出事件由本线程 exec 消费；
        # 不能依赖 worker.finished -> thread.quit 的 queued 连接（见 _finalize_collect）。
        thread.quit()
        self.finished.emit(data)
        # 通知欢迎卡片重渲染：优先 UIEventBus（任意线程发布安全），无 Qt 主线程
        # 场景跳过（缓存已写好，下次打开页签 get_cached() 直接命中）。
        notify_refresh()

    def _release(self):
        """释放管理器引用：此后 is_running() 立即为 False，新采集不被旧线程阻拦"""
        self._collector._thread = None
        self._collector._worker = None


class _Collector(QObject):
    """异步采集管理器（模块级单例，QObject 化保证回调线程归位主线程）

    【PySide6 崩溃修复】此前为纯 Python 对象：信号连接到非 QObject receiver
    无 thread affinity，PySide6 会在 worker 线程直接执行 _on_done →
    _refresh_welcome_cards 跨线程调 card.set_welcome_mode → qFatal 闪退
    （crash 0xC0000409，日志为空）。QObject 化后实例驻留主线程（首次由
    render_func 创建），信号自动走 queued 连接回主线程执行。
    """

    def __init__(self):
        super().__init__()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_CollectWorker] = None
        self._cache: Optional[dict] = None
        self._cache_key: tuple = ()
        self._cache_ts: float = 0.0  # 缓存写入时间（error TTL 用）

    def get_cached(self, cache_key: tuple) -> Optional[dict]:
        """缓存命中返回 data，否则 None

        error 结果带 TTL：过期视为未命中，允许自动重采恢复。
        """
        if self._cache is not None and self._cache_key == cache_key:
            if self._cache.get("error"):
                if time.monotonic() - self._cache_ts < _ERROR_TTL:
                    return self._cache
                return None  # error 过期 → 触发重采
            return self._cache
        return None

    def start(self, project_root: str, is_dark: bool, cache_key: tuple):
        """启动后台采集（幂等：正在跑则跳过）"""
        if self._thread is not None and self._thread.isRunning():
            return
        self._cache_key = cache_key
        self._cleanup()
        w = _CollectWorker(project_root, is_dark, self)
        t = QThread()
        w.moveToThread(t)
        t.started.connect(w.run)
        # 兜底：receiver 线程存活时 _on_done 还会再执行一次（幂等，见其文档）
        w.finished.connect(self._on_done)
        w.finished.connect(w.deleteLater)
        w.error.connect(w.deleteLater)
        t.finished.connect(t.deleteLater)
        # 引用清理统一挪到线程真正结束后（见 _on_thread_finished）：
        # 若在 _on_done（主线程）提前置 None，GC 可能从主线程销毁活在
        # worker 线程的 QObject → 段错误 0xC0000005。
        t.finished.connect(self._on_thread_finished)
        self._thread, self._worker = t, w
        t.start()

    def _on_done(self, data: dict):
        """finished 信号回调（幂等兜底）

        缓存写入 / 状态清理已在 worker 线程的 ``_finalize_collect`` 就地完成，
        这里重复写无害（同 key 同数据），仅补一次 UI 刷新通知。
        receiver 线程已死时本回调不会执行，也不影响数据就绪。
        """
        self._thread = None
        self._worker = None
        self._cache = data
        self._cache_ts = time.monotonic()
        notify_refresh()
        if data.get("error"):
            logger.error(f"[project-dashboard] collect error: {data['error']}")
        else:
            logger.info("[project-dashboard] collect done")

    def _on_error(self, err: str):
        self._thread = None
        self._worker = None
        logger.error(f"[project-dashboard] collect error: {err}")

    def _on_thread_finished(self):
        """worker 线程真正结束后才清理引用（deleteLater 已全部处理完）"""
        self._thread = None
        self._worker = None

    def _cleanup(self):
        """清理残留引用（线程已退出 + deleteLater 排队处理）"""
        self._thread = None
        self._worker = None


def _finalize_collect(data: dict, collector: "_Collector") -> None:
    """采集收尾：写缓存 + 日志 + 清运行态。在 worker 线程内直接调用。

    ⚠️ 不能依赖 ``_on_done`` 信号回调做这件事：QThread 必须在 exec() 退出后
    才能析构，而原实现把 ``w.finished`` 同时接到 ``_on_done``（首行就把
    ``self._thread`` 置 None）与 ``t.quit``（异步生效，此刻 exec() 仍在跑）——
    QThread 对象失去最后一个 Python 引用即析构，而线程尚在运行，Qt 直接
    ``qFatal: QThread: Destroyed while thread is still running``，缓存写入之类
    的后续代码根本到不了。
    修法：①缓存写入在 worker 线程就地完成；②线程退出改由 ``run()`` 内
    ``QThread.currentThread().quit()`` 负责。
    """
    collector._cache = data
    collector._cache_ts = time.monotonic()
    if data.get("error"):
        logger.error(f"[project-dashboard] collect error: {data['error']}")
    else:
        logger.info("[project-dashboard] collect done")


def notify_refresh() -> None:
    """通知各窗口欢迎卡片重渲染本页签

    优先走 UIEventBus（主程序 ≥ 0.5.0 通用机制，任意线程发布安全）；
    不可用则回退直接摸 UIPluginRegistry —— 后者只能在主线程执行，
    worker 线程触发时跳过（缓存已写好，下次打开页签 get_cached() 命中即有数据）。
    """
    try:
        from app.core.infra.ui_event_bus import EV_WELCOME_TAB_REFRESHED, UIEventBus

        UIEventBus.get_instance().publish(
            EV_WELCOME_TAB_REFRESHED, mode_key=_MODE_KEY, plugin_name=_PLUGIN_NAME
        )
        return
    except Exception as e:
        logger.debug(f"[project-dashboard] UIEventBus 不可用，回退直接刷新: {e}")

    try:
        app = QCoreApplication.instance()
        if app is None or QThread.currentThread() is not app.thread():
            return
    except Exception:
        pass

    _refresh_welcome_cards()


def _refresh_welcome_cards():
    """触发所有窗口欢迎卡片重渲染（当前显示 project-dashboard tab 的立即刷新）"""
    try:
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        reg = UIPluginRegistry.get_instance()
        for mw in list(reg._window_main_widgets.values()):
            try:
                wid = getattr(mw, "_window_id", None)
                if wid is None:
                    continue
                cache = getattr(mw, "_welcome_card_cache", {})
                card = cache.get(wid)
                if card is None:
                    continue
                # 🛡️ C++ 对象已析构时调任何方法都是 access violation（不可捕获）
                try:
                    from shiboken6 import isValid

                    if not isValid(card):
                        continue
                except ImportError:
                    pass
                mode = getattr(card, "_welcome_mode", "")
                if mode == _MODE_KEY:
                    card.set_welcome_mode(_MODE_KEY)
            except Exception:
                pass
    except Exception:
        pass


def get_collector() -> _Collector:
    """获取异步采集单例"""
    global _collector
    if _collector is None:
        _collector = _Collector()
    return _collector


def build_cache_key(project_root: str, data: Optional[dict] = None) -> tuple:
    """缓存 key：git 根 + HEAD + 日期（HEAD 变化自动重采）

    HEAD 查询带 5s TTL 缓存：主线程同步调用多次渲染时避免重复启动 git 子进程。
    """
    now = time.monotonic()
    cached = _head_cache.get(project_root)
    if cached is not None and now - cached[0] < _HEAD_TTL:
        head = cached[1]
    else:
        try:
            from .dashboard import _run_git

            head = _run_git(project_root, "rev-parse", "--short", "HEAD") or "none"
        except Exception:
            head = "none"
        _head_cache[project_root] = (now, head)
    return (project_root, head, datetime.now().strftime("%Y-%m-%d"))
