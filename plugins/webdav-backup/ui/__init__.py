# -*- coding: utf-8 -*-
"""webdav-backup UI 组件入口 — 注册备份中心卡（full 覆盖对话区，经侧边栏插件列表弹出）"""

import sys
from pathlib import Path

from loguru import logger

# 插件根加入 sys.path（自包含：core 以 webdavbackup_core.* 导入）
_PLUGIN_ROOT = Path(__file__).parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def register_ui(registry):
    """注册 webdav-backup 的 UI 组件（热重载兼容：清理 sys.modules 残留缓存）

    只清子模块（ui_plugin_webdav_backup.*）与 webdavbackup_core 包，
    不清当前模块自身（相对导入 `from .cards` 需要父包在 sys.modules 中）。
    """
    for k in list(sys.modules):
        if k.startswith("ui_plugin_webdav_backup."):
            del sys.modules[k]
    for k in list(sys.modules):
        if k == "webdavbackup_core" or k.startswith("webdavbackup_core."):
            del sys.modules[k]

    from .cards import WebDavBackupCard

    # 备份中心卡（full 覆盖对话区；经左侧边栏插件列表 / /webdav-backup:backup 命令弹出）
    registry.register_floating_card(
        plugin_name="webdav-backup",
        card_id="backup",
        widget_class=WebDavBackupCard,
        container="full",
        title="WebDAV 备份",
        default_visible=False,
    )

    # 提前启动调度器：UI 未打开时定时备份也照常执行
    # takeover()：停掉上一代实例（热重载后旧 QTimer 只有此处够得着），防多套调度器并存
    from webdavbackup_core.scheduler import BackupScheduler

    BackupScheduler.takeover().ensure_started()

    logger.info("[webdav-backup] UI components registered")


def unload_ui(registry):
    """卸载回调：停调度器 + 清单例锚点"""
    try:
        from webdavbackup_core.scheduler import BackupScheduler, _write_anchor

        BackupScheduler.get_instance().stop()
        _write_anchor(None)
        logger.info("[webdav-backup] unload_ui: 调度器已停止")
    except Exception as e:
        logger.warning(f"[webdav-backup] unload_ui 清理失败: {e}")
