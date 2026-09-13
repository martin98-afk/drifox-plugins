# -*- coding: utf-8 -*-
"""webdav_backup — WebDAV 备份管理工具（webdav-backup 插件 tools 组件）

action 分发：test（测试连接）/ list（列出云端备份）/ backup（立即备份）
全部为只读或追加型操作（上传不影响本地数据），safe。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 插件根加入 sys.path（tools 加载器不保证 UI 侧已注入；幂等）
_PLUGIN_ROOT = Path(__file__).parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from webdavbackup_core.host_compat import make_tool_result as ToolResult  # noqa: E402  自包含收口：主程序 ToolResult 缺失时降级为 str

_ACTIONS = ("test", "list", "backup")


def _impl(tool_ctx, action: str = "test", **kwargs):
    action = (action or "test").strip().lower()
    if action not in _ACTIONS:
        return ToolResult(False, content=f"未知 action: {action!r}，可选: {', '.join(_ACTIONS)}")

    from webdavbackup_core import engine

    if action == "test":
        r = engine.run_test()
    elif action == "list":
        r = engine.run_list()
    else:
        r = engine.run_backup()

    lines = [str(r.get("message", ""))]
    if action == "backup":
        skipped = r.get("skipped") or []
        if skipped:
            lines.append("跳过: " + "; ".join(skipped[:5]) + ("…" if len(skipped) > 5 else ""))
    if action == "list":
        items = r.get("items") or []
        for it in items[:20]:
            size = it.get("size") or 0
            lines.append(f"- {it.get('name')} ({size / 1048576:.1f} MB)")
        if len(items) > 20:
            lines.append(f"… 共 {len(items)} 份")
    return ToolResult(bool(r.get("ok")), content="\n".join(lines))


def register(registry):
    registry.register(
        "webdav_backup",
        {
            "type": "function",
            "function": {
                "name": "webdav_backup",
                "description": "WebDAV 备份管理：测试连接（test）、列出云端备份（list）、立即执行全量备份（backup）。备份内容为 DriFox 数据目录（会话/配置/插件数据）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": list(_ACTIONS),
                            "description": "要执行的动作，默认 test",
                        }
                    },
                },
            },
        },
        impl=_impl,
        danger="safe",
        icon="cloud",
        cn_name="WebDAV 备份",
        group="数据备份",
        description="通过 WebDAV（坚果云/Nextcloud）备份或查看 DriFox 数据",
    )
