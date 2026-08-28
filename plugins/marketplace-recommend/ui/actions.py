# -*- coding: utf-8 -*-
"""欢迎 tab 点击动作处理 — 点击安装 / 换一批

点击链路：欢迎卡片 HTML(.context-tag data-type) → 主程序
handle_recommended_question → UIPluginRegistry.dispatch_welcome_action → 本模块。

安装为耗时操作（git clone + deps），走 QThread；完成信号连到驻主线程的
Coordinator（QObject，thread affinity 在主线程 → 跨线程信号自动 queued），
保证 InfoBar / 重渲染都在主线程执行。
"""

import threading
from typing import Any, Dict

from loguru import logger
from PyQt5.QtCore import QObject, QThread, pyqtSignal

from . import mkt_bridge, render

_PLUGIN_NAME = "marketplace-recommend"
# 安装中的插件名（防重复点击）
_installing_lock = threading.Lock()
_installing: set = set()
# 存活的安装任务 (worker, coordinator)：QThread/协调器被 GC 会导致完成信号丢失
_active_jobs: list = []


class _InstallWorker(QThread):
    """后台安装单个插件（复用市场插件的 PluginInstaller）"""

    ok = pyqtSignal(str)  # plugin_name
    fail = pyqtSignal(str, str)  # plugin_name, error

    def __init__(self, meta: Dict[str, Any], parent=None):
        super().__init__(parent)
        self._meta = meta

    def run(self):
        name = str(self._meta.get("name", ""))
        try:
            installer = mkt_bridge.get_bridge_installer()
            if installer is None:
                self.fail.emit(name, "插件市场组件不可用")
                return
            ok = installer.install(self._meta)
            if ok:
                self.ok.emit(name)
            else:
                self.fail.emit(name, "安装失败（详见日志）")
        except Exception as e:
            logger.error(f"[{_PLUGIN_NAME}] 安装 {name} 异常: {e}")
            self.fail.emit(name, str(e))


class _InstallCoordinator(QObject):
    """驻主线程的安装结果协调器：弹通知 + 刷新推荐列表"""

    def __init__(self, main_widget, window_id: str):
        super().__init__()
        self._mw = main_widget
        self._window_id = window_id

    def on_ok(self, name: str):
        with _installing_lock:
            _installing.discard(name)
        self._reshuffle()
        self._infobar("success", "插件已安装", f"{name} 安装完成，已自动启用")

    def on_fail(self, name: str, error: str):
        with _installing_lock:
            _installing.discard(name)
        self._infobar("error", "插件安装失败", f"{name}: {error[:120]}")

    def _reshuffle(self):
        """强制欢迎卡片重渲染（重走 render_func：重随机 + 重过滤已安装）"""
        try:
            card = getattr(self._mw, "_welcome_card_cache", {}).get(self._window_id)
            if card is not None and hasattr(card, "set_welcome_mode"):
                card.set_welcome_mode(card._welcome_mode)
        except Exception as e:
            logger.warning(f"[{_PLUGIN_NAME}] 欢迎卡片刷新失败: {e}")

    def _infobar(self, level: str, title: str, content: str):
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition

            factory = getattr(InfoBar, level)
            factory(
                title=title,
                content=content,
                parent=self._mw,
                position=InfoBarPosition.BOTTOM,
                duration=3500,
            )
        except Exception as e:
            logger.warning(f"[{_PLUGIN_NAME}] InfoBar 显示失败: {e}")


def _find_meta(name: str) -> Dict[str, Any] | None:
    """按名取插件 meta（市场数据缓存优先，未就绪现拉）"""
    from .render import _get_marketplace_data

    for meta in _get_marketplace_data():
        if meta.get("name") == name:
            return meta
    return None


def handle_install(content: str, ctx: Dict[str, Any]):
    """点击安装：name → 后台 install → 主线程通知 + 刷新"""
    name = content.strip()
    if not name:
        return
    coordinator = _InstallCoordinator(ctx.get("main_widget"), ctx.get("window_id", ""))
    with _installing_lock:
        if name in _installing:
            coordinator._infobar("info", "正在安装中", f"{name} 正在后台安装，请稍候")
            return
        meta = _find_meta(name)
        if meta is None:
            coordinator._infobar("warning", "未找到插件", f"市场数据中不存在 {name}")
            return
        _installing.add(name)
    coordinator._infobar("info", "开始安装", f"{name} 正在后台安装…")
    worker = _InstallWorker(meta)
    # 保引用防 GC（局部变量被回收 → 完成信号丢失、无任何反馈）
    job = (worker, coordinator)
    _active_jobs.append(job)
    worker.ok.connect(coordinator.on_ok)
    worker.fail.connect(coordinator.on_fail)
    worker.finished.connect(lambda: _active_jobs.remove(job) if job in _active_jobs else None)
    worker.start()


def handle_shuffle(content: str, ctx: Dict[str, Any]):
    """换一批：仅重新随机抽样 + 重渲染（数据复用市场缓存，不重新拉取）"""
    try:
        mw = ctx.get("main_widget")
        card = getattr(mw, "_welcome_card_cache", {}).get(ctx.get("window_id", ""))
        if card is not None and hasattr(card, "set_welcome_mode"):
            card.set_welcome_mode(card._welcome_mode)
    except Exception as e:
        logger.warning(f"[{_PLUGIN_NAME}] 换一批失败: {e}")


ACTIONS = {
    render._ACTION_INSTALL: handle_install,
    render._ACTION_SHUFFLE: handle_shuffle,
}
