# -*- coding: utf-8 -*-
"""taskboard UI 组件入口

- 注册浮动卡片「任务看板」（container="right"：与浏览器卡同容器互斥，
  打开看板即替换浏览器插槽，关闭后浏览器可重新切回）
"""

import sys
from pathlib import Path

from loguru import logger

# 插件根加入 sys.path（自包含：core/worker 以 taskboard_core.* 导入）
_PLUGIN_ROOT = Path(__file__).parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def register_ui(registry):
    """注册 taskboard 的 UI 组件

    热重载兼容：清理 sys.modules 残留缓存，确保重新编译。
    """
    prefix = "ui_plugin_taskboard."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]
    # taskboard_core 包缓存同样清理（热重载后 worker/controller 需重新加载）
    stale_core = [k for k in sys.modules if k == "taskboard_core" or k.startswith("taskboard_core.")]
    for k in stale_core:
        del sys.modules[k]

    from .board_card import TaskBoardCard

    # 看板卡（right 停靠：替换插槽 — 同容器与 browser 卡互斥切换）
    registry.register_floating_card(
        plugin_name="taskboard",
        card_id="taskboard",
        widget_class=TaskBoardCard,
        container="right",
        title="任务看板",
        default_visible=False,
    )
    logger.info("[taskboard] UI components registered")


def unload_ui(registry):
    """卸载回调（热重载/卸载时由 UIPluginRegistry.unload_plugin 调用）

    停掉全部运行中的任务 worker 并归零控制器单例——
    热重载期间运行中的任务处理会被安全终止并保留看板数据。
    """
    from loguru import logger

    try:
        from .controller import TaskBoardController

        ctrl = TaskBoardController.get_instance()
        ctrl.shutdown()
        logger.info("[taskboard] unload_ui: controller 单例已归零，全部任务已停止")
    except Exception as e:
        logger.warning(f"[taskboard] unload_ui 清理失败: {e}")
