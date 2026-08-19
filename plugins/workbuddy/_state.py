# -*- coding: utf-8 -*-
"""workbuddy 进程内共享状态：tools 与 ui 之间传递 artifacts + plan mode 标记

简单按 workdir 索引的列表存储。工具 wb_present 调用时追加，UI 面板读取并渲染。
热重载与多窗口场景下：使用 RLock 保护读写；模块级单例在 sys.modules 缓存下共享。

通知机制：tools 写入后调用 notify(workdir, entry)，所有 register_listener 注册的
回调会被同步触发（同一线程，RLock 嵌套安全）。回调异常被吞掉，避免污染工具执行。

Plan mode 状态：wb_plan 写入，hook 读取。用模块属性持久化（避免 setdefault API 误解）。
"""
import sys
from threading import RLock
from typing import Callable

_LOCK = RLock()
_STORE: dict[str, list[dict]] = {}  # workdir -> artifacts list
_LISTENERS: list[Callable[[str, dict], None]] = []  # (workdir, entry) -> None


def add(workdir: str, entry: dict) -> None:
    """追加一条 artifact 记录（按 workdir 索引）并通知监听者"""
    if not workdir:
        return
    with _LOCK:
        _STORE.setdefault(workdir, []).append(entry)
    notify(workdir, entry)


def get_all(workdir: str) -> list[dict]:
    """读取 workdir 下的全部 artifact 记录（拷贝）"""
    if not workdir:
        return []
    with _LOCK:
        return list(_STORE.get(workdir, []))


def clear(workdir: str) -> None:
    """清空指定 workdir 的记录"""
    if not workdir:
        return
    with _LOCK:
        _STORE.pop(workdir, None)


def last_message(workdir: str) -> str:
    """最近一次 present_files 的 message（用于面板顶部摘要）"""
    items = get_all(workdir)
    for it in reversed(items):
        msg = it.get("message")
        if msg:
            return msg
    return ""


def register_listener(cb: Callable[[str, dict], None]) -> Callable[[], None]:
    """注册监听者；返回取消注册的闭包"""
    with _LOCK:
        if cb not in _LISTENERS:
            _LISTENERS.append(cb)

    def _unregister() -> None:
        unregister_listener(cb)

    return _unregister


def unregister_listener(cb: Callable[[str, dict], None]) -> None:
    with _LOCK:
        try:
            _LISTENERS.remove(cb)
        except ValueError:
            pass


def notify(workdir: str, entry: dict) -> None:
    """同步触发所有监听者（监听者异常被吞掉）"""
    with _LOCK:
        snapshot = list(_LISTENERS)
    for cb in snapshot:
        try:
            cb(workdir, entry)
        except Exception:
            import logging
            logging.getLogger("workbuddy").exception("state notify listener failed")


# ────────────────────────────────────────────────────────────
# Plan mode 状态（wb_plan 写入，hook 读取）
# 用模块属性而非 setdefault：避免模型误用 setdefault 的 setdefault 错误
# ────────────────────────────────────────────────────────────

def _plan_state() -> dict:
    """惰性初始化 plan state 字典（存在模块属性 _plan_state 中）"""
    state = getattr(sys.modules[__name__], "_plan_state", None)
    if state is None:
        state = {}
        setattr(sys.modules[__name__], "_plan_state", state)
    return state


def plan_get(workdir: str) -> dict | None:
    """获取指定 workdir 的 plan 状态（None 表示未进入 plan mode）"""
    return _plan_state().get(workdir)


def plan_set(workdir: str, entry: dict) -> None:
    """设置指定 workdir 的 plan 状态"""
    _plan_state()[workdir] = entry


def plan_clear(workdir: str) -> None:
    """清除指定 workdir 的 plan 状态"""
    _plan_state().pop(workdir, None)