# -*- coding: utf-8 -*-
"""
专用 Windows PowerShell 执行工具（win-powershell 插件）

与内置 bash 工具的区别：
- bash 在 Windows 底层也调 PowerShell，但它执行的是「通用 shell 字符串」
  （cmd/PowerShell 混用、含安全分类、findstr 修复等）。
- 本工具**强制**走 PowerShell 原生入口：
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand <b64>
  面向 PS 原生用法：cmdlet、管道对象、ConvertTo-Json/-Xml、脚本块。

编码方案（关键）：
- 用 -EncodedCommand（UTF-16LE base64）传脚本，彻底规避 Windows 命令行
  非 ASCII 字符被破坏的问题（直接 -Command "中文" 会乱码）。
- 脚本开头强制 [Console]::OutputEncoding = UTF-8，使 stdout 可靠为 UTF-8，
  解码时再兜底 gbk/latin-1（兼容外部 exe 的 GBK 输出）。

自包含：纯标准库实现（subprocess/base64），不依赖主程序 services。
"""
import base64
import shutil
import subprocess
from html import escape

from app.tools.registry import make_summarize_from_preview
from app.tools.result import ToolResult


# ── PowerShell 解释器自动检测（优先 PowerShell 7 pwsh，回退 Windows PowerShell 5.1）──
def _detect_powershell() -> str:
    """返回可用的 PowerShell 可执行文件名。

    Windows 必定有 powershell.exe（5.1，系统自带）。
    若装了 PowerShell 7（pwsh.exe，UTF-8/跨平台更好）则优先用。
    """
    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            return exe
    return "powershell"  # 兜底（Windows 上几乎一定存在）


# 强制 UTF-8 输出，避免控制台 OEM 编码（如中文 Windows 的 GBK）截断
_PS_ENCODING_PROLOGUE = (
    "$ErrorActionPreference='Stop';"
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    "$OutputEncoding=[System.Text.Encoding]::UTF8"
)


def _decode_output(raw: bytes) -> str:
    """智能解码 PowerShell 输出：优先 UTF-8，兜底 GBK（cp936）、latin-1。"""
    if not raw:
        return ""
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _powershell_impl(tool_ctx, **kwargs):
    """运行 PowerShell 脚本。

    参数:
        script:  要执行的 PowerShell 脚本/命令/脚本块（必填）
        cwd:     工作目录（可选，默认当前项目目录）
        timeout: 超时秒数（可选，默认 120，范围 1-3600）
    """
    script = kwargs.get("script")
    if not script or not str(script).strip():
        return ToolResult(False, error="script 不能为空")

    cwd = kwargs.get("cwd") or tool_ctx.get("workdir")
    if cwd is not None:
        cwd = str(cwd)
    timeout = int(kwargs.get("timeout") or 120)
    timeout = max(1, min(timeout, 3600))  # 防御：1s ~ 1h

    exe = _detect_powershell()
    full_script = f"{_PS_ENCODING_PROLOGUE}\n{script}"
    encoded = base64.b64encode(full_script.encode("utf-16-le")).decode("ascii")
    cmd = [
        exe,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded,
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, error=f"PowerShell 执行超时（>{timeout}s 已终止）")
    except FileNotFoundError:
        return ToolResult(False, error=f"未找到 PowerShell 可执行文件：{exe}")
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"执行失败：{e}")

    stdout = _decode_output(proc.stdout or b"")
    stderr = _decode_output(proc.stderr or b"")
    combined = "\n".join(filter(None, [stdout.strip(), stderr.strip()]))

    if proc.returncode != 0:
        detail = combined if combined else "(无输出)"
        return ToolResult(
            False,
            error=f"PowerShell 退出码 {proc.returncode}:\n{detail}",
        )
    return ToolResult(
        True, content=combined if combined else "(命令执行成功，无输出)"
    )


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "powershell",
        "description": (
            "专用 Windows PowerShell 执行工具。强制走 PowerShell 原生入口运行 PS "
            "脚本/命令（支持 cmdlet、管道对象、ConvertTo-Json/-Xml、脚本块），区别于"
            "通用 bash 工具。自动处理 UTF-8 编码与超时。慎用：可执行任意命令。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "要执行的 PowerShell 脚本/命令/脚本块",
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录（可选，默认当前项目目录）",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（可选，默认 120，范围 1-3600）",
                },
            },
            "required": ["script"],
        },
    },
}


def _preview(args: dict) -> str:
    script = (args or {}).get("script", "")
    first_line = (
        str(script).strip().splitlines()[0] if str(script).strip() else ""
    )
    return f"PowerShell: {escape(first_line)[:60]}"


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "powershell",
        _SCHEMA,
        impl=_powershell_impl,
        danger="dangerous",
        icon="powershell",
        cn_name="PowerShell 执行",
        group="PowerShell",
        description="运行 Windows PowerShell 脚本/命令",
        aliases=["PowerShell", "ps", "pwsh"],
        render_mode="",  # 默认折叠卡：长输出可折叠
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
        metadata={"permission_arg": "script"},
    )
