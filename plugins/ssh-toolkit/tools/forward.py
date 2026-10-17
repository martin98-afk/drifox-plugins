# ssh-toolkit/tools/forward.py
# -*- coding: utf-8 -*-
"""SSH 端口转发（local -L），后台线程运行。"""
import sys
import socket
import threading
from pathlib import Path

# PluginToolLoader 用 importlib 加载本模块，注入 tools/ 目录到 sys.path 以便绝对导入
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.result import ToolResult  # noqa: E402

import _pool as pool  # noqa: E402
import _guard as guard  # noqa: E402

FORWARDS = {}  # forward_id -> {"thread", "stop"}


def _pipe(src, dst):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        for s in (src, dst):
            try:
                s.close()
            except Exception:
                pass


def _forward_loop(ref, client, bind_addr, bind_port, remote_addr, remote_port, stop, ready=None, errbox=None):
    try:
        transport = client.get_transport()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_addr, bind_port))
        sock.listen(5)
    except Exception as e:  # noqa: BLE001 - 绑定失败必须回报给调用方
        if errbox is not None:
            errbox["error"] = f"{type(e).__name__}: {e}"
        if ready is not None:
            ready.set()
        return
    if errbox is not None:
        try:
            errbox["port"] = sock.getsockname()[1]
        except Exception:  # noqa: BLE001
            errbox["port"] = bind_port
    if ready is not None:
        ready.set()
    while not stop.is_set():
        try:
            conn, _ = sock.accept()
        except OSError:
            break
        try:
            ch = transport.open_channel("direct-tcpip", (remote_addr, remote_port), ("127.0.0.1", 0))
        except Exception:
            conn.close()
            continue
        threading.Thread(target=_pipe, args=(conn, ch), daemon=True).start()
    try:
        sock.close()
    except Exception:
        pass


def _forward_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    ftype = kwargs.get("type", "local")
    bind_addr = kwargs.get("bind_addr", "127.0.0.1")
    bind_port = int(kwargs.get("bind_port", 0))
    remote_addr = kwargs.get("remote_addr", "127.0.0.1")
    remote_port = int(kwargs.get("remote_port", 0))
    # 绑定地址边界：0.0.0.0 / :: 会把内网服务一键暴露给局域网，需显式开启
    ok, reason = guard.check_bind_addr(bind_addr, bool(kwargs.get("allow_public", False)))
    if not ok:
        return ToolResult(False, error=reason)
    if ftype not in ("local",):
        return ToolResult(False, error=f"不支持的转发类型：{ftype}（当前仅实现 local -L）")
    client, err = pool.ensure_client(ref) if ref else (None, None)
    if client is None:
        return ToolResult(False, error=err or f"未找到活跃连接：{ref}")
    stop = threading.Event()
    ready = threading.Event()
    errbox = {}
    t = threading.Thread(
        target=_forward_loop,
        args=(ref, client, bind_addr, bind_port, remote_addr, remote_port, stop, ready, errbox),
        daemon=True,
    )
    t.start()
    # 等监听就绪：bind_port=0 时真实端口只有线程里知道，返回占位值会误导调用方
    ready.wait(5.0)
    if errbox.get("error"):
        return ToolResult(False, error=f"转发启动失败：{errbox['error']}")
    real_port = errbox.get("port", bind_port)
    fid = f"fw:{ref}:{real_port}"
    FORWARDS[fid] = {"thread": t, "stop": stop}
    return ToolResult(True, content=f"已启动{ftype}转发 {fid}: {bind_addr}:{real_port} → {remote_addr}:{remote_port}")


def register(registry):
    registry.register(
        "ssh_forward",
        {"type": "function", "function": {
            "name": "ssh_forward",
            "description": "建立 SSH 端口转发（当前仅 local -L），后台运行",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "type": {"type": "string", "description": "local（当前仅支持 local -L）"},
                "bind_addr": {"type": "string", "description": "本地绑定地址，默认 127.0.0.1；其它地址需 allow_public=true"},
                "bind_port": {"type": "integer", "description": "本地绑定端口"},
                "remote_addr": {"type": "string", "description": "远端目标地址"},
                "remote_port": {"type": "integer", "description": "远端目标端口"},
                "allow_public": {"type": "boolean", "description": "允许绑定非回环地址（对外暴露端口，默认 false）"},
            }, "required": ["bind_port", "remote_port"]},
        }},
        impl=_forward_impl, danger="dangerous", icon="ssh", cn_name="SSH 端口转发", group="SSH 远程",
        description="SSH 端口转发",
    )
