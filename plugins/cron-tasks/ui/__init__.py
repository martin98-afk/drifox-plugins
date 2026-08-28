# -*- coding: utf-8 -*-
"""cron-tasks UI 组件入口 — 注册任务中心卡 + 输入区按钮（模式对齐 autoloop）"""

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

    # 任务中心卡（full 覆盖对话区；hide_sidebar：经输入按钮/命令弹出）
    registry.register_floating_card(
        plugin_name="cron-tasks",
        card_id="tasks",
        widget_class=CronTasksCard,
        container="full",
        title="定时任务",
        default_visible=False,
        metadata={"hide_sidebar": True},
    )

    # 输入区按钮（深色主题 clock_light.svg 白色线条；浅色主题 clock.svg 深色线条）
    _dark_icon = _PLUGIN_ROOT / "icons" / "clock_light.svg"
    _light_icon = _PLUGIN_ROOT / "icons" / "clock.svg"
    registry.register_input_button(
        plugin_name="cron-tasks",
        button_id="cron-tasks",
        icon_path=str(_dark_icon) if _dark_icon.exists() else "",
        icon_light_path=str(_light_icon) if _light_icon.exists() else "",
        tooltip="定时任务 — 可视化配置单次/间隔/Cron 定时执行",
        on_click=_on_input_button_clicked,
        position="before:memory",  # 插到「长期记忆」按钮左边
    )

    # 卡片实例化时绑定 controller（经 widget_class 包装不可行 → 用卡片 showEvent 内
    # ensure_started；此处提前启动调度器，保证 UI 未打开时任务也按时执行）
    _patch_card_binding()

    logger.info("[cron-tasks] UI components registered")


def _patch_card_binding():
    """为卡片类挂 on_created 钩子式绑定：实例化后向 controller 注册

    UIPluginRegistry 创建卡片实例后调用 set_context_provider；
    我们在卡片第一次 showEvent 时经 ensure_started 完成绑定（见 cards.py），
    这里只需保证调度器先启动（无 services 时 tick 自动推迟到期任务）。
    """
    from .controller import CronTasksController

    ctrl = CronTasksController.get_instance()
    ctrl.ensure_started()


def _on_input_button_clicked(context):
    """输入区按钮点击 — 切换任务中心卡显示"""
    from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

    UIPluginRegistry.get_instance().toggle_floating_card(
        "tasks", main_widget=context.get("main_widget")
    )


def unload_ui(registry):
    """卸载回调：停调度器 + 取消运行中任务 + 单例归零"""
    try:
        from .controller import CronTasksController

        ctrl = CronTasksController.get_instance()
        ctrl.shutdown_all()
        CronTasksController._instance = None
        logger.info("[cron-tasks] unload_ui: 调度器已停止，单例已归零")
    except Exception as e:
        logger.warning(f"[cron-tasks] unload_ui 清理失败: {e}")
