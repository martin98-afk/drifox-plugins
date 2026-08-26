# -*- coding: utf-8 -*-
"""workbuddy UI 组件入口

注册浮动卡片「产物」与 /artifacts 命令：
- /artifacts  打开/聚焦产物面板（自动刷新）

热重载语义（与 UIPluginRegistry.load_plugin 调用约定一致）：
1. 清理 sys.modules 中残留的 ui_plugin_workbuddy.* 子模块缓存
2. 注册浮动卡片（自动注册 /artifacts 命令）
3. 注册 _state 监听者：新 artifact 写入时刷新并弹出已实例化的面板
4. 通过 FunctionCommandHandlers 覆盖默认 handler，绑定卡片实例

错误隔离：单步异常不影响其余步骤（面板注册失败不阻塞其他 UI 组件加载）
"""
import sys
from pathlib import Path

# 注入插件根到 sys.path 以便 ui 子模块跨模块导入 _state
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from loguru import logger
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, Qt  # noqa: E402

# 模块级 state 监听者句柄（热重载时调用 unregister_listener 清理）
_UNREGISTER_LISTENER = None
# 模块级主线程桥接器（后台线程的 state listener 经它触发卡片显示）
_POPUP_BRIDGE = None


class _PopupBridge(QObject):
    """主线程桥接器：后台线程的 state listener 经它安全地触发卡片显示。"""

    _requested = pyqtSignal()

    def __init__(self, registry):
        super().__init__()
        self._registry = registry
        self._requested.connect(self._do_popup, Qt.QueuedConnection)
        # 线程归属加固：插件热重载链路可能在后台线程执行 register_ui，
        # 若 bridge 在非主线程构造，其 QueuedConnection 槽会投递到无事件
        # 循环的后台线程 → 永不执行（自动弹窗静默失败的根因之一）。
        # 构造后迁移到主线程，保证槽在主线程事件循环中执行。
        try:
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None and self.thread() is not app.thread():
                self.moveToThread(app.thread())
        except Exception:
            pass

    @pyqtSlot()
    def _do_popup(self):
        from .artifact_panel import ArtifactPanelCard

        card = ArtifactPanelCard._instance
        if card is not None and card.isVisible():
            card.refresh()
            card.raise_()
            return
        # 未显示 → 主线程创建/显示（toggle 在隐藏态=显示，不会误隐藏已显示卡片）
        try:
            self._registry.toggle_floating_card("artifacts")
        except Exception:
            logger.exception("[workbuddy] 弹出产物卡片失败")
        card = ArtifactPanelCard._instance
        if card is not None:
            card.refresh()
            if not card.isVisible():
                # registry 路径静默失败（如 host 未就绪）→ 兜底直接显示
                logger.warning("[workbuddy] toggle 后卡片仍不可见，直接 show 兜底")
                card.show()
            card.raise_()
        else:
            logger.warning("[workbuddy] 弹窗后仍无卡片实例（floating card 注册可能未生效）")


def register_ui(registry):
    """注册 workbuddy 插件的 UI 组件（浮动卡片 + function 命令）"""
    global _UNREGISTER_LISTENER, _POPUP_BRIDGE

    # 1) 清理旧子模块缓存，避免热重载后 Python 复用旧 .pyc
    prefix = "ui_plugin_workbuddy."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    # 2) 卸载旧 listener（热重载路径）
    if _UNREGISTER_LISTENER is not None:
        try:
            _UNREGISTER_LISTENER()
        except Exception:
            pass
        _UNREGISTER_LISTENER = None

    try:
        from .artifact_panel import ArtifactPanelCard
        from app.core.builtin_commands import FunctionCommandHandlers
        import _state
    except Exception:
        logger.exception("[workbuddy] UI 模块导入失败")
        return

    # 3) 注册浮动卡片（自动注册 /artifacts 命令）
    try:
        registry.register_floating_card(
            plugin_name="workbuddy",
            card_id="artifacts",
            widget_class=ArtifactPanelCard,
            container="right",
            title="产物",
            default_visible=False,
        )
    except Exception:
        logger.exception("[workbuddy] 浮动卡片注册失败")
        return

    # 创建主线程桥接器，供 state listener 跨线程安全地弹出卡片
    _POPUP_BRIDGE = _PopupBridge(registry)

    # 4) 注册 state 监听者：新 artifact 写入时刷新、弹出面板并聚焦对应 tab
    def _on_state_change(workdir: str, entry: dict) -> None:
        items = (entry or {}).get("items") or []
        if items:
            # 聚焦本次 present 的最后一个产物（refresh 时消费）
            ArtifactPanelCard.request_focus(
                items[-1].get("absolute") or items[-1].get("path", "")
            )
        card = ArtifactPanelCard._instance
        if card is None:
            # 卡片懒加载尚未实例化 → 经主线程桥接器创建并显示
            if _POPUP_BRIDGE is not None:
                _POPUP_BRIDGE._requested.emit()
            return
        # 跨线程安全：仅 emit 信号，真正的 UI 操作由 _do_auto_popup 槽
        # 经 Qt.QueuedConnection 投递到主线程执行，避免后台线程
        # （ChatWorker / SubAgentWorker）直接操作 Qt 对象导致 C++ 崩溃
        card._auto_popup.emit()

    _UNREGISTER_LISTENER = _state.register_listener(_on_state_change)

    # 5) 覆盖默认 handler，绑定类级单例引用
    FunctionCommandHandlers.register("artifacts", _handle_artifacts_command)
    logger.info("[workbuddy] UI components registered")


def _handle_artifacts_command(args: str = "", owner=None):
    """/artifacts 命令 handler：刷新并显示产物面板"""
    try:
        from .artifact_panel import ArtifactPanelCard
        if ArtifactPanelCard._instance is not None:
            ArtifactPanelCard._instance.refresh()
            ArtifactPanelCard._instance.show()
            ArtifactPanelCard._instance.raise_()
            return True
        return False
    except Exception:
        logger.exception("[workbuddy] /artifacts 命令失败")
        return False


def unload_ui(registry):
    """插件卸载/热重载回调（释放模块级状态）"""
    global _UNREGISTER_LISTENER, _POPUP_BRIDGE
    _POPUP_BRIDGE = None
    if _UNREGISTER_LISTENER is not None:
        try:
            _UNREGISTER_LISTENER()
        except Exception:
            pass
        _UNREGISTER_LISTENER = None
    try:
        from .artifact_panel import cleanup
        cleanup()
    except Exception:
        pass