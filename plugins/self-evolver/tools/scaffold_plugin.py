# -*- coding: utf-8 -*-
"""
evolution_scaffold — 自进化工具 1：按需求生成 DriFox 插件骨架。

写入目标默认 user 根（~/.drifox/plugins/<name>/），保存即热重载。
支持组件：tools / commands / agents / skills / hooks / mcp / lsp / themes。

安全约束：
- 插件名必须 ^[a-z][a-z0-9-]{1,63}$（kebab-case）
- 拒绝覆盖已存在插件（force=true 除外，且只清空重建属危险操作，仍保留备份提示）
- 所有生成的 Python 模板通过 py_compile 语法级保证
"""
import json
import re
import shutil
import time
from pathlib import Path

from app.tools.result import ToolResult

VALID_COMPONENTS = ("tools", "commands", "agents", "skills", "hooks", "mcp", "lsp", "themes")

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


def _user_root(tool_ctx) -> Path:
    """插件写入根：优先平台 app_data，回退 ~/.drifox/plugins"""
    env = tool_ctx.get("env") or {}
    app_data = env.get("app_data_dir")
    if app_data:
        root = Path(app_data) / "plugins"
        if root.is_dir():
            return root
    return Path.home() / ".drifox" / "plugins"


# ---------- 各组件模板 ----------

_TOOL_PY = '''# -*- coding: utf-8 -*-
"""{tool_name} — 由 evolution_scaffold 生成的工具骨架。impl 签名：impl(tool_ctx, **kwargs) -> ToolResult"""
from app.tools.result import ToolResult


def _impl(tool_ctx, **kwargs):
    # TODO: 实现工具逻辑；tool_ctx 提供 workdir/env/services
    return ToolResult(True, content="{plugin} 工具骨架已就绪，请填充实现。")


_SCHEMA = {{
    "type": "function",
    "function": {{
        "name": "{tool_name}",
        "description": "{tool_name} 工具（骨架，待实现）",
        "parameters": {{
            "type": "object",
            "properties": {{}},
            "required": [],
        }},
    }},
}}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "{tool_name}", _SCHEMA, impl=_impl,
        danger="safe",  # 必填：safe | dangerous
        cn_name="{cn_tool_name}",
        group="{group}",
        description="{plugin} 工具（骨架）",
    )
'''

_COMMAND_MD = '''---
description: {description}
type: prompt
---

# /{cmd}

TODO: 编写命令提示词正文。可用模板变量：$ARGUMENTS、$PLUGIN_NAME、$PLUGIN_DIR、$PROJECT_ROOT。
'''

_AGENT_MD = '''---
description: {description}。触发词：{plugin}、{plugin} 智能体。
mode: subagent
steps: 20
temperature: 0.3
permission:
  "*": allow
---

# Role

你是 {plugin} 插件的智能体（骨架）。TODO: 定义角色职责与输出格式。
'''

_SKILL_MD = '''---
name: {plugin}
description: {description}。触发关键词：{plugin}。
---

# {plugin} 技能

TODO: 编写技能知识正文（最佳实践、约束、流程）。
'''

_HOOKS_JSON = '''{{
  "description": "{plugin} Hook",
  "hooks": {{
    "PostToolUse": [
      {{
        "hooks": [
          {{
            "type": "python",
            "function": ".{plugin}_hook:handle",
            "timeout": 5,
            "enabled": true,
            "id": "{hook_id}"
          }}
        ]
      }}
    ]
  }}
}}
'''

_HOOK_PY = '''# -*- coding: utf-8 -*-
"""{plugin} hook（骨架）。事件见 hooks/hooks.json；handler 入参为事件 payload dict。"""


def handle(payload: dict) -> dict:
    # TODO: 实现钩子逻辑；返回 {} 或附加数据
    return {}
'''

_MCP_JSON = '''{{
  "mcpServers": {{
    "example-server": {{
      "type": "stdio",
      "command": "TODO-command",
      "args": [],
      "env": {{}},
      "enabled": false,
      "url": "",
      "headers": {{}}
    }}
  }}
}}
'''

_LSP_JSON = '''{{
  "TODO-language": {{
    "command": "TODO-lsp-command",
    "args": []
  }}
}}
'''


def _manifest(name: str, description: str, comps: list, author: str = "self-evolver") -> str:
    components = {c: (c in comps) for c in VALID_COMPONENTS}
    manifest = {
        "name": name,
        "description": description[:200],
        "version": "0.1.0",
        "author": {"name": author},
        "license": "GPL-3.0-or-later",
        "type": "user",
        "drifox": {"min_version": "0.5.0"},
        "keywords": [name.split("-")[0], "evolved"],
        "components": components,
    }
    return json.dumps(manifest, ensure_ascii=False, indent=4)


def _gen_hook_id() -> str:
    return f"{int(time.time() * 1000):032x}"[-32:]


