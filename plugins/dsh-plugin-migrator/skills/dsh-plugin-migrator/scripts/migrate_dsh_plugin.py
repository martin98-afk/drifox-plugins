#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按能力清单把 dsh 插件转成 DriFox 插件目录。

用法:
    python scripts/migrate_dsh_plugin.py --inventory <capability-inventory.json>
                                         --repo <drifox-plugins2 根>
                                         [--plugin-id <name>] [--description <文本>]
                                         [--overwrite]

退出码:
    0 — 落盘成功（可能含 MIGRATION_TODO）
    2 — 硬停止（清单非法 / 目标已存在且未 --overwrite）
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TODO_MARK = "MIGRATION_TODO"

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


def slugify(raw: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (raw or "").lower()).strip("-")
    s = re.sub(r"^-+|-+$", "", s)
    s = re.sub(r"-{2,}", "-", s)
    if not s or not s[0].isalpha():
        s = "dsh-" + s if s else "dsh-plugin"
    return s[:64].rstrip("-") or "dsh-plugin"


def pkg_short(name: str | None) -> str:
    return (name or "").split("/")[-1]


def tool_name_from_pkg(short: str) -> str:
    """@deepseek-ai/dsh-tool-web -> dsh_web"""
    base = re.sub(r"^dsh-(tool|command)-", "", short)
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "unknown"


def cmd_name_from_pkg(short: str) -> str:
    """@deepseek-ai/dsh-command-compact -> compact"""
    base = re.sub(r"^dsh-command-", "", short)
    base = re.sub(r"[^a-z0-9-]+", "-", base).strip("-")
    return base or "command"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------- skills


def port_skills(inv: dict, dest: Path, src_root: Path, todos: list[dict]) -> list[str]:
    made: list[str] = []
    pkg_name = pkg_short((inv.get("package") or {}).get("name"))
    for sb in inv.get("skill_bundles", []):
        raw_name = sb.get("name") or ""
        # 包根的 SKILL.md 会被扫成名为包目录的一段路径；用它自己的 name，
        # 没有就用包名（去掉 dsh- 前缀，和插件 id 的生成口径一致）
        name = slugify(str((sb.get("frontmatter") or {}).get("name") or raw_name))
        if name in {"", "sh"} or raw_name.startswith(pkg_name):
            name = slugify(pkg_name.removeprefix("dsh-")) or slugify(pkg_name)
        fm = sb.get("frontmatter") or {}
        if fm.get("disable-model-invocation") in (True, "true", "yes", "on", "1"):
            todos.append({
                "kind": "skill",
                "target": f"skills/{name}",
                "why": "dsh 侧 disable-model-invocation=true，该 skill 不面向模型，未迁移",
                "action": "确认是否需要在 DriFox 侧保留（DriFox 无此开关）",
            })
            continue
        if not fm.get("description"):
            todos.append({
                "kind": "skill",
                "target": f"skills/{name}",
                "why": "源 frontmatter 无 description，DriFox 必填",
                "action": "补写 description（20 字符以上）",
            })

        src_path = src_root / sb["path"]
        lines = ["---", f"name: {name}"]
        desc = fm.get("description") or "TODO: 补充触发描述"
        lines.append(f"description: {desc}")
        if fm.get("version"):
            lines.append(f"version: {fm['version']}")
        if isinstance(fm.get("metadata"), dict):
            lines.append("metadata:")
            for k, v in fm["metadata"].items():
                lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
        lines.append("---")
        lines.append("")

        if sb["kind"] == "bundle":
            body = (src_path / "SKILL.md").read_text(encoding="utf-8")
        else:
            body = src_path.read_text(encoding="utf-8")
        # 去掉源 frontmatter，只留正文
        if body.startswith("---"):
            parts = body.split("\n---", 1)
            body = parts[1].split("\n", 1)[1] if len(parts) > 1 and "\n" in parts[1] else body
        if fm.get("whenToUse"):
            body = f"## 何时使用\n\n{fm['whenToUse']}\n\n" + body
        if str(fm.get("user-invocable")).lower() in ("false", "no", "off", "0"):
            body += "\n\n> 源包声明该 skill 不面向用户直接调用。\n"

        write_text(dest / "skills" / name / "SKILL.md", "\n".join(lines) + body.strip() + "\n")

        for res in sb.get("resources", []):
            res_src = src_path / res
            res_dst = dest / "skills" / name / res
            if res_src.is_dir():
                shutil.copytree(res_src, res_dst, dirs_exist_ok=True)
                if res == "scripts":
                    for f in res_dst.rglob("*"):
                        if f.is_file() and f.suffix in {".ts", ".js", ".mjs"}:
                            todos.append({
                                "kind": "script",
                                "target": str(f.relative_to(dest)),
                                "why": "脚本依赖 dsh/Node 运行时 API",
                                "action": "改写为 Python 或删除",
                            })
        made.append(name)
    return made


