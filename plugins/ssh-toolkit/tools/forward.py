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


def _forward_loop(fid, client, bind_addr, bind_port, remote_addr, remote_port, stop):
    transport = client.get_transport()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_addr, bind_port))
    sock.listen(5)
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
    client, err = pool.ensure_client(ref) if ref else (None, None)
    if client is None:
        return ToolResult(False, error=err or f"未找到活跃连接：{ref}")
    fid = f"fw:{ref}:{bind_port}"
    stop = threading.Event()
    t = threading.Thread(target=_forward_loop, args=(fid, client, bind_addr, bind_port, remote_addr, remote_port, stop), daemon=True)
    t.start()
    FORWARDS[fid] = {"thread": t, "stop": stop}
    return ToolResult(True, content=f"已启动{ftype}转发 {fid}: {bind_addr}:{bind_port} → {remote_addr}:{remote_port}")


def register(registry):
    registry.register(
        "ssh_forward",
        {"type": "function", "function": {
            "name": "ssh_forward",
            "description": "建立 SSH 端口转发（local/remote），后台运行",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "type": {"type": "string", "description": "local 或 remote"},
                "bind_addr": {"type": "string", "description": "本地绑定地址"},
                "bind_port": {"type": "integer", "description": "本地绑定端口"},
                "remote_addr": {"type": "string", "description": "远端目标地址"},
                "remote_port": {"type": "integer", "description": "远端目标端口"},
            }, "required": ["bind_port", "remote_port"]},
        }},
        impl=_forward_impl, danger="dangerous", icon="ssh", cn_name="SSH 端口转发", group="SSH 远程",
        description="SSH 端口转发",
    )
