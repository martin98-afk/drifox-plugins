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
- session 级 $PSDefaultParameterValues['*:Encoding']='utf8'：Set-Content/Out-File
  等写入默认从 ANSI/UTF-16 变为 UTF-8，AI 生成的中文文件不再下游乱码。
  （PS 5.1 写 UTF-8 带 BOM，主流工具链均兼容；PS 7 无 BOM）

自包含：纯标准库实现（subprocess/base64），不依赖主程序 services。
"""
import base64
import re
import shutil
import subprocess
import sys
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


# 强制 UTF-8 输出，覆盖 PS 5.1 / PS 7 在 PIPE 场景的编码差异
# 关键：$OutputEncoding 是 PowerShell 重定向输出时使用的编码,
#       对 subprocess.PIPE 捕获的 stdout 是唯一可靠的开关(PS 5.1 仍部分依赖此开关)
#       [Console]::OutputEncoding 影响 .NET Console API
# $ProgressPreference 抑制进度活动:非交互 PIPE 主机可能把 Progress 流序列化为
# CLIXML 混入 stdout。注:CLIXML 主要由 Write-Host(Information 流)触发,而
# InformationPreference 在非交互主机下对 Write-Host 无效,故真正的去噪在 Python 侧
# _strip_clixml 兜底剥离(保留 Write-Host 文本,只剔 XML 元数据)。
#
# 错误处理策略(避免 native exe stderr 误判):
# - PS 7+ 调用 native exe 时,stderr 会被自动包装为 NativeCommandError 写入 error
#   流。原 Stop 偏好会把这种"仅仅是 stderr 输出"提升为 terminating error,导致
#   命令实际成功(exit 0)但脚本被终止、pwsh 进程退出码非零,被工具误判为失败。
# - 改用 Continue:cmdlet/native 错误仍写入 error 流(可见),但不终止脚本。
# - 加 $PSNativeCommandUseErrorActionPreference=$false(PS 7.4+):native 命令错误
#   记录不再触发 ErrorActionPreference,更精确地隔离"stderr 日志"与"真错误"。
#   PS 5.1 不支持此开关(静默忽略),不影响 5.1 行为。
_PS_ENCODING_PROLOGUE = (
    "$ErrorActionPreference='Continue';"
    "$PSNativeCommandUseErrorActionPreference=$false;"
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    "$OutputEncoding=[System.Text.Encoding]::UTF8;"
    "[Console]::InputEncoding=[System.Text.Encoding]::UTF8;"
    "$ProgressPreference='SilentlyContinue';"
    # 写入编码统一 UTF-8（无 BOM）：PS 5.1 的 Set-Content/Out-File 默认 ANSI/UTF-16，
    # AI 生成的中文文件下游（git/python/编辑器）读出乱码，是本工具最高频踩坑点。
    # 在 session 级把默认写入编码改为 UTF-8：PS 5.1 用 $PSDefaultParameterValues，
    # PS 7 本身默认即 UTF-8 无 BOM，设置无害。utf8NoBOM 仅 PS 7 支持（5.1 回退 utf8 带BOM？
    # 不：5.1 的 Set-Content -Encoding utf8 会写 BOM；改用 [IO.File]::WriteAllText
    # 会改变调用语义，这里接受 5.1 写 BOM（下游工具链均兼容），重点消灭 GBK）。
    "$PSDefaultParameterValues['*:Encoding']='utf8'"
)

# CLIXML 兜底：非交互主机序列化块的固定形态为 `#< CLIXML\n<Objs ...>...</Objs>`。
# 即使 prologue 已抑制两流,仍可能因子进程/特殊 cmdlet 残留,统一在此剥离。
_CLIXML_RE = re.compile(r"#< CLIXML[\s\S]*?</Objs>\s*", re.DOTALL)


def _strip_clixml(text: str) -> str:
    """剔除 PowerShell 非交互主机混入 stdout 的 CLIXML 元数据块(进度/信息流噪音)。"""
    if "#< CLIXML" not in text:
        return text
    return _CLIXML_RE.sub("", text).strip()


def _decode_output(raw: bytes) -> str:
    """智能解码 PowerShell 输出:先 BOM 嗅探,再严格 UTF-8,再 GBK,最后 UTF-8 replace。

    设计要点:
    1. BOM 优先:UTF-8/UTF-16 BOM 携带明确编码信息,跳过猜测。
    2. 严格 UTF-8:失败才认为不是 UTF-8,避免 GBK 字节被错误识别为合法 UTF-8。
    3. GBK 兜底:中文 Windows 外部 exe(git/findstr/xcopy 等)输出仍可能是 GBK。
    4. 不再用 latin-1 兜底:0x80+ 字节会产生"看似字符串但全是怪字符"的乱码,
       改用 UTF-8 errors='replace',保证任何字节流都能安全降级。
    """
    if not raw:
        return ""
    # 1. BOM 嗅探(明确无歧义,跳过猜测)
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    # 2. 严格 UTF-8
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # 3. GBK 兜底
    try:
        return raw.decode("gbk")
    except UnicodeDecodeError:
        pass
    # 4. 终极兜底:UTF-8 replace(不再用 latin-1,避免怪字符)
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

    # 静默执行:Windows 上 powershell.exe 是控制台程序,父进程无控制台时,
    # 系统会为其分配一个可见的黑框窗口。用 STARTUPINFO(wShowWindow=SW_HIDE)
    # 隐藏窗口,再用 CREATE_NO_WINDOW 创建无窗口子进程彻底消除黑框。
    # 二者都不影响 stdout/stderr 的 PIPE 捕获、退出码与超时逻辑。
    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, error=f"PowerShell 执行超时（>{timeout}s 已终止）")
    except FileNotFoundError:
        return ToolResult(False, error=f"未找到 PowerShell 可执行文件：{exe}")
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"执行失败：{e}")

    # 关键修复:合并 stdout/stderr 字节流后统一解码。
    # 原实现分别解码再拼接,会在 PS 5.1 下产生"半 GBK 半 UTF-8"编码错位,
    # 触发条件是 stderr(GBK)与 stdout(可能 UTF-8)同时存在时——典型"部分乱码"场景。
    stdout_raw = proc.stdout or b""
    stderr_raw = proc.stderr or b""
    merged_raw = stdout_raw
    if stderr_raw:
        if merged_raw and not merged_raw.endswith(b"\n"):
            merged_raw += b"\n"
        merged_raw += stderr_raw
    decoded = _strip_clixml(_decode_output(merged_raw))

    if proc.returncode != 0:
        return ToolResult(
            False,
            error=f"PowerShell 退出码 {proc.returncode}:\n{decoded or '(无输出)'}",
        )
    return ToolResult(
        True, content=decoded or "(命令执行成功，无输出)"
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