# ---------------------------------------------------------------- agents


def port_agents(inv: dict, dest: Path, todos: list[dict]) -> list[str]:
    made: list[str] = []
    for preset in inv.get("agent_presets", []):
        pid = slugify(str(preset.get("preset_id") or "preset"))
        plugins = preset.get("plugins") or []
        write_tools = [
            p for p in plugins
            if pkg_short(p.get("name")).startswith(("dsh-tool-fs", "dsh-tool-bash", "dsh-tool-web"))
        ]
        mode = "all" if write_tools else "subagent"
        body = f"""---
description: TODO: 用一句话说明 {pid} 这个 agent preset 的定位与触发场景（描述需自写，不得复制源包原文）。
mode: {mode}
---

# Role

TODO: 描述该 preset 的行为定位（抽象定位可保留，提示词原文不得照搬）。

# Primary Goal

- TODO: 列出该 preset 承担的主要工作

# Constraints

- 本 agent 由 dsh 插件自动迁移生成，行为语义待人工补全

# dsh 源 preset 清单（未映射）

源 preset `{preset.get("preset_id")}`（order={preset.get("order")}）声明了 {len(plugins)} 个插件行。
DriFox 没有组合层，以下清单仅供参考，不生成对应组件：

| dsh 插件 | 说明 |
|---|---|
"""
        for p in plugins:
            body += f"| `{p.get('name')}` | {TODO_MARK}: 确认该行在 dsh 中的职责及 DriFox 是否有等价物 |\n"
        body += "\n"
        write_text(dest / "agents" / f"{pid}.md", body)
        todos.append({
            "kind": "agent",
            "target": f"agents/{pid}.md",
            "why": "preset 只提供配置清单，persona 语义需人工按源材料重写",
            "action": "补写 description / Role / Primary Goal",
        })
        made.append(pid)
    return made


# ---------------------------------------------------------------- commands


def stub_commands(inv: dict, dest: Path, todos: list[dict]) -> list[str]:
    made: list[str] = []
    seen: set[str] = set()
    for row in inv.get("patch_rows", []):
        if row.get("verdict") != "stub":
            continue
        short = pkg_short(row.get("name"))
        if not short.startswith("dsh-command-"):
            continue
        cname = slugify(cmd_name_from_pkg(short))
        if cname in seen:
            continue
        seen.add(cname)
        desc = inv.get("locale_meta", {}).get("description") or f"TODO: 说明 /{cname} 做什么"
        body = f"""---
description: {desc}
type: prompt
---

# /{cname}

你正在处理 `/{cname}` 命令。

<!-- {TODO_MARK}: 源命令由 TypeScript handler 实现（{row.get('name')}）。
     以下仅为按源材料可确定的行为骨架，真实行为需人工按 handler 语义补全。 -->

## 源行为线索

- 源包：`{row.get('name')}`（patch 行 id=`{row.get('id')}`）
- 可读材料：{"locale / README 可用" if inv.get("readable_materials", {}).get("has_locale") or inv.get("readable_materials", {}).get("has_readme") else "无可读材料（仅编译产物）"}

## 行为

TODO: 按源 handler 的语义写清步骤。

## 模板变量

- `$ARGUMENTS`：用户输入的完整参数
"""
        write_text(dest / "commands" / f"{cname}.md", body)
        todos.append({
            "kind": "command",
            "target": f"commands/{cname}.md",
            "why": "dsh 命令是 TS handler，提示词语义无法自动推导",
            "action": f"读源包 handler 语义后补全正文；若只是状态开关则改判 skip",
        })
        made.append(cname)
    return made


