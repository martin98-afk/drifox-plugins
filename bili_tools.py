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

# ── PIL 仲裁（ssh-toolkit _prefer_vendored_crypto 同款）──
# 打包版宿主的 FrozenImporter 会虚拟出一个残缺 PIL（_internal 无 _imaging.pyd），
# 且 meta_path 优先于 deps/ 的 sys.path 注入 ⇒ 必须用钩子把 PIL 指到 deps 版。
import importlib.machinery
import importlib.util

_PIL_SELFTEST_OK = False


def _vendored_pil_dir() -> Path | None:
    here = Path(__file__).resolve().parent.parent
    plat = "win32" if os.name == "nt" else sys.platform
    for sub in (plat, ""):
        d = here / "deps" / sub / "PIL"
        if (d / "__init__.py").is_file():
            return d
    return None


class _VendoredPilFinder:
    """meta_path 钩子：PIL* 一律指向插件 deps 目录，其余放行。"""

    def __init__(self, pkg_dir: str):
        hook = importlib.machinery.FileFinder.path_hook(
            (importlib.machinery.ExtensionFileLoader, importlib.machinery.EXTENSION_SUFFIXES),
            (importlib.machinery.SourceFileLoader, importlib.machinery.SOURCE_SUFFIXES),
            (importlib.machinery.SourcelessFileLoader, importlib.machinery.BYTECODE_SUFFIXES),
        )
        self._finder = hook(pkg_dir)

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PIL" or fullname.startswith("PIL."):
            return self._finder.find_spec(fullname, target)
        return None


def _pil_modules():
    return [k for k in sys.modules if k == "PIL" or k.startswith("PIL.")]


def _pil_selftest():
    from PIL import _imaging  # noqa: F401  残缺副本正是缺这个


def _prefer_vendored_pil():
    """宿主 PIL 缺 _imaging 时换成 deps 版（幂等，失败回滚宿主原状）。"""
    global _PIL_SELFTEST_OK
    if _PIL_SELFTEST_OK:
        return
    pkg_dir = _vendored_pil_dir()
    if not pkg_dir:
        return
    try:
        _pil_selftest()
        _PIL_SELFTEST_OK = True  # 宿主副本完好，不动
        return
    except Exception:
        pass
    saved = {k: sys.modules[k] for k in _pil_modules()}
    finder = _VendoredPilFinder(str(pkg_dir.parent))
    for k in saved:
        del sys.modules[k]
    sys.meta_path.insert(0, finder)
    try:
        importlib.import_module("PIL")
        mod = sys.modules.get("PIL")
        new_file = os.path.normcase(os.path.abspath(str(getattr(mod, "__file__", "") or "")))
        if not new_file.startswith(os.path.normcase(str(pkg_dir.parent))):
            raise RuntimeError(f"vendored PIL 未生效：{new_file}")
        _pil_selftest()
        _PIL_SELFTEST_OK = True  # 钩子常驻：后续 PIL.* 子模块 import 仍需绕开 FrozenImporter
        logger.info("[bili-scroll] 已仲裁 PIL → 插件 deps 版（宿主副本缺 _imaging）")
    except Exception as e:  # noqa: BLE001 - 任何失败都回滚到宿主现状
        logger.warning(f"[bili-scroll] vendored PIL 仲裁失败，回滚宿主原状: {e}")
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass
        for k in _pil_modules():
            sys.modules.pop(k, None)
        sys.modules.update(saved)


_prefer_vendored_pil()


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
