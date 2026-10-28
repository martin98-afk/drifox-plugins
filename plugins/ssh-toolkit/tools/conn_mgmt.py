# ssh-toolkit/tools/conn_mgmt.py
# -*- coding: utf-8 -*-
"""连接查看 / 删除（本地配置，safe）。

保存不再有独立工具：`ssh_connect` 连成功即自动落库（见 exec_tool._connect_impl），
无名的直连按 user@host 命名，同名重复连接只刷新「最后连接时间」与次数。
"""
import sys
from pathlib import Path

# PluginToolLoader 用 importlib 加载本模块，注入 tools/ 目录到 sys.path 以便绝对导入
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.result import ToolResult  # noqa: E402

import _store as store  # noqa: E402


def _list_impl(tool_ctx, **kwargs):
    data = store.mask_passwords(store.load_connections())
    conns = data["connections"]
    if not conns:
        return ToolResult(True, content="（无已保存连接，连接一次即自动记录）")
    lines = []
    for c in conns:
        lines.append(
            f"{c['name']}  {c.get('user','')}@{c.get('host','')}:{c.get('port',22)}"
            f"  [{c.get('auth_type','')}]  最后连接 {c.get('last_connected') or '未知'}"
        )
    return ToolResult(True, content="\n".join(lines))


def _remove_impl(tool_ctx, **kwargs):
    name = kwargs.get("name")
    ok = store.remove_connection(name)
    if ok:
        return ToolResult(True, content=f"已删除连接：{name}")
    return ToolResult(False, error=f"未找到连接：{name}")


def register(registry):
    registry.register(
        "ssh_list_connections",
        {"type": "function", "function": {
            "name": "ssh_list_connections",
            "description": "列出所有已保存的 SSH 连接（密码掩码，含最后连接时间）",
            "parameters": {"type": "object", "properties": {}},
        }},
        impl=_list_impl, danger="safe", icon="ssh_conn", cn_name="SSH 列出连接", group="SSH 远程",
        description="列出已保存的 SSH 连接",
    )
    registry.register(
        "ssh_remove_connection",
        {"type": "function", "function": {
            "name": "ssh_remove_connection",
            "description": "删除一个已保存的 SSH 连接",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "连接名"},
            }, "required": ["name"]},
        }},
        impl=_remove_impl, danger="safe", icon="ssh_conn", cn_name="SSH 删除连接", group="SSH 远程",
        description="删除已保存的 SSH 连接",
    )
