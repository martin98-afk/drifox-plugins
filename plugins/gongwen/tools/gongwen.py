# -*- coding: utf-8 -*-
"""公文工具 — 把 gongwen-skill 的 Python CLI 暴露为模型工具（单入口 + command 分发）。

上游 gongwen-skill 的 dsh host 端只做一件事：`spawn("python", ["-m", "gongwen", ...])`。
本文件等价复刻该路径，引擎本体原样放在 skills/gongwen/ 下，不重写任何格式逻辑。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from app.tools.result import ToolResult

# 引擎根目录：<plugin>/skills/gongwen（gongwen 包、rules、prompts 都在它下面）
_PKG_ROOT = Path(__file__).resolve().parent.parent / "skills" / "gongwen"

# 直接作为 CLI flag 透传的简单参数
_FLAG_ARGS = {
    "input": None,          # 位置参数，单独处理
    "output": "--output",
    "doc_type": "--doc-type",
    "template": "--template",
    "style": "--style",
    "mode": "--mode",
    "changes": "--changes",
    "apply": "--apply",
    "json": "--json",
}

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "gongwen",
        "description": (
            "中文公文全流程处理（GB/T 9704 国家标准）。通过 command 切换能力：\n"
            "  - check: 格式检查（只读），列出字号/字体/行距/页边距等问题\n"
            "  - optimize: 按标准自动修复格式，输出修复后的 docx\n"
            "  - optimize-content: 内容修订，产出差分对比版（红色标注 + 删除线 + 修改说明）\n"
            "  - md2docx: Markdown 转公文格式 docx\n"
            "  - template: 生成公文模板（版头/版记/页码注入）\n"
            "  - style-learn: 从标准文档学习排版样式，生成自定义模板\n"
            "  - list-types: 列出支持的公文类型（通知/请示/报告/函/纪要等 25 类）\n"
            "  - doctor: 环境与依赖全面诊断\n"
            "  - handoff: 长任务会话交接（--list / --latest）\n"
            "\n"
            "典型用法：\n"
            "  gongwen(command='list-types')\n"
            "  gongwen(command='check', input='/path/通知.docx', doc_type='notice')\n"
            "  gongwen(command='optimize', input='/path/通知.docx', output='/path/修复.docx')\n"
            "  gongwen(command='optimize-content', input='/path/稿.docx', changes='/path/changes.json', apply=True, mode='tracked')\n"
            "\n"
            "拿不准参数时先用 doctor 或 list-types，不要猜。其余 CLI 参数可用 extra 传 JSON 对象透传。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令名：check / optimize / optimize-content / md2docx / template / style-learn / list-types / doctor / handoff / wizard",
                },
                "input": {"type": "string", "description": "输入文件路径（多数命令的位置参数）"},
                "output": {"type": "string", "description": "输出文件路径（--output）"},
                "doc_type": {
                    "type": "string",
                    "description": "公文类型（--doc-type）：notice / request / report / letter / meeting 等，用 list-types 查全部",
                },
                "template": {"type": "string", "description": "样式模板名（--template，style-learn 学到的命名模板）"},
                "style": {"type": "string", "description": "内容优化风格（--style），如 庄重严谨"},
                "mode": {"type": "string", "description": "修订模式（--mode），如 tracked"},
                "changes": {"type": "string", "description": "内容变更 JSON 文件路径（--changes）"},
                "apply": {"type": "boolean", "description": "直接应用、跳过交互确认（--apply）"},
                "json": {"type": "boolean", "description": "输出 JSON（--json）"},
                "extra": {
                    "type": "string",
                    "description": (
                        "其余 CLI 参数透传，JSON 对象字符串，键为参数名（不含 -- 前缀）。"
                        '例如 {"doc-type":"notice","style":"庄重严谨"}'
                    ),
                },
            },
            "required": ["command"],
        },
    },
}


def _build_argv(kwargs):
    """把工具参数翻译成 gongwen CLI 参数列表（与上游 toolArgsToCli 同语义）"""
    argv = []
    if kwargs.get("input"):
        argv.append(str(kwargs["input"]))
    for key, flag in _FLAG_ARGS.items():
        if key == "input" or flag is None:
            continue
        val = kwargs.get(key)
        if val is None or val == "":
            continue
        if isinstance(val, bool):
            if val:
                argv.append(flag)
            continue
        argv.extend([flag, str(val)])

    raw_extra = kwargs.get("extra")
    if raw_extra:
        try:
            extra = json.loads(raw_extra) if isinstance(raw_extra, str) else dict(raw_extra)
        except (TypeError, ValueError):
            return None, f"extra 不是合法 JSON 对象：{raw_extra!r}"
        for key, val in extra.items():
            flag = key if key.startswith("-") else f"--{key}"
            if isinstance(val, bool):
                if val:
                    argv.append(flag)
            elif val is not None:
                argv.extend([flag, str(val)])
    return argv, None


def _gongwen_impl(tool_ctx, **kwargs):
    command = (kwargs.get("command") or "").strip()
    if not command:
        return ToolResult(False, error="缺少必填参数 command，可用 gongwen(command='list-types') 先看支持的公文类型")

    if not (_PKG_ROOT / "gongwen").is_dir():
        return ToolResult(False, error=f"插件引擎缺失：{_PKG_ROOT / 'gongwen'} 不存在，插件可能安装不完整")

    argv, err = _build_argv(kwargs)
    if err:
        return ToolResult(False, error=err)

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_PKG_ROOT), env.get("PYTHONPATH")]))
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    workdir = (tool_ctx or {}).get("workdir") or str(_PKG_ROOT)
    cmd = [sys.executable, "-m", "gongwen", command, *argv]

    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, error=f"gongwen {command} 超过 600 秒未结束，已中止。可先用 check 缩小范围")
    except OSError as exc:
        return ToolResult(False, error=f"无法启动 gongwen 进程：{exc}")

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if proc.returncode != 0:
        detail = stderr or stdout or f"退出码 {proc.returncode}"
        return ToolResult(False, error=f"gongwen {command} 执行失败：\n{detail[:4000]}")

    if stdout[:1] in "{[":
        try:
            return ToolResult(True, content=json.dumps(json.loads(stdout), ensure_ascii=False, indent=2))
        except ValueError:
            pass

    content = stdout or "（命令执行成功，无输出）"
    if stderr:
        content = f"{content}\n\n[stderr]\n{stderr[:2000]}"
    return ToolResult(True, content=content)


def register(registry):
    """工具插件化注册入口：gongwen（单入口 + command 分发）"""
    registry.register(
        "gongwen",
        _SCHEMA,
        impl=_gongwen_impl,
        danger="dangerous",
        icon="FileText",
        cn_name="公文处理",
        group="文档处理",
        description="中文公文 GB/T 9704 格式检查/修复/内容修订/模板生成",
        aliases=["gongwen_skill", "公文"],
    )
