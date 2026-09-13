# -*- coding: utf-8 -*-
"""win-powershell 插件超时杀树回归测试。

死锁背景（2026-09-13 实录）：subprocess.run 超时分支在 Windows 上是 kill
直接子进程后再次 communicate() 等管道 EOF；PowerShell 启动 native exe 时
句柄继承泄漏，孙进程持有 stdout 管道写端，若孙进程安静不退出（起 UI/长任务
不写输出），EOF 永不到达 → 工具线程永久死锁、AI 端转圈不返回。
修复：Popen + communicate(timeout) + 超时 taskkill /T /F 杀整棵进程树。

测试通过 stub 主程序 app.* 命名空间直接加载插件模块（与 conftest.py 的
importlib 从文件路径加载方式一致）。
"""

import importlib.util
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest

# ---- stub 主程序依赖（插件在主程序外无法 import app.*）----
_app_pkg = types.ModuleType("app")
_tools_pkg = types.ModuleType("app.tools")
_registry_mod = types.ModuleType("app.tools.registry")
_registry_mod.make_summarize_from_preview = lambda fn: None
_result_mod = types.ModuleType("app.tools.result")


class _ToolResult:
    def __init__(self, success, content=None, error=None, **kw):
        self.success = success
        self.content = content
        self.error = error


_result_mod.ToolResult = _ToolResult
sys.modules.setdefault("app", _app_pkg)
sys.modules.setdefault("app.tools", _tools_pkg)
sys.modules.setdefault("app.tools.registry", _registry_mod)
sys.modules.setdefault("app.tools.result", _result_mod)

_TOOL_PATH = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "win-powershell" / "tools" / "powershell.py"
)
_spec = importlib.util.spec_from_file_location("win_powershell_tool", _TOOL_PATH)
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 专用插件")

# 唯一 sleep 秒数，避免与机器上其他进程串扰
_HANG_SLEEP = "1237"
_HANG_MARKER = f"time.sleep({_HANG_SLEEP})"
CTX = {"workdir": None}


def _leftover_children() -> int:
    """统计当前残留的挂住子进程数（按唯一 sleep 正则匹配命令行）。

    排除查询进程自身（其命令行含匹配模式文本）；
    正则带 time.sleep 前缀避免撞上其他进程命令行里的随机数字。
    """
    pattern = f"time\\.sleep\\({_HANG_SLEEP}\\)"
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID "
         f"-and $_.CommandLine -match '{pattern}' }} | Measure-Object).Count"],
        capture_output=True, text=True, timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        return int(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return -1


def test_normal_command_and_chinese_utf8():
    r = ps._powershell_impl(CTX, command="Write-Output '你好-ps'; exit 0", timeout=60)
    assert r.success, r.error
    assert "你好-ps" in (r.content or "")


def test_nonzero_exit_code_reports_error():
    r = ps._powershell_impl(
        CTX, command="exit 7", timeout=60
    )
    assert not r.success
    assert "7" in (r.error or "")


def test_quiet_child_timeout_returns_and_kills_tree():
    """安静长寿子进程超时：必须返回错误且进程树无残留（修复前永久死锁）。"""
    command = f'& "{sys.executable}" -c "import time; {_HANG_MARKER}"'
    result_box = {}

    def runner():
        t0 = time.time()
        result_box["r"] = ps._powershell_impl(CTX, command=command, timeout=5)
        result_box["dt"] = time.time() - t0

    th = threading.Thread(target=runner, daemon=True)
    th.start()
    th.join(timeout=30)
    # 死锁形态：30s（timeout 5s 的 6 倍）后仍未返回
    assert not th.is_alive(), "powershell 工具线程在超时后 30s 内未返回（死锁回归）"
    assert not result_box["r"].success
    assert "超时" in (result_box["r"].error or "")
    assert result_box["dt"] < 25, f"超时返回耗时异常：{result_box['dt']:.1f}s"
    # 杀树后不留孤儿
    assert _leftover_children() == 0, "超时杀树后仍残留挂住子进程"
