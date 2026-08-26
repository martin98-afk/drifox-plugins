# -*- coding: utf-8 -*-
"""workbuddy 进程内共享状态：tools 与 ui 之间传递 artifacts + plan mode 标记

简单按 workdir 索引的列表存储。工具 wb_present 调用时追加，UI 面板读取并渲染。
热重载与多窗口场景下：使用 RLock 保护读写；模块级单例在 sys.modules 缓存下共享。

通知机制：tools 写入后调用 notify(workdir, entry)，所有 register_listener 注册的
回调会被同步触发（同一线程，RLock 嵌套安全）。回调异常被吞掉，避免污染工具执行。

Plan mode 状态：wb_plan 写入，hook 读取。用模块属性持久化（避免 setdefault API 误解）。
"""
from threading import RLock
from typing import Callable

import os

_LOCK = RLock()
_STORE: dict[str, list[dict]] = {}  # workdir -> artifacts list
_LISTENERS: list[Callable[[str, dict], None]] = []  # (workdir, entry) -> None


def _norm(workdir: str) -> str:
    """workdir key 规范化：绝对路径 + 分隔符/大小写归一（Windows 不区分大小写，
    但工具写入端与 UI 读取端的原始字符串可能存在盘符大小写/正反斜杠差异，
    不归一会导致面板偶尔读不到数据（表现为"自动弹出但空白"）。"""
    if not workdir:
        return ""
    try:
        return os.path.normcase(os.path.abspath(str(workdir)))
    except OSError:
        return str(workdir)


def add(workdir: str, entry: dict) -> None:
    """追加一条 artifact 记录（按 workdir 索引）并通知监听者"""
    if not workdir:
        return
    with _LOCK:
        _STORE.setdefault(_norm(workdir), []).append(entry)
    notify(workdir, entry)


def get_all(workdir: str) -> list[dict]:
    """读取 workdir 下的全部 artifact 记录（拷贝）"""
    if not workdir:
        return []
    with _LOCK:
        return list(_STORE.get(_norm(workdir), []))


def clear(workdir: str) -> None:
    """清空指定 workdir 的记录"""
    if not workdir:
        return
    with _LOCK:
        _STORE.pop(_norm(workdir), None)


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
# 用模块级 dict，避免与同名函数冲突导致的 TypeError，也不依赖 sys.modules 自引用
# ────────────────────────────────────────────────────────────

_PLAN_STATE: dict[str, dict] = {}  # workdir -> plan entry


def plan_get(workdir: str) -> dict | None:
    """获取指定 workdir 的 plan 状态（None 表示未进入 plan mode）"""
    return _PLAN_STATE.get(workdir)


def plan_set(workdir: str, entry: dict) -> None:
    """设置指定 workdir 的 plan 状态"""
    _PLAN_STATE[workdir] = entry


def plan_clear(workdir: str) -> None:
    """清除指定 workdir 的 plan 状态"""
    _PLAN_STATE.pop(workdir, None)