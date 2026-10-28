# -*- coding: utf-8 -*-
"""PPT 生成工具 — 包装上游 dsh-ppt 技能的 Node 生成器（build-deck.mjs）。

上游在 dsh 里注册了 8 个工具（ppt_create / ppt_themes / ppt_templates / ppt_edit /
ppt_data / ppt_undo / ppt_check / ppt_render），实现都在 lib/*.js 里且只是对
skills/dsh-ppt/scripts/*.mjs 的薄封装。这里不重写生成逻辑：直接调用脚本本体，
用 action 参数分流。脚本依赖 Node 22.19+ 与 npm install 装的 Office Kit。
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from app.tools.result import ToolResult

_SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "ppt-deck"
_SCRIPT = _SKILL_DIR / "scripts" / "build-deck.mjs"
_NODE_MIN = (22, 19, 0)

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ppt_deck",
        "description": (
            "把一句话或 Markdown 文档生成完整演示文稿：独立 HTML 网页放映 + 可编辑 PPTX + deck manifest。\n"
            "action 切换能力：\n"
            "  - create（默认）: 生成三件套（html / pptx / json）\n"
            "  - list_themes: 列出 5 套内置主题 id\n"
            "  - list_templates: 列出场景结构参考（weekly / defense / project / pitch）\n"
            "  - check: 查看已有 deck.json 的质量报告与页码/ID\n"
            "  - render: 用可选官方引擎把 pptx 渲染成逐页 PNG/PDF\n"
            "\n"
            "典型用法：\n"
            "  ppt_deck(title='产品发布', content='# 一\\n要点…', theme='data', lang='zh', out='dist')\n"
            "  ppt_deck(action='list_themes')\n"
            "  ppt_deck(action='check', deck='dist/产品发布.json')\n"
            "\n"
            "依赖 Node 22.19+，且技能目录需先跑过 npm install（图片/图表导出需要 Office Kit）。"
            "纯文本放映不需要 Office Kit。缺依赖时工具会直接告诉你缺什么。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list_themes", "list_templates", "check", "render"],
                    "description": "要执行的动作，默认 create",
                },
                "title": {"type": "string", "description": "演示文稿标题（create 必填）"},
                "content": {
                    "type": "string",
                    "description": "Markdown 正文；或文件路径（自动读取）；或 @- 从 stdin 读（此处不适用）",
                },
                "slides": {"type": "string", "description": "结构化 slides 的 JSON 字符串，与 content 二选一"},
                "template": {
                    "type": "string",
                    "description": "场景模板：weekly / defense / project / pitch；只给模板会生成待填草稿",
                },
                "theme": {"type": "string", "description": "视觉主题 id，用 action=list_themes 查"},
                "lang": {"type": "string", "enum": ["zh", "en", "bilingual"], "description": "界面语言，默认 zh"},
                "motion": {"type": "string", "enum": ["on", "off"], "description": "转场与入场动画，默认 on"},
                "out": {"type": "string", "description": "输出目录，默认当前工作目录"},
                "file": {"type": "string", "description": "输出文件名前缀，默认取标题"},
                "overwrite": {"type": "boolean", "description": "覆盖同名三件套（默认自动追加 -1/-2）"},
                "deck": {"type": "string", "description": "已有 deck.json 路径（action=check 用）"},
                "deck_file": {"type": "string", "description": "待渲染的 pptx 路径（action=render 用）"},
                "format": {"type": "string", "enum": ["png", "pdf", "both"], "description": "render 的输出格式"},
                "extra_args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "其余 CLI 参数透传，如 ['--brand', '{\"primary\":\"#c33\"}'] 或 ['--revision','3']",
                },
            },
            "required": [],
        },
    },
}


def _find_node():
    """返回 (node 路径, (major, minor, patch)) 或 (None, None)。

    宿主以 GUI 方式启动时 PATH 往往只有 /usr/bin:/bin:/usr/sbin:/sbin，
    homebrew / nvm / volta 装的 node 都不在 PATH 里，所以要显式探测常见位置。
    """
    candidates = []
    found = shutil.which("node")
    if found:
        candidates.append(found)
    candidates += [
        "/opt/homebrew/bin/node",   # Apple Silicon homebrew
        "/usr/local/bin/node",      # Intel homebrew
        "/usr/bin/node",
        str(Path.home() / ".volta/bin/node"),
    ]
    # nvm：取版本号最大的一个
    nvm_root = Path.home() / ".nvm/versions/node"
    if nvm_root.is_dir():
        versions = sorted(nvm_root.glob("v*/bin/node"), key=lambda p: p.parent.name, reverse=True)
        candidates += [str(p) for p in versions]
    for exe in candidates:
        if not Path(exe).is_file():
            continue
        try:
            out = subprocess.run([exe, "-v"], capture_output=True, text=True, timeout=15).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        m = re.match(r"v(\d+)\.(\d+)\.(\d+)", out)
        if m:
            return exe, tuple(int(x) for x in m.groups())
    return None, None


def _build_argv(kwargs):
    action = (kwargs.get("action") or "create").strip()
    argv = []
    if action == "list_themes":
        argv.append("--list-themes")
    elif action == "list_templates":
        argv.append("--list-templates")
    elif action == "check":
        deck = kwargs.get("deck")
        if not deck:
            return None, "action=check 需要 deck 参数（deck.json 路径）"
        argv.extend(["--check", str(deck)])
    elif action == "render":
        deck_file = kwargs.get("deck_file") or kwargs.get("deck")
        if not deck_file:
            return None, "action=render 需要 deck_file 参数（.pptx 路径）"
        argv.extend(["--render", str(deck_file)])
        if kwargs.get("format"):
            argv.extend(["--format", str(kwargs["format"])])
    elif action == "create":
        if not kwargs.get("title"):
            return None, "action=create 需要 title 参数"
        argv.extend(["--title", str(kwargs["title"])])
        for key in ("content", "slides", "template", "theme", "lang", "motion", "out", "file"):
            val = kwargs.get(key)
            if val:
                argv.extend([f"--{key}", str(val)])
    else:
        return None, f"未知 action：{action}"

    if kwargs.get("overwrite"):
        argv.append("--overwrite")
    extra = kwargs.get("extra_args") or []
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except ValueError:
            return None, "extra_args 需要字符串数组"
    if not isinstance(extra, list):
        return None, "extra_args 需要字符串数组"
    argv.extend(str(x) for x in extra)
    return argv, None


def _ppt_impl(tool_ctx, **kwargs):
    if not _SCRIPT.is_file():
        return ToolResult(False, error=f"技能脚本缺失：{_SCRIPT}")

    node_exe, ver = _find_node()
    if ver is None:
        return ToolResult(
            False,
            error=(
                "未找到 Node.js。PPT 生成依赖 Node 22.19+（脚本是 .mjs）。\n"
                "已探测 PATH、/opt/homebrew/bin、/usr/local/bin、/usr/bin、~/.volta、~/.nvm。\n"
                "装好后重试；或让助手直接按技能正文用 node 手工跑脚本。"
            ),
        )
    if ver < _NODE_MIN:
        return ToolResult(
            False,
            error=f"Node 版本过低：v{'.'.join(map(str, ver))}，需要 22.19.0 或 24+。",
        )

    argv, err = _build_argv(kwargs)
    if err:
        return ToolResult(False, error=err)

    workdir = (tool_ctx or {}).get("workdir") or str(_SKILL_DIR)
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")

    try:
        proc = subprocess.run(
            [node_exe, str(_SCRIPT), *argv],
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, error="PPT 生成超过 300 秒未结束，已中止（大文档可拆成多次或减少页数）")
    except OSError as exc:
        return ToolResult(False, error=f"无法启动 node：{exc}")

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        detail = stderr or stdout or f"退出码 {proc.returncode}"
        if "Cannot find package" in detail or "npm install" in detail:
            detail += "\n\n提示：在技能目录跑 npm install --ignore-scripts 安装 Office Kit。"
        return ToolResult(False, error=f"ppt_deck 执行失败：\n{detail[:4000]}")
    # 静默失败保护：生成器用 `import.meta.url === pathToFileURL(process.argv[1])` 判断是否直接执行，
    # 脚本路径经过符号链接时两者不等 → main() 不跑，退出码仍是 0 且零输出。
    if not stdout:
        return ToolResult(
            False,
            error=(
                "ppt_deck 退出码 0 却没有任何输出，说明生成器没真正执行。\n"
                f"脚本路径：{_SCRIPT}\n"
                "常见原因：插件目录是符号链接（如 macOS 的 /tmp → /private/tmp），"
                "生成器判断「是否直接运行」时路径比对失败。把插件放到真实路径下再试。"
            ),
        )
    content = stdout
    if stderr:
        content = f"{content}\n\n[stderr]\n{stderr[:1500]}"
    return ToolResult(True, content=content)


def register(registry):
    """工具插件化注册入口：ppt_deck（单入口 + action 分发）"""
    registry.register(
        "ppt_deck",
        _SCHEMA,
        impl=_ppt_impl,
        danger="safe",
        icon="Presentation",
        cn_name="PPT 生成",
        group="文档处理",
        description="一句话或文档生成 HTML 放映 + 可编辑 PPTX",
        aliases=["ppt_create", "ppt"],
    )
