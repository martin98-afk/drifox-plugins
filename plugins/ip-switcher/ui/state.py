# -*- coding: utf-8 -*-
"""ip-switcher 状态/事件总线

职责：
- 维护当前出口 IP、换绑历史（内存 + 可选落盘）、统计计数
- 通过 pyqtSignal 广播事件（换绑完成、代理池异常、模式变化）
- 线程安全：信号跨线程自动投递，计数加锁
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal


@dataclass
class SwitchEvent:
    """一次换绑事件"""

    timestamp: float
    trigger: str  # "ratelimit" | "manual" | "startup"
    old_ip: str
    new_ip: str
    success: bool = True
    note: str = ""


class IPState(QObject):
    """全局状态总线（QObject 以便信号跨线程）"""

    # 信号：换绑事件、状态变化（供 UI 刷新）
    switched = pyqtSignal(object)          # SwitchEvent
    status_changed = pyqtSignal(str, str)  # (field, value)
    pool_state_changed = pyqtSignal(str)   # "ok" | "error" | "starting"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = __import__("threading").RLock()
        self._current_ip: str = "未使用"
        self._mode: str = "auto"          # auto/sticky/manual
        self._auto_switch: bool = True
        self._pool_state: str = "stopped"  # stopped/starting/ok/error
        self._history: Deque[SwitchEvent] = deque(maxlen=50)
        self._stats: Dict[str, int] = {
            "total_switches": 0,
            "today_switches": 0,
            "success_count": 0,
            "fail_count": 0,
            "rate_limit_hits": 0,
        }
        self._today: str = time.strftime("%Y-%m-%d")

    # ── 读 ──

    def current_ip(self) -> str:
        with self._lock:
            return self._current_ip

    def mode(self) -> str:
        with self._lock:
            return self._mode

    def is_auto_switch(self) -> bool:
        with self._lock:
            return self._auto_switch

    def pool_state(self) -> str:
        with self._lock:
            return self._pool_state

    def history(self) -> List[SwitchEvent]:
        with self._lock:
            return list(self._history)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            # 跨天重置今日计数
            today = time.strftime("%Y-%m-%d")
            if today != self._today:
                self._today = today
                self._stats["today_switches"] = 0
            return dict(self._stats)

    # ── 写（均广播信号） ──

    def set_current_ip(self, ip: str) -> None:
        with self._lock:
            self._current_ip = ip or "未使用"
        self.status_changed.emit("current_ip", self._current_ip)

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode
        self.status_changed.emit("mode", mode)

    def set_auto_switch(self, on: bool) -> None:
        with self._lock:
            self._auto_switch = on
        self.status_changed.emit("auto_switch", "on" if on else "off")

    def set_pool_state(self, state: str) -> None:
        with self._lock:
            self._pool_state = state
        self.pool_state_changed.emit(state)

    def record_switch(self, trigger: str, old_ip: str, new_ip: str, success: bool = True, note: str = "") -> None:
        """记录一次换绑事件并广播"""
        ev = SwitchEvent(
            timestamp=time.time(),
            trigger=trigger,
            old_ip=old_ip,
            new_ip=new_ip,
            success=success,
            note=note,
        )
        with self._lock:
            self._history.append(ev)
            self._stats["total_switches"] += 1
            if time.strftime("%Y-%m-%d") == self._today:
                self._stats["today_switches"] += 1
            if success:
                self._stats["success_count"] += 1
            else:
                self._stats["fail_count"] += 1
            if trigger == "ratelimit":
                self._stats["rate_limit_hits"] += 1
            self._current_ip = new_ip or self._current_ip
        self.switched.emit(ev)
        self.status_changed.emit("current_ip", self._current_ip)


# 模块级单例
_state: Optional[IPState] = None


def get_state() -> IPState:
    """获取全局状态单例（须在主线程创建）"""
    global _state
    if _state is None:
        _state = IPState()
    return _state


def reset_state_for_test() -> IPState:
    """测试辅助"""
    global _state
    _state = IPState()
    return _state