# ---------------------------------------------------------------- tools


def stub_tools(inv: dict, dest: Path, todos: list[dict]) -> list[str]:
    made: list[str] = []
    seen: set[str] = set()
    for row in inv.get("patch_rows", []):
        if row.get("verdict") != "stub":
            continue
        short = pkg_short(row.get("name"))
        if not short.startswith("dsh-tool-"):
            continue
        tname = tool_name_from_pkg(short)
        if tname in seen:
            continue
        seen.add(tname)

        py = f'''# -*- coding: utf-8 -*-
"""{short} 的 DriFox 迁移骨架。

{TODO_MARK}: 源工具由 TypeScript `defineTool` 实现，参数 schema 若能从源包读到应照搬，
`execute` 语义必须人工用 Python 重写。此处显式抛错，不伪造返回值。
"""

_SCHEMA = {{
    "type": "function",
    "function": {{
        "name": "{tname}",
        "description": "TODO: 用一句话说明该工具做什么",
        "parameters": {{
            "type": "object",
            "properties": {{}},
        }},
    }},
}}


def _impl(tool_ctx, **kwargs):
    raise NotImplementedError(
        "{TODO_MARK}: 源工具 {short} 的行为需人工按 TypeScript 实现重写。"
    )


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "{tname}",
        _SCHEMA,
        impl=_impl,
        danger="safe",  # {TODO_MARK}: 危险级别需人工确认（源侧无对应声明）
        cn_name="{tname}",
        group="{short}",
        description="TODO: 工具描述",
    )
'''
        write_text(dest / "tools" / f"{tname}.py", py)
        todos.append({
            "kind": "tool",
            "target": f"tools/{tname}.py",
            "why": "TS 工具的 execute 语义不可自动翻译",
            "action": f"按源 {short} 的实现重写 _impl，并确认 danger 级别",
        })
        made.append(tname)
    return made


# ---------------------------------------------------------------- hooks


# 观测型 hook 的默认事件集。DriFox 白名单见 docs/hooks.md。
# 只有 BuildSystemPrompt 的返回值会进 system prompt，其余一律返回空串，
# 否则返回值会被拼进消息流污染会话。
HOOK_EVENTS = ["SessionStart", "PostToolUse", "PostAssistantMessage", "Stop"]
DECLARATION_EVENT = "BuildSystemPrompt"


