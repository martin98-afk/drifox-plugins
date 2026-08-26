# -*- coding: utf-8 -*-
"""cron-chat UI 组件入口 — 注册主卡（任务列表/编辑/运行记录）+ 输入区按钮"""

import sys
from pathlib import Path

from loguru import logger

# 插件根加入 sys.path（自包含：cards 以 cron_core.* 导入，与 autoloop 的 deps 模式一致）
_PLUGIN_ROOT = Path(__file__).parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def register_ui(registry):
    """注册 cron-chat 的 UI 组件（热重载兼容：清理 sys.modules 残留缓存）"""
    prefix = "ui_plugin_cron_chat."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]
    # cron_core 包缓存同样清理（热重载后 scheduler/runner 需重新加载）
    stale_core = [k for k in sys.modules if k == "cron_core" or k.startswith("cron_core.")]
    for k in stale_core:
        del sys.modules[k]

    from .cards import CronChatCard

    # 主卡（full 覆盖对话区；hide_sidebar：仅经输入按钮/命令弹出）
    registry.register_floating_card(
        plugin_name="cron-chat",
        card_id="main",
        widget_class=CronChatCard,
        container="full",
        title="CronChat 定时任务",
        default_visible=False,
        metadata={"hide_sidebar": True},
    )
    # 输入区按钮
    _icon = _PLUGIN_ROOT / "icons" / "定时.svg"
    registry.register_input_button(
        plugin_name="cron-chat",
        button_id="cron-chat",
        icon_path=str(_icon) if _icon.exists() else "",
        tooltip="CronChat 定时任务（定时触发的自动化对话）",
        on_click=_on_input_button_clicked,
    )
    logger.info("[cron-chat] UI components registered")


def _on_input_button_clicked(context):
    """输入区按钮点击 — 切换主卡显示"""
    from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

    UIPluginRegistry.get_instance().toggle_floating_card("main", main_widget=context.get("main_widget"))


def unload_ui(registry):
    """卸载回调：停调度器 + 停执行中的 worker + 控制器单例归零（热重载安全）"""
    try:
        from .controller import CronChatController

        controller = CronChatController.get_instance()
        controller.shutdown()
        CronChatController._instance = None
        logger.info("[cron-chat] unload_ui: controller 单例已归零，调度器已停止")
    except Exception as e:
        logger.warning(f"[cron-chat] unload_ui 清理失败: {e}")
