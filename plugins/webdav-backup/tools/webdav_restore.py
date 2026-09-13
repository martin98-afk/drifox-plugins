# -*- coding: utf-8 -*-
"""webdav_restore — 从 WebDAV 备份恢复 DriFox 数据（webdav-backup 插件 tools 组件）

危险操作：覆盖本地数据目录。恢复前自动留回滚副本；完成后必须重启 DriFox。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 插件根加入 sys.path（tools 加载器不保证 UI 侧已注入；幂等）
_PLUGIN_ROOT = Path(__file__).parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from webdavbackup_core.host_compat import make_tool_result as ToolResult  # noqa: E402  自包含收口：主程序 ToolResult 缺失时降级为 str


def _impl(tool_ctx, backup_name: str = "", encryption_password: str = "", **kwargs):
    name = (backup_name or "").strip()
    if not name:
        # 未指定时列出可选项，避免盲恢复
        from webdavbackup_core import engine

        r = engine.run_list()
        items = r.get("items") or []
        if not items:
            return ToolResult(False, content=f"无法列出云端备份: {r.get('message', '列表为空')}")
        lines = ["请指定要恢复的备份名（backup_name 参数），可选："]
        for it in items[:20]:
            lines.append(f"- {it.get('name')}")
        return ToolResult(False, content="\n".join(lines))

    from webdavbackup_core import engine

    r = engine.run_restore(name, encryption_password=encryption_password)
    msg = str(r.get("message", ""))
    rb = r.get("rollback_dir")
    if rb:
        msg += f"\n回滚副本目录: {rb}"
    return ToolResult(bool(r.get("ok")), content=msg)


def register(registry):
    registry.register(
        "webdav_restore",
        {
            "type": "function",
            "function": {
                "name": "webdav_restore",
                "description": "从 WebDAV 云端备份恢复 DriFox 数据（覆盖本地会话/配置/插件数据），完成后需重启 DriFox。危险操作，需用户明确要求后才调用",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "backup_name": {
                            "type": "string",
                            "description": "备份文件名，如 drifox-backup-20260914-120000.zip；不传则列出可选备份",
                        },
                        "encryption_password": {
                            "type": "string",
                            "description": "可选：加密备份包的密码（未设置时使用插件配置里的密码）",
                        },
                    },
                },
            },
        },
        impl=_impl,
        danger="dangerous",
        icon="cloud",
        cn_name="WebDAV 恢复",
        group="数据备份",
        description="从 WebDAV 备份恢复 DriFox 数据（覆盖本地，需重启）",
    )
