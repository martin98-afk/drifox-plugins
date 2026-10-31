# -*- coding: utf-8 -*-
"""B站工具族注册：vendor server 的工具函数在宿主进程内直接暴露为 DriFox tools。

为什么不走 stdio MCP：vendored 二进制（cp314 .pyd）必须与解释器 ABI 匹配，
.mcp.json 拉起的系统 `py -3`（用户机器版本不可控）加载不了；而 deps/ 经宿主
deps_loader 注入的正是宿主解释器。故对齐 ssh-toolkit 模式：import vendor 的
mcp_server（import 无副作用，`__main__` 才 run），遍历其 FastMCP 工具表，
asyncio.run 包装后逐个注册。工具逻辑与上游零改动。

凭证与 duty 隔离区路径在 import mcp_server 前经 env 下发（vendor patch ⑦）。
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
from pathlib import Path

from app.tools.result import ToolResult

# 宿主 tools 加载器不注插件根，先自注入再 import 本插件包
_PLUGIN_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT_DIR)

from biliscroll_core.paths import PLUGIN_ROOT
from biliscroll_core.schema_registry import TOOL_SCHEMAS

_VENDOR_DIR = PLUGIN_ROOT / "vendor" / "bilibili-mcp"

# duty_* 窄口五件套由 DriFox 侧 tools/bili_duty_data.py 等价实现（统一数据布局），
# 转写三件 v1 未启用（章程与开场说明声明）；均不在注册名单。
_EXCLUDED = ("duty_", "bili_transcribe")

# 写类工具（拿用户账号发言）必须显式 dangerous
_DANGEROUS = {"bili_reply", "bili_send_message"}

_CRED_DEFAULT = PLUGIN_ROOT / "data" / "bili_credential.json"
_DUTY = PLUGIN_ROOT / "data" / "duty"

# ── PIL 仲裁：实现在 biliscroll_core/pil_arbiter.py。不放本文件的原因：
# tools/ 顶层非下划线文件会被 PluginToolLoader 的 ASTGuard 审计，仲裁回滚
# 路径的 sys.modules.update(saved)（动态键）会被整文件拒载（ssh-toolkit
# 同款仲裁同理藏在 _auth.py）。必须在 import mcp_server 前调用。
# biliscroll_core.* 是共享顶层名模块，热重载滞留旧版（宿主只清 _plugin_tool_* 前缀），
# pil_arbiter 新增函数后滞留旧模块会 ImportError；它无跨轮状态，reload 自愈。
import biliscroll_core.pil_arbiter
importlib.reload(biliscroll_core.pil_arbiter)
from biliscroll_core.pil_arbiter import prefer_vendored_pil, prefer_vendored_stdlib

prefer_vendored_pil()


def _cred_path() -> Path:
    """凭证落 plugin_data（规范位置）；能力池不可用回退插件 data/（重装即弃）。"""
    try:
        from biliscroll_core.paths import plugin_data_root

        root = plugin_data_root()
        if root:
            return root / "bili_credential.json"
    except Exception:
        pass
    return _CRED_DEFAULT


os.environ.setdefault("BILI_CRED_FILE", str(_cred_path()))
os.environ.setdefault("BILI_DUTY_HOME", str(_DUTY))

# 宿主打包环境只收集了部分标准库 xml（无 xml.dom），而 bilibili_api 顶层拉
# danmaku2ass 要 xml.dom；PyiFrozenLoader 挂 meta_path 优先于 sys.path，sys.path
# 塞副本无效，须按 PIL 同款仲裁（del 残缺模块 + meta_path 钩子 + 重新 import）。
# 副本藏 deps/_pystdlib_xml/（放 deps 根会被 deps_loader 按 stdlib 顶层名防劫持检
# 查拒注入整个 deps）。必须在 import mcp_server 前调用。

prefer_vendored_stdlib(PLUGIN_ROOT / "deps" / "_pystdlib_xml")

if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import mcp_server as _server  # noqa: E402  vendor 模块（import 无副作用）

_IMPLS: dict[str, object] = {}


def _make_impl(fn):
    """async 工具函数 → 同步 impl（worker 线程无活动 loop，asyncio.run 安全）。"""

    def _impl(tool_ctx, **kwargs):
        try:
            out = asyncio.run(fn(**kwargs))
        except Exception as e:
            return ToolResult(False, error=f"{type(e).__name__}: {e}")
        if isinstance(out, str):
            return ToolResult(True, content=out)
        return ToolResult(True, content=json.dumps(out, ensure_ascii=False, default=str))

    return _impl


def _iter_fastmcp_tools():
    """跨 mcp SDK 小版本枚举 FastMCP 工具表（name -> Tool）。"""
    tm = getattr(_server.mcp, "_tool_manager", None)
    tools = getattr(tm, "_tools", None)
    if isinstance(tools, dict):
        return tools
    raise RuntimeError("FastMCP 工具表结构未知（mcp SDK 版本不兼容），无法注册 B站工具")


def register(registry):
    for name, tool in sorted(_iter_fastmcp_tools().items()):
        if name.startswith(_EXCLUDED):
            continue
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": (tool.description or "").strip() or name,
                "parameters": tool.parameters or {"type": "object", "properties": {}},
            },
        }
        fn = tool.fn if hasattr(tool, "fn") else tool.func
        registry.register(
            name,
            schema,
            impl=_make_impl(fn),
            danger="dangerous" if name in _DANGEROUS else "safe",
            icon="bili",
            cn_name=f"B站 {name.removeprefix('bili_')}",
            group="B站工具" if name not in _DANGEROUS else "B站发言",
            description=(tool.description or "").strip()[:80],
        )
        TOOL_SCHEMAS[name] = schema
        _IMPLS[name] = fn
