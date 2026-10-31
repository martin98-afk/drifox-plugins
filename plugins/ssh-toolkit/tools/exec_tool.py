# ssh-toolkit/tools/exec_tool.py
# -*- coding: utf-8 -*-
"""SSH 连接 / 命令执行 / 断开（dangerous 除断开外）。"""
import sys
import time
from pathlib import Path

from loguru import logger

# PluginToolLoader 用 importlib 加载本模块，注入 tools/ 目录到 sys.path 以便绝对导入
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.result import ToolResult  # noqa: E402

import _store as store  # noqa: E402
import _args as args  # noqa: E402
import _auth as auth  # noqa: E402
import _pool as pool  # noqa: E402

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


def _store_api():
    """取 _store 模块并保证是最新实现（热重载自愈）。

    宿主热重载只清 ``_plugin_tool_<plugin>_*`` 前缀的模块，tools 之间共享的
    顶层名模块（_store/_pool/_args）会滞留在 sys.modules；新版工具调用新增
    函数时报 "module '_store' has no attribute 'upsert_connection'"。
    按文件重载一次即可拿到当前实现（_store 无运行态，重载无副作用）。
    """
    if hasattr(store, "upsert_connection"):
        return store
    import importlib

    try:
        return importlib.reload(store)
    except Exception as e:  # noqa: BLE001 — 重载失败按旧接口降级，不阻断连接
        logger.warning(f"[ssh-toolkit] 重载 _store 失败: {e}")
        return store


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

    # 连过一次就落库（用户口径：不再要求先 ssh_add_connection）：
    # 直连参数按默认命名存入，已有同名连接则刷新最后连接时间与次数。
    saved_note = ""
    saved_name = name or ""
    try:
        record = {
            "host": conn.get("host"),
            "user": conn.get("user"),
            "port": args.to_int(conn.get("port"), 22),
            "auth_type": conn.get("auth_type") or "publickey",
            "key_path": conn.get("key_path") or "~/.ssh/id_rsa",
            "password": conn.get("password") or "",
            "key_passphrase": conn.get("key_passphrase") or "",
            "host_key_policy": conn.get("host_key_policy") or "tofu",
            "timeout": args.to_int(conn.get("timeout"), 10),
            "note": conn.get("note") or "",
        }
        if name:
            record["name"] = name
        api = _store_api()
        upsert = getattr(api, "upsert_connection", None)
        if upsert is None:
            raise RuntimeError("_store 模块版本过旧，重启宿主后生效")
        saved_name, created = upsert(record)
        saved_note = f"\n[已{'记录' if created else '更新'}连接] {saved_name}（设置 → SSH 远程连接 可查看/删除）"
    except Exception as e:  # noqa: BLE001 — 落库失败不影响本次连接
        logger.warning(f"[ssh-toolkit] 连接配置落库失败: {e}")
        saved_note = f"\n[连接配置未保存] {e}"

    # handle 用落库后的名字：直连（未命名）也能拿到可读可复用的 handle
    handle = pool.put_connection(saved_name or name, client)
    body = f"已连接 {saved_name or name or conn.get('host')}，handle={handle}" + saved_note
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
    timeout = args.to_int(kwargs.get("timeout"), 30)
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
            "description": "建立 SSH 连接并加入连接池，返回 handle（供 ssh_exec 等复用）。连接成功会自动保存到本地，无需预先保存配置",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "已保存连接名；不传名字时用 host/user 直连，成功后按 user@host 自动命名保存"},
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
            "description": (
                "在已连接主机上执行命令，返回 stdout/stderr/exit code。"
                "阻塞到进程退出，超时即强制关通道，长任务会随通道一起死。"
                "跑长任务/后台任务用 tmux 分离会话（禁 tmux attach，永不返回）："
                "建/复用 tmux has-session -t S 2>/dev/null || tmux new-session -d -s S -c DIR；"
                "投喂 tmux send-keys -t S 'cmd; echo __RC=$?' Enter；"
                "取输出 tmux capture-pane -pt S -S -300 后找 __RC=；"
                "探活 tmux list-panes -t S -F '#{pane_dead}'。"
                "exec_command 走非 login shell，PATH 不全时用 bash -lc 包一层。"
            ),
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