def stub_hooks(inv: dict, dest: Path, plugin_id: str, todos: list[dict]) -> list[str]:
    made: list[str] = []
    rows = [r for r in inv.get("patch_rows", [])
            if r.get("verdict") == "stub" and r.get("target") == "hooks"]
    if not rows:
        return made

    mod = re.sub(r"[^a-z0-9]+", "_", plugin_id) + "_hook"
    events = HOOK_EVENTS + [DECLARATION_EVENT]

    hooks_json = {
        "description": f"TODO: 说明 {plugin_id} 的 hook 做什么",
        "hooks": {},
    }
    for idx, ev in enumerate(events, 1):
        hooks_json["hooks"][ev] = [{
            "hooks": [{
                "type": "python",
                "function": f".{mod}:{_hook_func_name(ev)}",
                "timeout": 15,
                "enabled": True,
                "id": f"0000000{idx}-0000-4000-8000-00000000000{idx}",
                "add_output_to_context": ev == DECLARATION_EVENT,
            }]
        }]
    write_text(dest / "hooks" / "hooks.json",
               json.dumps(hooks_json, ensure_ascii=False, indent=4) + "\n")

    sources = "\n".join(
        f"  - `{r.get('name')}`（patch id=`{r.get('id')}`）" for r in rows
    )
    py = f'''# -*- coding: utf-8 -*-
"""{plugin_id} 的 hook 迁移骨架。

{TODO_MARK}: 源能力是 dsh 侧的运行时服务，语义需人工按源材料重写。
本文件提供合法的 hook 契约骨架（函数签名 + CLI 入口），行为留空。

源 patch 行：
{sources}

关键约束（DriFox 以 subprocess 每次全新调用 hook，无内存共享）：
- 除 {DECLARATION_EVENT} 外，所有 hook 返回**空串**，避免返回值被注入消息流；
  需要留痕就写盘（建议 memory/ 目录），不要靠返回值。
- 必须幂等（hook 可能重复触发）。
- 单次执行必须控制在 hooks.json 声明的 timeout（15s）内。
"""

import argparse
import json
import sys

PLUGIN_NAME = "{plugin_id}"

{TODO_MARK}_DECLARATION = (
    "TODO: 写一句静态能力声明（{DECLARATION_EVENT} 会把它拼进 system prompt 尾部）。"
    "必须静态到头——动态拼接会话状态会让会话缓存失稳。"
)
'''
    for ev in HOOK_EVENTS:
        fn = _hook_func_name(ev)
        py += f'''

def {fn}(event: str, context: dict) -> str:
    """{TODO_MARK}: 实现 {ev} 的行为。

    观测型 hook 返回空串；需要留痕请写盘，不要用返回值。
    """
    return ""


def handle_{fn}(ctx: dict) -> str:
    """CLI 调试用（与 {fn} 行为一致）。"""
    return {fn}("{ev}", ctx)
'''
    py += f'''

def {_hook_func_name(DECLARATION_EVENT)}(event: str, context: dict) -> str:
    """{DECLARATION_EVENT}：返回静态能力声明，会被拼进 system prompt 尾部。"""
    return {TODO_MARK}_DECLARATION


def handle_{_hook_func_name(DECLARATION_EVENT)}(ctx: dict) -> str:
    """CLI 调试用。"""
    return {TODO_MARK}_DECLARATION


# ============================================================
# CLI 入口（独立调试用）
# 用法:
#   echo '{{}}' | python {mod}.py --event=SessionStart
# ============================================================


_HANDLER_MAP = {{
'''
    for ev in events:
        py += f'    "{ev}": handle_{_hook_func_name(ev)},\n'
    py += '''}


def main():
    parser = argparse.ArgumentParser(description=f"{PLUGIN_NAME} Hook Handler")
    parser.add_argument("--event", required=True, choices=list(_HANDLER_MAP.keys()))
    args = parser.parse_args()

    raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    try:
        ctx = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        ctx = {}

    result = _HANDLER_MAP[args.event](ctx)
    if isinstance(result, str):
        print(result)


if __name__ == "__main__":
    main()
'''
    write_text(dest / "hooks" / f"{mod}.py", py)
    todos.append({
        "kind": "hooks",
        "target": f"hooks/{mod}.py",
        "why": f"源能力是 dsh 运行时服务（{len(rows)} 个 patch 行），行为语义无法自动推导",
        "action": "按源材料实现各 hook 函数，并确认事件集是否匹配源行为",
    })
    made.append(mod)
    return made


def _hook_func_name(event: str) -> str:
    return "hook_" + re.sub(r"(?<!^)(?=[A-Z])", "_", event).lower()


# ---------------------------------------------------------------- mcp


def stub_mcp(inv: dict, dest: Path, todos: list[dict]) -> list[str]:
    made: list[str] = []
    rows = [r for r in inv.get("patch_rows", [])
            if r.get("verdict") == "stub" and r.get("target") == "mcp"]
    if not rows:
        return made

    servers = {}
    for r in rows:
        sid = slugify(str(r.get("id") or pkg_short(r.get("name"))))
        servers[sid] = {
            "type": "stdio",
            "command": "TODO_COMMAND",
            "args": [],
            "env": {},
            "enabled": False,  # 迁移产物默认不自动启动：凭据未知
        }
    cfg = {"mcpServers": servers}
    write_text(dest / ".mcp.json", json.dumps(cfg, ensure_ascii=False, indent=4) + "\n")
    todos.append({
        "kind": "mcp",
        "target": ".mcp.json",
        "why": "源为 dsh MCP 客户端/服务端，启动命令与凭据无法从源推导",
        "action": "填 command/args/url 与 credential 声明；密钥不得入库，走 credential 或 ${env.VAR}",
    })
    made.append(".mcp.json")
    return made