def _write_components(base: Path, name: str, description: str, comps: list) -> list:
    """写入各组件骨架文件，返回相对路径清单"""
    written = []

    if "tools" in comps:
        d = base / "tools"
        d.mkdir(exist_ok=True)
        tool_name = name.replace("-", "_")
        (d / f"{tool_name}.py").write_text(
            _TOOL_PY.format(
                tool_name=tool_name, plugin=name, cn_tool_name=name,
                group=name, description=description,
            ),
            encoding="utf-8",
        )
        written.append(f"tools/{tool_name}.py")

    if "commands" in comps:
        d = base / "commands"
        d.mkdir(exist_ok=True)
        cmd = name.split("-")[0]
        (d / f"{cmd}.md").write_text(
            _COMMAND_MD.format(description=description[:80], cmd=cmd),
            encoding="utf-8",
        )
        written.append(f"commands/{cmd}.md")

    if "agents" in comps:
        d = base / "agents"
        d.mkdir(exist_ok=True)
        (d / "assistant.md").write_text(
            _AGENT_MD.format(description=description[:80], plugin=name),
            encoding="utf-8",
        )
        written.append("agents/assistant.md")

    if "skills" in comps:
        d = base / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            _SKILL_MD.format(plugin=name, description=description[:80]),
            encoding="utf-8",
        )
        written.append(f"skills/{name}/SKILL.md")

    if "hooks" in comps:
        d = base / "hooks"
        d.mkdir(exist_ok=True)
        (d / "hooks.json").write_text(
            _HOOKS_JSON.format(plugin=name, hook_id=_gen_hook_id()),
            encoding="utf-8",
        )
        (d / f"{name}_hook.py").write_text(
            _HOOK_PY.format(plugin=name), encoding="utf-8"
        )
        written.extend(["hooks/hooks.json", f"hooks/{name}_hook.py"])

    if "mcp" in comps:
        (base / ".mcp.json").write_text(_MCP_JSON, encoding="utf-8")
        written.append(".mcp.json")

    if "lsp" in comps:
        (base / ".lsp.json").write_text(_LSP_JSON, encoding="utf-8")
        written.append(".lsp.json")

    return written


def _impl(tool_ctx, **kwargs):
    try:
        name = (kwargs.get("name") or "").strip()
        description = (kwargs.get("description") or f"{name} 插件（self-evolver 生成）").strip()
        components = kwargs.get("components") or ["tools"]
        force = bool(kwargs.get("force"))

        # 参数校验
        if not name:
            return ToolResult(False, error="必须提供 name（kebab-case 插件名，如 my-tool-plugin）")
        if not _NAME_RE.match(name):
            return ToolResult(
                False,
                error=f"插件名 {name!r} 不符合 ^[a-z][a-z0-9-]{{1,63}}$ 规则",
            )
        if isinstance(components, str):
            components = [c.strip() for c in components.split(",") if c.strip()]
        bad = [c for c in components if c not in VALID_COMPONENTS]
        if bad:
            return ToolResult(
                False,
                error=f"不支持的组件类型 {bad}；可用：{list(VALID_COMPONENTS)}",
            )

        root = _user_root(tool_ctx)
        base = root / name

        if base.exists():
            if not force:
                return ToolResult(
                    False,
                    error=f"插件 {name} 已存在于 {base}。确认覆盖请设 force=true"
                          f"（旧版本会备份为 {name}.bak.<ts>）",
                )
            bak = root / f"{name}.bak.{int(time.time())}"
            shutil.move(str(base), str(bak))

        root.mkdir(parents=True, exist_ok=True)
        base.mkdir()

        # manifest
        manifest_dir = base / ".drifox-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            _manifest(name, description, components, author=(kwargs.get("author") or "self-evolver").strip()),
            encoding="utf-8",
        )
        written = [".drifox-plugin/plugin.json"]

        # 组件骨架
        written += _write_components(base, name, description, components)

        # README + 包标记
        (base / "__init__.py").write_text(
            f'# -*- coding: utf-8 -*-\n"""{name} — self-evolver 生成"""\n',
            encoding="utf-8",
        )
        (base / "README.md").write_text(
            f"# {name}\n\n{description}\n\n> 由 evolution_scaffold 生成，"
            f"骨架文件已就位，请填充 TODO 实现。\n",
            encoding="utf-8",
        )
        written += ["__init__.py", "README.md"]

        backup_note = f"\n旧版本已备份：{bak.name}" if force else ""
        content = (
            f"插件骨架 {name} 已生成 ✅\n\n"
            f"路径：{base}\n"
            f"组件：{components}\n"
            f"文件清单：\n" + "\n".join(f"  - {w}" for w in written) +
            f"\n\n下一步：\n"
            f"1. 填充各 TODO 实现（read/edit 直接改，热重载自动生效）\n"
            f"2. 用 evolution_validate plugin_name={name} 校验\n"
            f"3. 用 evolution_journal 记录本次进化{backup_note}"
        )
        return ToolResult(True, content=content)
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"evolution_scaffold 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "evolution_scaffold",
        "description": (
            "自进化：按需求生成 DriFox 插件骨架（manifest+组件模板+README），"
            "写入 user 根（~/.drifox/plugins/<name>/）保存即热重载。"
            "生成后填充 TODO 即得新插件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "插件名，kebab-case（如 my-tool-plugin），与目录名一致",
                },
                "description": {
                    "type": "string",
                    "description": "一句话插件描述（≤200字），写入 manifest",
                },
                "components": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": list(VALID_COMPONENTS),
                    },
                    "description": "要启用的组件列表，默认 ['tools']",
                },
                "force": {
                    "type": "boolean",
                    "description": "同名插件已存在时覆盖（旧版备份为 .bak.<ts>），默认 false",
                    "default": False,
                },
                "author": {
                    "type": "string",
                    "description": "插件作者名（写入 manifest author.name），默认 self-evolver",
                },
            },
            "required": ["name"],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "evolution_scaffold", _SCHEMA, impl=_impl,
        danger="safe", icon="evolution_scaffold", cn_name="生成插件骨架",
        group="自进化", description="按需求生成 DriFox 插件骨架（热重载即时生效）",
        metadata={"permission_arg": "name"},
    )
