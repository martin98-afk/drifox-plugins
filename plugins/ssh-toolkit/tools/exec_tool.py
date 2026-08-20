# ssh-toolkit/tools/exec_tool.py
# -*- coding: utf-8 -*-
"""SSH 连接 / 命令执行 / 断开（dangerous 除断开外）。"""
import sys
from pathlib import Path

# PluginToolLoader 用 importlib 加载本模块，注入 tools/ 目录到 sys.path 以便绝对导入
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.result import ToolResult  # noqa: E402

import _store as store, _auth as auth, _pool as pool  # noqa: E402


def _connect_impl(tool_ctx, **kwargs):
    name = kwargs.get("name")
    conn = store.get_connection(name)
    if conn is None:
        # 允许运行时直接传连接参数
        conn = {k: kwargs.get(k) for k in ("name", "host", "port", "user", "auth_type", "key_path", "password", "key_passphrase", "timeout")}
        if not conn.get("host") or not conn.get("user"):
            return ToolResult(False, content=f"未找到连接 {name}，且未提供 host/user")
    try:
        client = auth.connect(conn)
    except Exception as e:
        return ToolResult(False, content=f"连接失败：{e}")
    handle = pool.put_connection(name, client)
    return ToolResult(True, content=f"已连接 {name or conn.get('host')}，handle={handle}")


def _exec_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    client = pool.get_client(ref) if ref else None
    if client is None:
        return ToolResult(False, content=f"未找到活跃连接：{ref}（先 ssh_connect）")
    command = kwargs.get("command", "")
    timeout = int(kwargs.get("timeout", 30))
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
    except Exception as e:
        return ToolResult(False, content=f"执行失败：{e}")
    body = f"$ {command}\n{out}{err}\nexit={code}"
    return ToolResult(True, content=body)


def _disconnect_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name") or kwargs.get("forward_id")
    if ref and pool.remove_connection_handle(ref):
        return ToolResult(True, content=f"已断开：{ref}")
    return ToolResult(True, content=f"未找到活跃连接：{ref}（可能已断开）")


def register(registry):
    registry.register(
        "ssh_connect",
        {"type": "function", "function": {
            "name": "ssh_connect",
            "description": "建立 SSH 连接并加入连接池，返回 handle（供 ssh_exec 等复用）",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "已保存连接名；或运行时 host/user 直接连"},
                "host": {"type": "string", "description": "主机（运行时直连时用）"},
                "port": {"type": "integer", "description": "端口"},
                "user": {"type": "string", "description": "用户名"},
                "auth_type": {"type": "string", "description": "认证方式"},
                "key_path": {"type": "string", "description": "私钥路径"},
                "password": {"type": "string", "description": "密码"},
                "key_passphrase": {"type": "string", "description": "私钥口令"},
                "timeout": {"type": "integer", "description": "超时秒"},
            }, "required": []},
        }},
        impl=_connect_impl, danger="dangerous", icon="ssh", cn_name="SSH 连接", group="SSH 远程",
        description="建立 SSH 连接",
    )
    registry.register(
        "ssh_exec",
        {"type": "function", "function": {
            "name": "ssh_exec",
            "description": "在已连接主机上执行命令，返回 stdout/stderr/exit code",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "ssh_connect 返回的 handle，或连接名"},
                "name": {"type": "string", "description": "连接名（无 handle 时用）"},
                "command": {"type": "string", "description": "要执行的 shell 命令"},
                "timeout": {"type": "integer", "description": "执行超时秒，默认 30"},
            }, "required": ["command"]},
        }},
        impl=_exec_impl, danger="dangerous", icon="ssh", cn_name="SSH 执行命令", group="SSH 远程",
        description="在远程主机执行命令",
    )
    registry.register(
        "ssh_disconnect",
        {"type": "function", "function": {
            "name": "ssh_disconnect",
            "description": "关闭 SSH 连接或端口转发",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "forward_id": {"type": "string", "description": "端口转发 id"},
            }, "required": []},
        }},
        impl=_disconnect_impl, danger="safe", icon="ssh", cn_name="SSH 断开", group="SSH 远程",
        description="关闭 SSH 连接/转发",
    )