# ---------------------------------------------------------------- ui


def stub_ui(inv: dict, dest: Path, plugin_id: str, todos: list[dict]) -> list[str]:
    """Client UI → ui/ 骨架。

    只搬两件事：注册哪个扩展点、挂哪个容器方位。widget 本体一律留空——
    React 组件与 Qt widget 之间没有机械映射，任何「自动翻译」都是编造。
    骨架里的占位 QWidget 必须能真被实例化，否则 register_ui 一跑就崩，
    连结构验证都做不了。
    """
    made: list[str] = []
    rows = [r for r in inv.get("patch_rows", [])
            if r.get("verdict") == "stub" and r.get("target") == "ui"]
    if not rows:
        return made

    # 多个 UI 行时按扩展点聚合：同一类扩展点只出一个骨架，避免重复注册
    by_ext: dict[str, list[dict]] = {}
    for r in rows:
        hint = r.get("ui_hint") or {}
        ext = hint.get("extension") or "floating_card"
        by_ext.setdefault(ext, []).append(r)

    safe = re.sub(r"[^a-z0-9]+", "_", plugin_id)
    cards: list[dict] = []
    for ext, group in sorted(by_ext.items()):
        hint = group[0].get("ui_hint") or {}
        container = hint.get("container") or "right"
        cid = f"{plugin_id}-{ext.replace('_', '-')}"
        cards.append({
            "extension": ext,
            "card_id": cid,
            "container": container,
            "sources": [g.get("name") for g in group],
        })

    src_lines = "\n".join(
        f"  - `{r.get('name')}` → {r.get('ui_hint', {}).get('extension')}"
        f"（方位 {r.get('ui_hint', {}).get('container')}）"
        for r in rows
    )

    init_py = f'''# -*- coding: utf-8 -*-
"""{plugin_id} 的 UI 迁移骨架。

{TODO_MARK}: 源能力是 dsh 的 Client UI（React），DriFox 侧是 Qt widget，
两者没有机械映射。本文件只固化两件事：注册哪个扩展点、挂哪个容器方位。
widget 本体必须人工重写——占位类只保证 register_ui 能跑通结构验证。

源 patch 行：
{src_lines}

扩展点与方位的推测置信度为 low：host 侧的 dsh-client-ui-* 包 apply() 多为
空函数（实测 32 个里 31 个无任何 register 调用），浏览器那一半通过
package.json 的 dsh.client 声明单独分发，host 包内无可提取的 UI 结构。
"""

import sys

from loguru import logger


def _clear_stale_modules(plugin_id: str) -> None:
    """热重载兼容：清理 sys.modules 中残留的子模块缓存。"""
    prefix = f"ui_plugin_{{plugin_id.replace('-', '_')}}."
    for key in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[key]


def _import_qt():
    """按 DriFox 双栈现状探测 Qt 绑定：先 PySide6，再 PyQt5。

    不要写死任一侧——仓库主线是 PyQt5，pyside6 分支另有一套，
    硬编码绑定会让插件在另一条线上直接 ImportError。
    """
    for mod in ("PySide6", "PyQt5"):
        try:
            widgets = __import__(f"{{mod}}.QtWidgets", fromlist=["QtWidgets"])
            return widgets
        except ImportError:
            continue
    raise ImportError("未找到 Qt 绑定（PySide6 / PyQt5 均未安装）")


def register_ui(registry):
    """注册 {plugin_id} 的 UI 组件（骨架）。"""
    _clear_stale_modules("{plugin_id}")

    QtWidgets = _import_qt()
    QLabel = QtWidgets.QLabel
    QVBoxLayout = QtWidgets.QVBoxLayout
    QWidget = QtWidgets.QWidget
'''

    for c in cards:
        cls = "_" + "".join(p.title() for p in c["extension"].split("_")) + "Placeholder"
        init_py += f'''
    class {cls}(QWidget):
        """{TODO_MARK}: 用真实 widget 替换本占位类。

        源包：{', '.join(f'`{s}`' for s in c['sources'])}
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.addWidget(
                QLabel("TODO: {c['extension']} —— 源为 dsh Client UI，widget 需人工重写")
            )
'''
    init_py += "\n"
    for c in cards:
        cls = "_" + "".join(p.title() for p in c["extension"].split("_")) + "Placeholder"
        if c["extension"] == "floating_card":
            init_py += f'''    registry.register_floating_card(
        plugin_name="{plugin_id}",
        card_id="{c['card_id']}",
        widget_class={cls},
        container="{c['container']}",
        title="{TODO_MARK}: 卡片标题",
        default_visible=False,
    )
'''
        elif c["extension"] == "settings_card":
            init_py += f'''    registry.register_settings_card(
        "{plugin_id}",
        "{c['card_id']}",
        "{TODO_MARK}: 设置卡标题",
        {cls},
        priority=1,
    )
'''
        elif c["extension"] == "content_renderer":
            init_py += f'''    def _render_{re.sub(r"[^a-z0-9]", "_", c['card_id'])}(data, context=None) -> str:
        """{TODO_MARK}: 返回 HTML 字符串。"""
        return "<p>TODO: 渲染 HTML</p>"

    registry.register_content_renderer(
        plugin_name="{plugin_id}",
        type_name="{c['card_id'].rsplit('-', 1)[-1]}",
        render_func=_render_{re.sub(r"[^a-z0-9]", "_", c['card_id'])},
        priority=0,
    )
'''
        else:
            init_py += f'''    def _cond_{re.sub(r"[^a-z0-9]", "_", c['card_id'])}(message) -> bool:
        """{TODO_MARK}: 判断消息是否由本工厂处理。"""
        return False

    def _factory_{re.sub(r"[^a-z0-9]", "_", c['card_id'])}(message, parent=None):
        return {cls}(parent)

    registry.register_message_factory(
        plugin_name="{plugin_id}",
        name="{c['card_id']}",
        condition_func=_cond_{re.sub(r"[^a-z0-9]", "_", c['card_id'])},
        factory_func=_factory_{re.sub(r"[^a-z0-9]", "_", c['card_id'])},
        priority=0,
    )
'''

    init_py += f'''
    logger.info("[{plugin_id}] UI components registered (skeleton)")


def unload_ui(registry):
    """卸载钩子（骨架无残留状态需要清理）"""
'''
    write_text(dest / "ui" / "__init__.py", init_py)
    todos.append({
        "kind": "ui",
        "target": "ui/__init__.py",
        "why": f"源为 dsh Client UI（{len(rows)} 行），React 组件无 Qt 等价物；"
               "扩展点与方位均为 low 置信度推测",
        "action": "人工重写 widget（PySide6/Qt）；确认扩展点类型与 container 方位是否正确",
    })
    made.append("__init__.py")
    return made


