# -*- coding: utf-8 -*-
"""archify — DriFox 适配插件工具。

封装 tt-a1i/archify（MIT, v2.16）Node 运行时，把代码库 / 系统描述 /
纯语言需求 / Mermaid 转成自包含交互式架构图 HTML
（architecture / workflow / sequence / dataflow / lifecycle）。

内部调用 vendored 运行时：plugins/archify/archify_runtime/bin/archify.mjs
无需 npm 依赖（渲染器为纯 Node 标准库），本机 Node >=18 即可。
"""
from __future__ import annotations

import json
import os
import sys
import shutil
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

from app.tools.registry import make_summarize_from_preview
from app.tools.result import ToolResult

_RUNTIME = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "archify_runtime"))
_OUTPUT_DIR = os.path.join(_RUNTIME, "output")
_ARCHIFY_CLI = os.path.join(_RUNTIME, "bin", "archify.mjs")
_TYPES = ["architecture", "workflow", "sequence", "dataflow", "lifecycle"]
_NODE = shutil.which("node") or "node"


# ── 辅助 ─────────────────────────────────────────────────────────────────────
def _ensure_output_dir() -> str:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return _OUTPUT_DIR


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_input_json(input_json, out_dir: str) -> str:
    """LLM 传入的 JSON 字符串 / dict / list → 临时 .json 文件，返回路径。"""
    if isinstance(input_json, (dict, list)):
        data = input_json
    else:
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"input_json 不是合法 JSON：{e}") from e
    path = os.path.join(out_dir, f"candidate_{_now()}_{os.getpid()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _resolve_input(kw: dict, out_dir: str) -> str:
    input_path = kw.get("input_path")
    if input_path:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"input_path 不存在：{input_path}")
        return input_path
    input_json = kw.get("input_json")
    if input_json is None:
        raise ValueError("必须提供 input_json（JSON 字符串）或 input_path（文件路径）")
    return _write_input_json(input_json, out_dir)


