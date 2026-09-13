# -*- coding: utf-8 -*-
"""cron-tasks UI 组件入口 — 注册任务中心卡（full 覆盖对话区，经侧边栏插件列表弹出）"""

import sys
from pathlib import Path

from loguru import logger

# 插件根加入 sys.path（自包含：core 以 crontasks_core.* 导入）
_PLUGIN_ROOT = Path(__file__).parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def register_ui(registry):
    """注册 cron-tasks 的 UI 组件（热重载兼容：清理 sys.modules 残留缓存）

    注意：只清子模块（ui_plugin_cron_tasks.*）与 crontasks_core 包，
    不清当前模块自身（相对导入 `from .cards` 需要父包在 sys.modules 中）。
    """
    for k in list(sys.modules):
        if k.startswith("ui_plugin_cron_tasks."):
            del sys.modules[k]
    for k in list(sys.modules):
        if k == "crontasks_core" or k.startswith("crontasks_core."):
            del sys.modules[k]

    from .cards import CronTasksCard

    # 任务中心卡（full 覆盖对话区；经左侧边栏插件列表 / /cron-tasks:tasks 命令弹出）
    registry.register_floating_card(
        plugin_name="cron-tasks",
        card_id="tasks",
        widget_class=CronTasksCard,
        container="full",
        title="定时任务",
        default_visible=False,
    )

    # 卡片实例化时绑定 controller（经 widget_class 包装不可行 → 用卡片 showEvent 内
    # ensure_started；此处提前启动调度器，保证 UI 未打开时任务也按时执行）
    _patch_card_binding()

    logger.info("[cron-tasks] UI components registered")


def _patch_card_binding():
    """新一代接棒 + 启动调度器

    UIPluginRegistry 创建卡片实例后调用 set_context_provider；
    我们在卡片第一次 showEvent 时经 ensure_started 完成绑定（见 cards.py）。
    此处提前启动调度器，保证 UI 未打开时任务也按时执行。

    必须用 takeover() 而非 get_instance()：热重载场景下锚点里可能还挂着
    上一代实例，它在进程内已无其他入口可停（unload_ui 只对新模块可见），
    漏停会留下仍在 tick 的 QTimer + 运行中的 executor（多套调度器并存，
    状态错位、任务卡死后只能重启软件）。
    """
    from .controller import CronTasksController

    ctrl = CronTasksController.takeover()
    ctrl.ensure_started()


def unload_ui(registry):
    """卸载回调：停调度器 + 取消运行中任务 + 清单例锚点"""
    try:
        from .controller import CronTasksController, _write_anchor

        ctrl = CronTasksController.get_instance()
        ctrl.shutdown_all()
        _write_anchor(None)
        logger.info("[cron-tasks] unload_ui: 调度器已停止，单例已归零")
    except Exception as e:
        logger.warning(f"[cron-tasks] unload_ui 清理失败: {e}")