# ---------------------------------------------------------------- manifest / report


def build_manifest(plugin_id: str, description: str, comps: dict) -> dict:
    return {
        "name": plugin_id,
        "description": description[:200],
        "version": "1.0.0",
        "author": {"name": "DriFox 社区"},
        "license": "MIT",
        "type": "user",
        "min_host_version": "0.5.0",
        "keywords": ["dsh", "deepseek-harness", "migrated"],
        "components": comps,
    }


def build_report(inv: dict, plugin_id: str, made: dict, todos: list[dict],
                 skipped: list[dict]) -> str:
    src_pkg = (inv.get("package") or {}).get("name") or "?"
    L: list[str] = []
    L.append(f"# 迁移报告：{src_pkg} → `plugins/{plugin_id}`\n")
    L.append("本插件由 `dsh-plugin-migrator` 自动生成。以下三段分别说明搬了什么、待补什么、跳过了什么。\n")
    L.append(f"- 源包：`{src_pkg}` @ `{(inv.get('package') or {}).get('version')}`")
    L.append(f"- 源路径：`{inv.get('source_dir')}`")
    L.append(f"- dsh 声明形态：`{(inv.get('dsh_declaration') or {}).get('kind')}`")
    L.append(f"- patch 文件：`{', '.join(inv.get('patch_files') or []) or '（无）'}`")
    if inv.get("engines_dsh"):
        L.append(f"- engines.dsh：`{inv['engines_dsh']}`")

    ws = inv.get("dsh_workshop") or {}
    if ws.get("capability") or ws.get("permissions"):
        L.append("")
        L.append("### 源包能力契约（dshWorkshop）\n")
        if ws.get("capability"):
            cap = ws["capability"]
            L.append(f"- capability.id：`{cap.get('id')}`（kind=`{cap.get('kind')}`）")
            if cap.get("invocation"):
                L.append(f"- invocation：`{cap['invocation']}`")
            if cap.get("expected"):
                L.append(f"- expected：`{cap['expected']}`")
        if ws.get("permissions"):
            L.append(f"- permissions：{', '.join(f'`{p}`' for p in ws['permissions'])}")
            L.append("")
            L.append("  permissions 是 DriFox 侧 `agents/*.md` 权限声明的直接依据："
                     "`filesystem:read` → 只放开 read/glob/grep，其余 deny。")
        if ws.get("dsh_versions"):
            L.append(f"- 兼容 harness 版本：{', '.join(f'`{v}`' for v in ws['dsh_versions'])}")

    agg = inv.get("aggregate_bundle") or {}
    if agg.get("is_aggregate_bundle"):
        L.append("")
        L.append(f"> ⚠ 源包声明了 {agg.get('row_count')} 个 patch 行（stub 占比 {agg.get('stub_ratio')}），"
                 "属于 harness 组合层而非离散插件。本产物含大量无语义 stub，应改以单个能力单元为目标重新迁移。\n")

    L.append("## 已生成\n")
    for kind, items in made.items():
        if items:
            L.append(f"- **{kind}**：{', '.join(f'`{i}`' for i in items)}")
    if not any(made.values()):
        L.append("- 无可自动搬运的组件。本插件目前只有骨架，必须人工补全后才能声称可用。")

    L.append("\n## 待补（MIGRATION_TODO）\n")
    if todos:
        L.append("| 类型 | 目标 | 为什么 | 要做什么 |")
        L.append("|---|---|---|---|")
        for t in todos:
            L.append(f"| {t['kind']} | `{t['target']}` | {t['why']} | {t['action']} |")
    else:
        L.append("（无）")

    L.append("\n## 未映射（skip）\n")
    L.append("这些能力属于 dsh 宿主固有服务、默认关闭的可选能力，或无 DriFox 等价载体，因此不生成组件。\n")
    if skipped:
        L.append("| dsh 插件 | 原因 |")
        L.append("|---|---|")
        for s in skipped:
            L.append(f"| `{s['name']}` | {s['note']} |")
    else:
        L.append("（无）")

    L.append("\n## 证明层级\n")
    L.append("- `structure_status`：运行 `python tools/validate_plugins.py plugins/" + plugin_id + "` 后填写")
    L.append("- `runtime_status`：存在未处理 TODO 时只能填 `blocked`")
    L.append("- `human_status`：需人工比对源插件语义后确认\n")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="把 dsh 能力清单转成 DriFox 插件目录")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--repo", required=True, help="drifox-plugins2 仓库根")
    ap.add_argument("--plugin-id", default=None)
    ap.add_argument("--description", default=None)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    inv_path = Path(args.inventory)
    if not inv_path.exists():
        print(f"error: 清单不存在 {inv_path}", file=sys.stderr)
        return 2
    inv = json.loads(inv_path.read_text(encoding="utf-8"))

    repo = Path(args.repo).resolve()
    if not (repo / "plugins").is_dir():
        print(f"error: {repo} 下没有 plugins/ 目录", file=sys.stderr)
        return 2

    src_pkg = (inv.get("package") or {}).get("name") or ""
    plugin_id = args.plugin_id or slugify(pkg_short(src_pkg).removeprefix("dsh-"))
    if not NAME_RE.match(plugin_id):
        print(f"error: 插件名不合规（kebab-case, 2-64）: {plugin_id!r}", file=sys.stderr)
        return 2

    dest = repo / "plugins" / plugin_id
    if dest.exists() and not args.overwrite:
        print(f"error: 目标已存在 {dest}（硬停止，加 --overwrite 才覆盖）", file=sys.stderr)
        return 2
    if dest.exists() and args.overwrite:
        shutil.rmtree(dest)

    src_root = Path(inv.get("source_dir") or ".")
    todos: list[dict] = []
    skipped = [
        {"name": r.get("name"), "note": r.get("note")}
        for r in inv.get("patch_rows", []) if r.get("verdict") == "skip"
    ]

    made: dict[str, list[str]] = {}
    made["skills"] = port_skills(inv, dest, src_root, todos)
    made["agents"] = port_agents(inv, dest, todos)
    made["commands"] = stub_commands(inv, dest, todos)
    made["tools"] = stub_tools(inv, dest, todos)
    made["hooks"] = stub_hooks(inv, dest, plugin_id, todos)
    made["mcp"] = stub_mcp(inv, dest, todos)
    made["ui"] = stub_ui(inv, dest, plugin_id, todos)

    # 兜底：没有被任何通道接走的 stub 必须显式进报告，不能静默消失。
    # 静默丢弃是这类迁移最危险的失败模式——它让「搬完了」看起来成立。
    handled_targets = {"commands", "tools", "hooks", "mcp"}
    for r in inv.get("patch_rows", []):
        if r.get("verdict") != "stub":
            continue
        if r.get("target") in handled_targets:
            continue
        todos.append({
            "kind": f"unmapped:{r.get('target')}",
            "target": "（无产物）",
            "why": f"建议落 {r.get('target')}，但该通道暂无自动搬运路径",
            "action": "人工判定：改写为其他通道，或确认源能力在 DriFox 无等价物后跳过",
        })

    comps = {
        "commands": bool(made["commands"]),
        "agents": bool(made["agents"]),
        "skills": bool(made["skills"]),
        "tools": bool(made["tools"]),
        "hooks": bool(made["hooks"]),
        "mcp": bool(made["mcp"]),
        "ui": bool(made["ui"]),
    }
    if not any(comps.values()):
        comps["skills"] = True
        write_text(dest / "skills" / "placeholder" / "SKILL.md", """---
name: placeholder
description: TODO: 源包无可自动搬运的能力单元，本占位 skill 仅用于让插件结构合法；人工补全后请删除。
---

# 占位

本插件由自动迁移生成，源包未提供可搬运的声明式能力单元。请按 `migration-report.md` 补全或删除本文件。
""")
        todos.append({
            "kind": "plugin",
            "target": plugin_id,
            "why": "源包没有任何可自动搬运的能力单元",
            "action": "人工判定该包是否值得迁移；若不值得，删除本目录",
        })
        made["skills"] = ["placeholder"]

    description = args.description or f"由 dsh 插件 {pkg_short(src_pkg)} 自动迁移生成的 DriFox 插件（含待补项，见 migration-report.md）。"
    write_text(dest / ".drifox-plugin" / "plugin.json",
               json.dumps(build_manifest(plugin_id, description, comps), ensure_ascii=False, indent=4) + "\n")
    write_text(dest / "__init__.py", "")
    write_text(dest / "README.md", f"""# {plugin_id}

> 由 `dsh-plugin-migrator` 从 `{src_pkg}` 自动生成。**含待补项**，完整清单见 [`migration-report.md`](migration-report.md)。

{description}

## 来源

- 源包：`{src_pkg}` @ `{(inv.get('package') or {}).get('version')}`
- 许可证：`{(inv.get('package') or {}).get('license') or '未声明'}`

## 状态

未完成自动搬运的部分以 `MIGRATION_TODO` 标记。在这些标记处理完之前，本插件不应声称功能等价。
""")
    write_text(dest / "migration-report.md", build_report(inv, plugin_id, made, todos, skipped))

    print(f"已生成 {dest}")
    for k, v in made.items():
        if v:
            print(f"  {k}: {len(v)}")
    print(f"  MIGRATION_TODO: {len(todos)}；skip: {len(skipped)}")
    if todos:
        print("下一步：处理 migration-report.md 中的 TODO，然后运行 validate_plugins.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