def _run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    # Windows 默认 locale 编码为 gbk，archify 输出含 UTF-8 中文会解码失败，
    # 强制 utf-8 解码并 replace 兜底。
    return subprocess.run(
        [_NODE, _ARCHIFY_CLI, *args],
        cwd=_RUNTIME, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def _err(proc: subprocess.CompletedProcess) -> str:
    head = "\n".join((proc.stdout or "").splitlines()[:60])
    tail = "\n".join((proc.stderr or "").splitlines()[-40:])
    return f"archify 退出码 {proc.returncode}\n--- stdout ---\n{head}\n--- stderr ---\n{tail}"


def _open(path: str) -> None:
    # 用独立进程打开文件：tool 可能在子线程执行，webbrowser/os.startfile 依赖调用线程 COM 公寓易失败
    try:
        p = os.path.abspath(path)
        if sys.platform == "win32":
            subprocess.run(f'cmd /c start "" "{p}"', shell=True, check=False, timeout=30)
        elif sys.platform == "darwin":
            subprocess.run(["open", p], check=False, timeout=30)
        else:
            subprocess.run(["xdg-open", p], check=False, timeout=30)
    except Exception:
        pass


def _fmt_html_result(output_path: str, stdout: str, warn: str = "") -> str:
    size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    lines = [l for l in (stdout or "").splitlines() if l.strip()]
    summary = "\n".join(lines[:6])
    msg = [
        f"架构图 HTML 已生成：{output_path}",
        f"文件大小：{size} 字节",
    ]
    if warn:
        msg.append(f"⚠️ {warn}")
    if summary:
        msg.append(f"--- archify 输出 ---\n{summary}")
    msg.append(
        "提示：用浏览器打开该路径查看交互式架构图（主题切换/缩放/关系追踪/"
        "导出 PNG/SVG/WebP/WebM）。"
    )
    return "\n".join(msg)


# ── 各 action 实现 ────────────────────────────────────────────────────────────
def _action_render(kw: dict) -> ToolResult:
    diagram_type = (kw.get("diagram_type") or "").strip().lower()
    if diagram_type not in _TYPES:
        return ToolResult(False, error=f"diagram_type 必须是 {_TYPES} 之一，收到 {diagram_type!r}")
    quality = (kw.get("quality") or "showcase").strip().lower()
    if quality not in ("showcase", "standard"):
        quality = "showcase"
    repo_root = kw.get("repo_root")
    open_browser = bool(kw.get("open"))
    out_dir = _ensure_output_dir()
    try:
        in_file = _resolve_input(kw, out_dir)
    except (ValueError, FileNotFoundError) as e:
        return ToolResult(False, error=str(e))
    output_path = kw.get("output_path") or os.path.join(out_dir, f"archify_{diagram_type}_{_now()}.html")
    args = ["deliver", diagram_type, in_file, output_path, "--quality", quality, "--json"]
    if repo_root:
        args += ["--repo-root", repo_root]
    proc = _run(args)
    html_ok = os.path.exists(output_path) and os.path.getsize(output_path) > 0
    if proc.returncode == 0 and html_ok:
        if open_browser:
            _open(output_path)
        return ToolResult(True, content=_fmt_html_result(output_path, proc.stdout))
    if html_ok:
        if open_browser:
            _open(output_path)
        return ToolResult(
            True,
            content=_fmt_html_result(output_path, proc.stdout, warn="deliver 最终校验未全过，但 HTML 已生成，可手动预览"),
        )
    return ToolResult(False, error=_err(proc))


def _action_validate(kw: dict) -> ToolResult:
    diagram_type = (kw.get("diagram_type") or "").strip().lower()
    if diagram_type not in _TYPES:
        return ToolResult(False, error=f"diagram_type 必须是 {_TYPES} 之一")
    quality = (kw.get("quality") or "showcase").strip().lower()
    if quality not in ("showcase", "standard"):
        quality = "showcase"
    out_dir = _ensure_output_dir()
    try:
        in_file = _resolve_input(kw, out_dir)
    except (ValueError, FileNotFoundError) as e:
        return ToolResult(False, error=str(e))
    proc = _run(["validate", diagram_type, in_file, "--quality", quality, "--json"])
    if proc.returncode == 0:
        return ToolResult(True, content=proc.stdout.strip() or "校验通过")
    return ToolResult(False, error=_err(proc))


def _action_inspect(kw: dict) -> ToolResult:
    diagram_type = (kw.get("diagram_type") or "").strip().lower()
    if diagram_type not in _TYPES:
        return ToolResult(False, error=f"diagram_type 必须是 {_TYPES} 之一")
    out_dir = _ensure_output_dir()
    try:
        in_file = _resolve_input(kw, out_dir)
    except (ValueError, FileNotFoundError) as e:
        return ToolResult(False, error=str(e))
    proc = _run(["inspect", diagram_type, in_file])
    if proc.returncode == 0:
        return ToolResult(True, content=proc.stdout.strip())
    return ToolResult(False, error=_err(proc))


def _action_check(kw: dict) -> ToolResult:
    output_path = kw.get("output_path")
    if not output_path or not os.path.exists(output_path):
        return ToolResult(False, error=f"output_path 必须指向已生成的 HTML 文件，收到 {output_path!r}")
    proc = _run(["check", output_path])
    if proc.returncode == 0:
        return ToolResult(True, content=proc.stdout.strip() or "check 通过")
    return ToolResult(False, error=_err(proc))


def _action_guide(kw: dict) -> ToolResult:
    scenario = kw.get("scenario") or ""
    lang = (kw.get("lang") or "en").strip().lower()
    if lang not in ("en", "zh"):
        lang = "en"
    proc = _run(["guide", scenario, "--json", "--lang", lang])
    if proc.returncode == 0:
        return ToolResult(True, content=proc.stdout.strip())
    return ToolResult(False, error=_err(proc))


def _action_brands(kw: dict) -> ToolResult:
    query = kw.get("brand_query") or ""
    proc = _run(["brands", query, "--json"])
    if proc.returncode == 0:
        return ToolResult(True, content=proc.stdout.strip())
    return ToolResult(False, error=_err(proc))


def _action_doctor() -> ToolResult:
    proc = _run(["doctor"])
    if proc.returncode == 0:
        return ToolResult(True, content=proc.stdout.strip())
    return ToolResult(False, error=_err(proc))


def _action_examples() -> ToolResult:
    proc = _run(["examples"])
    if proc.returncode == 0:
        return ToolResult(True, content=proc.stdout.strip())
    return ToolResult(False, error=_err(proc))


# ── 入口 ─────────────────────────────────────────────────────────────────────
def _impl(tool_ctx, **kwargs):
    action = (kwargs.get("action") or "").strip().lower()
    try:
        if action == "preview":
            kwargs["open"] = True
            return _action_render(kwargs)
        if action == "render":
            return _action_render(kwargs)
        if action == "validate":
            return _action_validate(kwargs)
        if action == "inspect":
            return _action_inspect(kwargs)
        if action == "check":
            return _action_check(kwargs)
        if action == "guide":
            return _action_guide(kwargs)
        if action == "brands":
            return _action_brands(kwargs)
        if action == "doctor":
            return _action_doctor()
        if action == "examples":
            return _action_examples()
        return ToolResult(
            False,
            error=f"不支持的 action：{action!r}（可选：render/validate/preview/inspect/check/guide/brands/doctor/examples）",
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, error="archify 执行超时（>300s），图可能过于复杂，请简化后重试")
    except (ValueError, FileNotFoundError) as e:
        return ToolResult(False, error=str(e))
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"archify 工具异常：{e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "archify",
        "description": (
            "Archify 架构图生成器（适配 tt-a1i/archify 运行时）。"
            "把代码库 / 系统描述 / 纯语言需求 / Mermaid 转成自包含交互式架构图 HTML。"
            "支持 5 类图：architecture(组件/服务/云边界/基础设施)、workflow(流程/审批/CI-CD)、"
            "sequence(API 调用链/请求生命周期/异步链路)、dataflow(管道/ETL/数据血缘/治理)、"
            "lifecycle(状态机/生命周期/重试/终态)。"
            "典型流程：(1) action=guide 获取场景引导；(2) 按类型生成符合 schema 的 typed JSON；"
            "(3) action=validate 校验；(4) action=render 生成 HTML（内部走 deliver 验收）。"
            "参考：插件 archify_runtime/schemas 含各类型 schema，archify_runtime/examples 含输入样例。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["render", "validate", "preview", "inspect", "check", "guide", "brands", "doctor", "examples"],
                    "description": "操作：render=生成HTML(走deliver验收)；validate=校验JSON；preview=生成并打开浏览器；inspect=检查JSON；check=检查HTML；guide=场景引导；brands=品牌查询；doctor=自检；examples=列出示例。",
                },
                "diagram_type": {
                    "type": "string",
                    "enum": _TYPES,
                    "description": "图类型，render/validate/inspect 必填。",
                },
                "input_json": {
                    "type": "string",
                    "description": "archify typed JSON 字符串（render/validate/inspect 与 input_path 二选一）。",
                },
                "input_path": {
                    "type": "string",
                    "description": "已存在的 JSON 文件路径（替代 input_json）。",
                },
                "output_path": {
                    "type": "string",
                    "description": "HTML 输出路径（render/preview/check 用）。省略则自动命名到插件 output 目录。",
                },
                "quality": {
                    "type": "string",
                    "enum": ["showcase", "standard"],
                    "description": "质量档位，默认 showcase（9/9 验收）。",
                },
                "repo_root": {
                    "type": "string",
                    "description": "代码仓库根路径（--repo-root，用于 repository evidence 收据）。",
                },
                "scenario": {
                    "type": "string",
                    "description": "guide 的场景描述（如 'Kafka 消费链'）。",
                },
                "brand_query": {
                    "type": "string",
                    "description": "brands 的查询词（品牌名/别名/域名/类别）。",
                },
                "lang": {
                    "type": "string",
                    "enum": ["en", "zh"],
                    "description": "guide 输出语言，默认 en。",
                },
                "open": {
                    "type": "boolean",
                    "description": "render/preview 生成后是否在默认浏览器打开 HTML，默认 false。",
                },
            },
            "required": ["action"],
        },
    },
}


def _preview(args):
    a = args or {}
    action = a.get("action", "")
    dt = a.get("diagram_type", "")
    extra = a.get("scenario") or a.get("brand_query") or ""
    s = f"archify {action}"
    if dt:
        s += f" [{dt}]"
    if extra:
        s += f" {extra}"
    return s.strip()


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "archify", _SCHEMA, impl=_impl,
        danger="safe",
        cn_name="archify 架构图",
        group="archify",
        description="生成交互式架构图 HTML（architecture/workflow/sequence/dataflow/lifecycle）",
        aliases=["archify", "架构图", "画架构图", "Archify"],
        render_mode="",
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
        metadata={"category": "visualization"},
    )
