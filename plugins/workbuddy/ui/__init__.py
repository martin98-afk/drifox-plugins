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

# 模块级 state 监听者句柄（热重载时调用 unregister_listener 清理）
_UNREGISTER_LISTENER = None


def register_ui(registry):
    """注册 workbuddy 插件的 UI 组件（浮动卡片 + function 命令）"""
    global _UNREGISTER_LISTENER

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

    # 4) 注册 state 监听者：新 artifact 写入时刷新并弹出已实例化的面板
    def _on_state_change(workdir: str, _entry: dict) -> None:
        card = ArtifactPanelCard._instance
        if card is None:
            return  # 用户尚未手动打开过面板，跳过弹窗
        # 仅刷新当前 workdir 匹配的面板
        if card._workdir and card._workdir != workdir:
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
    global _UNREGISTER_LISTENER
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