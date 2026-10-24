# -*- coding: utf-8 -*-
"""ssh-toolkit UI 组件入口 — 系统设置页「SSH 远程连接」管理卡

AI 通过 ssh_add_connection 保存的连接，与本卡共享同一份配置
（~/.drifox/cache/ssh/connections.json），因此设置页始终反映 AI 的最新操作。

职责边界（v0.2.0 起）：
- 设置页只做**审查与删除**，新增/编辑继续交给 AI 工具完成。
- 删除时同步断开该连接名下的活跃连接与端口转发，避免旧配置复活。
"""

import sys

from loguru import logger

PLUGIN_NAME = "ssh-toolkit"


def register_ui(registry):
    """注册 ssh-toolkit 的 UI 组件。

    热重载兼容：主程序按 safe_name（连字符转下划线）生成 ui_plugin_ 前缀模块名，
    需清理上次加载残留的子模块缓存，否则改动不生效。
    """
    prefix = "ui_plugin_ssh_toolkit."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    from .connections_card import register_connections_card

    register_connections_card(registry)
    logger.info("[ssh-toolkit] UI components registered")


def unload_ui(registry):
    """卸载钩子。可达性探测是短命 QRunnable（TCP 超时 3s），跑完即弃；
    结果经主线程出生的模块级信号桥投递，卡片销毁后由 Qt 自动丢弃，无残留。"""
