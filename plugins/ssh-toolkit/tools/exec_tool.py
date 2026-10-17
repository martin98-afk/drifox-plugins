# ssh-toolkit/tools/exec_tool.py
# -*- coding: utf-8 -*-
"""SSH 连接 / 命令执行 / 断开（dangerous 除断开外）。"""
import sys
import time
from pathlib import Path

# PluginToolLoader 用 importlib 加载本模块，注入 tools/ 目录到 sys.path 以便绝对导入
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.result import ToolResult  # noqa: E402

import _store as store, _auth as auth, _pool as pool  # noqa: E402

# 单流输出上限：`timeout` 只约束单次 recv，不是总时长。远端 `yes` / `cat
# /dev/urandom` 会持续灌数据，无上限的 read() 会把宿主进程直接 OOM。
MAX_OUTPUT_BYTES = 256 * 1024


def _read_streams(chan, limit, deadline):
    """同时收集 stdout/stderr，返回 (out_bytes, err_bytes, truncated)。

    必须两路同轮询：只看一路的话，另一路写满 SSH 窗口（默认 64KB）后远端
    会阻塞在 write，本端永远等不到 EOF → 看似“卡住”实际是锁死。
    """
    outs, errs = [], []
    n_out = n_err = 0
    truncated = False
    while True:
        progressed = False
        if n_out < limit and chan.recv_ready():
            data = chan.recv(min(32768, limit - n_out))
            if data:
                outs.append(data)
                n_out += len(data)
                progressed = True
        elif n_out >= limit and chan.recv_ready():
            # 达上限且仍有待读数据：直接退出，由调用方关通道（不在此空转）
            return b"".join(outs), b"".join(errs), True
        if n_err < limit and chan.recv_stderr_ready():
            data = chan.recv_stderr(min(32768, limit - n_err))
            if data:
                errs.append(data)
                n_err += len(data)
                progressed = True
        elif n_err >= limit and chan.recv_stderr_ready():
            return b"".join(outs), b"".join(errs), True
        if progressed:
            continue
        if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
            break
        if time.monotonic() >= deadline:
            truncated = True
            break
        time.sleep(0.02)
    return b"".join(outs), b"".join(errs), truncated


def _exit_status(chan, deadline):
    """限时等待退出码；超时/不可用返回 -1（不无限阻塞）"""
    while not chan.exit_status_ready():
        if time.monotonic() >= deadline:
            return -1
        time.sleep(0.05)
    try:
        return chan.recv_exit_status()
    except Exception:  # noqa: BLE001
        return -1


def _connect_impl(tool_ctx, **kwargs):
    name = kwargs.get("name")
    conn = store.get_connection(name)
    if conn is None:
        # 允许运行时直接传连接参数
        conn = {k: kwargs.get(k) for k in ("name", "host", "port", "user", "auth_type", "key_path", "password", "key_passphrase", "host_key_policy", "timeout")}
        if not conn.get("host") or not conn.get("user"):
            return ToolResult(False, error=f"未找到连接 {name}，且未提供 host/user")
    try:
        client = auth.connect(conn)
    except Exception as e:
        return ToolResult(False, error=f"连接失败：{e}")
    handle = pool.put_connection(name, client)
    body = f"已连接 {name or conn.get('host')}，handle={handle}"
    # 首次连接：回显主机密钥指纹，让人有机会核对（TOFU 的可见面）
    new_keys = getattr(client, "_drifox_new_host_keys", None) or []
    if new_keys:
        fps = "，".join(f"{k['host']}={k['fingerprint']}" for k in new_keys)
        body += f"\n[首次连接，已记录主机密钥] {fps}"
    return ToolResult(True, content=body)


def _exec_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    client, err = pool.ensure_client(ref) if ref else (None, None)
    if client is None:
        return ToolResult(False, error=err or f"未找到活跃连接：{ref}（先 ssh_connect）")
    command = kwargs.get("command", "")
    timeout = int(kwargs.get("timeout", 30))
    deadline = time.monotonic() + max(1, timeout)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        chan = stdout.channel
        out_b, err_b, cut = _read_streams(chan, MAX_OUTPUT_BYTES, deadline)
        code = _exit_status(chan, deadline)
        if cut:
            # 远端可能仍在灌数据：关通道，避免 transport 窗口填满后永不退出
            try:
                chan.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:
        return ToolResult(False, error=f"执行失败：{e}")
    out = out_b.decode("utf-8", "replace")
    err = err_b.decode("utf-8", "replace")
    body = f"$ {command}\n{out}{err}\nexit={code}"
    if cut:
        body += f"\n[输出已截断：单路上限 {MAX_OUTPUT_BYTES // 1024}KB 或超时 {timeout}s]"
    if code == -1:
        body += f"\n[未取得退出码：超时 {timeout}s 或通道关闭]"
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
                "host_key_policy": {
                    "type": "string",
                    "description": "主机密钥策略：tofu（默认，首次记录后校验）/ strict（只认已登记）/ off（不校验，危险）",
                },
                "timeout": {"type": "integer", "description": "超时秒"},
            }, "required": []},
        }},
        impl=_connect_impl, danger="dangerous", icon="ssh_conn", cn_name="SSH 连接", group="SSH 远程",
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
        impl=_disconnect_impl, danger="safe", icon="ssh_conn", cn_name="SSH 断开", group="SSH 远程",
        description="关闭 SSH 连接/转发",
    )
