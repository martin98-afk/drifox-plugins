# -*- coding: utf-8 -*-
"""B站能力 MCP 服务器 — stdio 转发壳（browser 插件同款两段式）

工作流：
    AI → mcp__bili__* 工具 → 本服务器(stdio) → HTTP → 控制端点(宿主主进程)
    → vendor mcp_server 工具函数（deps/仲裁/凭证全在宿主进程内）

自引导：
    当前解释器缺 mcp/httpx 时，从 bridge.json 读宿主端点探测好的
    python 路径并 os.execv 重启自己（bridge.json 由插件 UI 加载时写入）。

工具表动态化：
    不静态声明工具；list_tools 从控制端点 /api/tools 实时拉取，
    上游 vendor 加减工具无需改本文件。
"""

import json
import os
import sys
import time
from pathlib import Path


# ── 自引导：确保 mcp/httpx 可用 ─────────────────────────

def _can_import(python: str) -> bool:
    import subprocess

    kwargs = {}
    if os.name == "nt":
        flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if flag:
            kwargs["creationflags"] = flag
    try:
        r = subprocess.run(
            [python, "-c", "import mcp, httpx"],
            capture_output=True,
            timeout=10,
            **kwargs,
        )
        return r.returncode == 0
    except Exception:
        return False


def _bootstrap():
    try:
        import mcp  # noqa: F401
        import httpx  # noqa: F401
        return
    except ImportError:
        pass

    candidates = []
    try:
        bridge = Path(__file__).resolve().parent / "bridge.json"
        if bridge.exists():
            py = json.loads(bridge.read_text(encoding="utf-8")).get("python_executable")
            if py:
                candidates.append(py)
    except Exception:
        pass
    import shutil

    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p:
            candidates.append(p)

    for py in candidates:
        try:
            if os.path.realpath(py) == os.path.realpath(sys.executable):
                continue
        except Exception:
            pass
        if _can_import(py):
            os.execv(py, [py] + sys.argv)
    sys.stderr.write(
        "[bili-mcp] 未找到能 import mcp/httpx 的 python 解释器。\n"
        "请确保系统 Python 可用并安装: pip install mcp httpx\n"
    )
    sys.exit(1)


_bootstrap()

import httpx  # noqa: E402
import mcp.types as types  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

_BRIDGE_PATH = Path(__file__).resolve().parent / "bridge.json"
_HTTP_TIMEOUT = 300.0  # 字幕批量爬取等长调用

server = Server("bili-scroll")


def _bridge() -> dict:
    return json.loads(_BRIDGE_PATH.read_text(encoding="utf-8"))


def _api(op: str, payload: dict = None, timeout: float = None) -> dict:
    """调用宿主进程控制端点"""
    bridge = _bridge()
    base = f"http://127.0.0.1:{bridge['port']}"
    body = {"token": bridge["token"]}
    if payload:
        body.update(payload)
    resp = httpx.post(f"{base}/api/{op}", json=body, timeout=timeout or _HTTP_TIMEOUT)
    return resp.json()


def _wait_bridge(timeout: float = 30.0) -> bool:
    """等待插件主进程写好 bridge.json 并可用（插件加载有先后时序）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _BRIDGE_PATH.exists():
            try:
                bridge = _bridge()
                st = httpx.get(f"http://127.0.0.1:{bridge['port']}/healthz", timeout=2)
                if st.status_code == 200:
                    return True
            except Exception:
                pass
        time.sleep(1)
    return False


@server.list_tools()
async def _list_tools() -> list[types.Tool]:
    data = _api("tools")
    if not data.get("ok"):
        raise RuntimeError(f"控制端点异常: {data.get('error', 'unknown')}")
    return [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"],
        )
        for t in data.get("tools", [])
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        data = _api("call", {"name": name, "kwargs": arguments or {}})
    except Exception as e:
        return [types.TextContent(type="text", text=f"控制端点不可达: {e}（插件可能未加载，稍后重试）")]
    if not data.get("ok"):
        return [types.TextContent(type="text", text=f"调用失败: {data.get('error', 'unknown')}")]
    return [types.TextContent(type="text", text=data.get("content", ""))]


def _endpoint_alive() -> bool:
    """bridge.json 存在且端点 healthz 可达。

    只查存在性不够：app 重启后残留的上次实例 bridge.json（端口/token 已失效）
    会让本壳提前握手，list_tools 连旧端口失败崩溃，客户端表现为
    "Expecting value: line 1 column 1"（stdio EOF）。
    """
    try:
        bridge = _bridge()
        st = httpx.get(f"http://127.0.0.1:{bridge['port']}/healthz", timeout=2)
        return st.status_code == 200
    except Exception:
        return False


async def _main():
    if not _endpoint_alive():
        # 不存在或已过期 → 轮询等端点启动/重启重写 bridge.json（每次循环重读端口）
        if not _wait_bridge():
            sys.stderr.write("[bili-mcp] bridge.json 未就绪（插件 UI 未加载？）\n")
            sys.exit(1)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import anyio

    anyio.run(_main)
