# -*- coding: utf-8 -*-
"""定时备份调度器（进程级单例，锚定 sys 模块跨热重载存活）

QObject + QTimer 在主线程 tick 判期；到点后起 daemon 线程跑 engine.run_backup，
经 pyqtSignal（queued）回主线程广播结果。UI 未打开时备份照常执行。
"""
from __future__ import annotations

import gc
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from . import config as cfg_mod

# 热重载会清 sys.modules["ui_plugin_webdav_backup.*"] 并生成新一代类对象；
# 单例若只存类属性，新一代会另建实例，旧 QTimer 在进程内再无入口可停。
_SINGLETON_ANCHOR = "_drifox_webdav_backup_scheduler"

_TICK_MS = 10 * 60 * 1000        # 常规判期周期：10 分钟
_FIRST_TICK_MS = 60 * 1000       # 启动后首查延迟，避开启动高峰
_RETRY_AFTER_ERROR_MIN = 60      # 上次备份失败后的最小重试间隔（分钟），防打爆坚果云频率限制


def _read_anchor():
    import sys

    return getattr(sys, _SINGLETON_ANCHOR, None)


def _write_anchor(inst) -> None:
    import sys

    if inst is None:
        try:
            delattr(sys, _SINGLETON_ANCHOR)
        except AttributeError:
            pass
    else:
        setattr(sys, _SINGLETON_ANCHOR, inst)


def _due(state: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """距上次成功备份是否已超过间隔；上次失败时按更短的重试间隔判"""
    last = state.get("last_backup_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last))
    except ValueError:
        return True
    elapsed_min = (datetime.now() - last_dt).total_seconds() / 60
    if state.get("last_backup_status") == "error":
        return elapsed_min >= _RETRY_AFTER_ERROR_MIN
    return elapsed_min >= cfg.get("interval_hours", 24) * 60


class BackupScheduler(QObject):
    """定时备份调度器（takeover 单例）"""

    backup_finished = pyqtSignal(dict)  # engine.run_backup 结果（queued 回主线程）

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._busy = threading.Lock()
        self._started = False

    # ── 单例管理 ────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "BackupScheduler":
        inst = _read_anchor()
        if inst is None:
            inst = cls()
            _write_anchor(inst)
        return inst

    @classmethod
    def takeover(cls) -> "BackupScheduler":
        """新一代接棒：停掉上一代实例并新建（register_ui 专用）"""
        old = _read_anchor()
        if old is not None:
            try:
                old.stop()
            except Exception as e:
                logger.warning(f"[webdav-backup] 上一代调度器停止失败: {e}")
            _write_anchor(None)
        inst = cls()
        _write_anchor(inst)
        cls._sweep_stale(keep=inst)
        return inst

    @classmethod
    def _sweep_stale(cls, keep: "BackupScheduler") -> None:
        """gc 扫描静默其他世代遗留实例（旧版本类属性单例时代产物）"""
        killed = 0
        for obj in gc.get_objects():
            try:
                if obj is keep or type(obj).__name__ != "BackupScheduler":
                    continue
                if getattr(obj, "_started", False):
                    obj.stop()
                    killed += 1
            except Exception:
                continue
        if killed:
            logger.info(f"[webdav-backup] 已静默 {killed} 个遗留调度器实例")

    # ── 生命周期 ────────────────────────────────────────

    def ensure_started(self) -> None:
        """幂等启动；首查延迟 60s"""
        if self._started:
            return
        self._started = True
        QTimer.singleShot(_FIRST_TICK_MS, self._tick)
        self._timer.start()
        logger.info("[webdav-backup] 调度器已启动（每 10 分钟判期）")

    def stop(self) -> None:
        self._started = False
        if self._timer.isActive():
            self._timer.stop()

    # ── 判期与执行 ──────────────────────────────────────

    def _tick(self) -> None:
        try:
            cfg = cfg_mod.load_config()
            if not cfg.get("auto_backup") or not cfg_mod.is_configured(cfg):
                return
            if not _due(cfg_mod.load_state(), cfg):
                return
            self.trigger_async(reason="auto")
        except Exception as e:  # tick 层屏障：任何异常不得杀死 QTimer
            logger.warning(f"[webdav-backup] 调度 tick 异常: {e}")

    def trigger_async(self, reason: str = "manual") -> bool:
        """后台线程执行备份；已有任务进行中返回 False"""
        if not self._busy.acquire(blocking=False):
            return False
        try:

            def _worker():
                from .engine import run_backup

                try:
                    result = run_backup()
                    logger.info(f"[webdav-backup] 自动备份({reason}): {result.get('message', '')}")
                    self.backup_finished.emit(result)
                except Exception as e:  # worker 屏障
                    result = {"ok": False, "message": f"备份线程异常: {e}"}
                    self.backup_finished.emit(result)
                finally:
                    self._busy.release()

            threading.Thread(target=_worker, daemon=True, name="webdav-backup").start()
            return True
        except Exception:
            self._busy.release()
            raise

    def is_busy(self) -> bool:
        return self._busy.locked()
