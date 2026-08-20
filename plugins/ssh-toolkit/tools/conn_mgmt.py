# ssh-toolkit/tools/conn_mgmt.py
# -*- coding: utf-8 -*-
"""连接管理工具：增 / 列 / 删（本地配置，safe）。"""
import sys
from pathlib import Path

# PluginToolLoader 用 importlib 加载本模块，注入 tools/ 目录到 sys.path 以便绝对导入
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.result import ToolResult  # noqa: E402

import _store as store  # noqa: E402


def _add_impl(tool_ctx, **kwargs):
    conn = {
        "name": kwargs.get("name"),
        "host": kwargs.get("host"),
        "port": int(kwargs.get("port", 22)),
        "user": kwargs.get("user"),
        "auth_type": kwargs.get("auth_type", "publickey"),
        "key_path": kwargs.get("key_path", "~/.ssh/id_rsa"),
        "password": kwargs.get("password", ""),
        "key_passphrase": kwargs.get("key_passphrase", ""),
        "timeout": int(kwargs.get("timeout", 10)),
        "note": kwargs.get("note", ""),
    }
    try:
        store.add_connection(conn)
    except ValueError as e:
        return ToolResult(False, content=str(e))
    return ToolResult(True, content=f"已保存连接：{conn['name']} ({conn['user']}@{conn['host']}:{conn['port']})")


def _list_impl(tool_ctx, **kwargs):
    data = store.mask_passwords(store.load_connections())
    conns = data["connections"]
    if not conns:
        return ToolResult(True, content="（无已保存连接）")
    lines = [f"{c['name']}  {c.get('user','')}@{c.get('host','')}:{c.get('port',22)}  [{c.get('auth_type','')}]" for c in conns]
    return ToolResult(True, content="\n".join(lines))


def _remove_impl(tool_ctx, **kwargs):
    name = kwargs.get("name")
    ok = store.remove_connection(name)
    if ok:
        return ToolResult(True, content=f"已删除连接：{name}")
    return ToolResult(False, content=f"未找到连接：{name}")


def register(registry):
    registry.register(
        "ssh_add_connection",
        {"type": "function", "function": {
            "name": "ssh_add_connection",
            "description": "保存一个命名 SSH 连接配置到本地（~/.drifox/cache/ssh/connections.json）",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "连接名（唯一标识）"},
                "host": {"type": "string", "description": "主机地址"},
                "port": {"type": "integer", "description": "SSH 端口，默认 22"},
                "user": {"type": "string", "description": "登录用户名"},
                "auth_type": {"type": "string", "description": "认证方式: publickey/password/keyboard-interactive/agent"},
                "key_path": {"type": "string", "description": "私钥路径（publickey/agent）"},
                "password": {"type": "string", "description": "密码（明文存储，注意安全）"},
                "key_passphrase": {"type": "string", "description": "私钥口令"},
                "timeout": {"type": "integer", "description": "连接超时秒"},
                "note": {"type": "string", "description": "备注"},
            }, "required": ["name", "host", "user"]},
        }},
        impl=_add_impl, danger="safe", icon="ssh", cn_name="SSH 保存连接", group="SSH 远程",
        description="保存命名 SSH 连接配置",
    )
    registry.register(
        "ssh_list_connections",
        {"type": "function", "function": {
            "name": "ssh_list_connections",
            "description": "列出所有已保存的 SSH 连接（密码掩码）",
            "parameters": {"type": "object", "properties": {}},
        }},
        impl=_list_impl, danger="safe", icon="ssh", cn_name="SSH 列出连接", group="SSH 远程",
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
        impl=_remove_impl, danger="safe", icon="ssh", cn_name="SSH 删除连接", group="SSH 远程",
        description="删除已保存的 SSH 连接",
    )
