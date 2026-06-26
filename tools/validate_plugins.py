#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_plugins.py — 校验 plugins/* 下所有插件的 manifest 和组件完整性

用法:
    python tools/validate_plugins.py
    python tools/validate_plugins.py --strict
    python tools/validate_plugins.py plugins/evolver

退出码:
    0 — 全部通过
    1 — 至少一个插件校验失败
    2 — 致命错误（如 schema 文件缺失）
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ============================================================
# 路径定位
# ============================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "plugin.schema.json"
PLUGINS_DIR = REPO_ROOT / "plugins"
MARKETPLACE_PATH = REPO_ROOT / "marketplace.json"
MANIFEST_PATH = Path(".drifox-plugin") / "plugin.json"

SUPPORTED_EVENTS = {
    "SessionStart",
    "Stop",
    "UserPromptSubmit",
    "PreUserMessage",
    "PostUserMessage",
    "PreAssistantMessage",
    "PostAssistantMessage",
    "PreToolUse",
    "PostToolUse",
}

VALID_COMMAND_TYPES = {"prompt", "function", "agent"}
VALID_AGENT_MODES = {"all", "subagent", "primary"}

# ============================================================
# 输出样式
# ============================================================

_IS_TTY = sys.stdout.isatty()


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if _IS_TTY else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _IS_TTY else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _IS_TTY else s


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _IS_TTY else s


# ============================================================
# 报告数据结构
# ============================================================


@dataclass
class CheckResult:
    plugin: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ============================================================
# Schema 加载
# ============================================================


def load_schema() -> dict | None:
    if not SCHEMA_PATH.exists():
        return None
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def has_jsonschema() -> bool:
    try:
        import jsonschema  # noqa: F401

        return True
    except ImportError:
        return False


# ============================================================
# 基础校验（不依赖 jsonschema 库）
# ============================================================


def basic_manifest_check(manifest: dict) -> list[str]:
    errors: list[str] = []

    for key in ("name", "description", "version", "components"):
        if key not in manifest:
            errors.append(f"缺少必填字段: {key}")

    if not errors:
        name = manifest["name"]
        if not re.match(r"^[a-z][a-z0-9-]{1,63}$", name):
            errors.append(f"name 不符合 kebab-case 规则: {name!r}")

        if not re.match(
            r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
            r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
            r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
            r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$",
            manifest["version"],
        ):
            errors.append(f"version 不是合法 SemVer: {manifest['version']!r}")

        if not (1 <= len(manifest["description"]) <= 200):
            errors.append(
                f"description 长度需在 1-200 之间，当前 {len(manifest['description'])}"
            )

        comps = manifest.get("components", {})
        valid_comps = {"commands", "agents", "skills", "themes", "hooks", "mcp", "lsp"}
        extra = set(comps) - valid_comps
        if extra:
            errors.append(f"components 包含未知键: {sorted(extra)}")
        if not any(comps.get(k) for k in valid_comps):
            errors.append("components 中至少需要启用一个组件")

    return errors


# ============================================================
# 完整 Schema 校验
# ============================================================


def schema_validate(manifest: dict) -> list[str]:
    schema = load_schema()
    if schema is None:
        return ["schemas/plugin.schema.json 不存在"]

    if not has_jsonschema():
        return ["未安装 jsonschema（pip install jsonschema）"]

    import jsonschema

    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in validator.iter_errors(manifest)
    ]


# ============================================================
# YAML frontmatter 解析（极简，支持本仓库用到的子集）
# ============================================================


def _parse_frontmatter(content: str) -> tuple[dict, list[str]]:
    """解析文件开头的 --- 包围的 YAML frontmatter。

    返回 (parsed_dict, warnings)。当遇到不识别的结构时返回 warnings 但不中断。
    """
    warnings: list[str] = []
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("不是 frontmatter 格式")

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError("frontmatter 未闭合")

    body = lines[1:end_idx]
    result, _ = _parse_block(body, 0)
    if not isinstance(result, dict):
        warnings.append("frontmatter 顶层必须是 mapping")
        return {}, warnings
    return result, warnings


def _parse_block(lines: list[str], indent: int) -> tuple[Any, int]:
    """解析一个缩进块，自动判断是 mapping 还是 sequence。"""
    # 找第一个非空非注释行
    first = next(
        (l for l in lines if l.strip() and not l.strip().startswith("#")), None
    )
    if first is None:
        return None, len(lines)

    first_indent = len(first) - len(first.lstrip())
    first_stripped = first.lstrip()

    if first_stripped.startswith("- "):
        return _parse_list(lines, first_indent)
    return _parse_mapping(lines, first_indent)


def _parse_mapping(lines: list[str], indent: int) -> tuple[dict, int]:
    result: dict = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue

        line_indent = len(line) - len(line.lstrip())
        if line_indent < indent:
            break
        if line_indent > indent:
            i += 1
            continue

        stripped = line.strip()
        if ":" not in stripped:
            i += 1
            continue

        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()

        if not rest:
            # 子块：自动判断类型
            sub_lines = lines[i + 1 :]
            sub_value, sub_consumed = _parse_block(sub_lines, indent + 2)
            result[key] = sub_value
            i += 1 + sub_consumed
        else:
            result[key] = _parse_scalar(rest)
            i += 1

    return result, i


def _parse_list(lines: list[str], indent: int) -> tuple[list, int]:
    """解析 list，可包含 string 元素或 dict 元素。"""
    result: list = []
    i = 0
    item_first_indent: int | None = None
    item_lines: list[str] = []
    item_indent: int | None = None

    def flush():
        nonlocal item_lines
        if not item_lines:
            return
        if item_first_indent is not None and item_lines[0].lstrip().startswith("- "):
            first_content = item_lines[0].lstrip()[2:]
            if first_content.strip():
                wrapped = [" " * ((item_first_indent or 0) + 2) + first_content] + item_lines[1:]
                value, _ = _parse_block(wrapped, (item_first_indent or 0) + 2)
                result.append(value)
            else:
                value, _ = _parse_block(item_lines[1:], (item_first_indent or 0) + 2)
                result.append(value)
        else:
            value, _ = _parse_block(item_lines, (item_indent or indent) + 2)
            result.append(value)
        item_lines = []

    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue

        line_indent = len(line) - len(line.lstrip())
        if line_indent < indent:
            break

        stripped = line.lstrip()
        if stripped.startswith("- "):
            flush()
            item_first_indent = line_indent
            item_indent = line_indent + 2
            item_lines = [line]
        else:
            if item_lines:
                item_lines.append(line)
            else:
                # 孤立行（在 - 之前），跳过
                pass
        i += 1

    flush()
    return result, i


def _parse_scalar(s: str) -> Any:
    s = s.strip()
    if not s:
        return ""
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [
            _parse_scalar(p.strip())
            for p in _split_top_level_commas(inner)
            if p.strip()
        ]
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    if s.lower() in ("null", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _split_top_level_commas(s: str) -> list[str]:
    """在顶层逗号处分割字符串（忽略引号内和括号内的逗号）。"""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_str: str | None = None
    for ch in s:
        if in_str:
            buf.append(ch)
            if ch == in_str and (not buf or buf[-2] != "\\"):
                in_str = None
        elif ch in ('"', "'"):
            in_str = ch
            buf.append(ch)
        elif ch in "[(":
            depth += 1
            buf.append(ch)
        elif ch in "])":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


# ============================================================
# 组件完整性检查
# ============================================================


def check_commands_dir(
    plugin_dir: Path, manifest: dict, errors: list[str], warnings: list[str]
) -> None:
    if not manifest.get("components", {}).get("commands"):
        return

    commands_dir = plugin_dir / "commands"
    if not commands_dir.exists():
        errors.append("components.commands=true 但 commands/ 目录不存在")
        return

    md_files = sorted(commands_dir.glob("*.md"))
    if not md_files:
        errors.append("components.commands=true 但 commands/ 下没有 .md 文件")
        return

    for md in md_files:
        if not re.match(r"^[a-z][a-z0-9-]*\.md$", md.name):
            errors.append(f"命令文件名不符合 kebab-case: {md.name}")

        content = md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            errors.append(f"{md.name} 缺少 frontmatter（必须以 --- 开头）")
            continue

        try:
            fm, fm_warnings = _parse_frontmatter(content)
        except ValueError as e:
            errors.append(f"{md.name} frontmatter 解析失败: {e}")
            continue
        warnings.extend(f"{md.name}: {w}" for w in fm_warnings)

        if "description" not in fm:
            errors.append(f"{md.name} frontmatter 缺少 description")
        if "type" not in fm:
            errors.append(f"{md.name} frontmatter 缺少 type")
        elif fm["type"] not in VALID_COMMAND_TYPES:
            errors.append(
                f"{md.name} type 必须是 {sorted(VALID_COMMAND_TYPES)} 之一，"
                f"当前 {fm['type']!r}"
            )

        # mutex_groups 与 prompt_sections 一致性
        mg = fm.get("mutex_groups")
        ps = fm.get("prompt_sections")
        if mg and ps:
            if not isinstance(mg, dict):
                errors.append(f"{md.name} mutex_groups 必须是 dict")
            elif not isinstance(ps, dict):
                errors.append(f"{md.name} prompt_sections 必须是 dict")
            else:
                for group_name, group_values in mg.items():
                    if not isinstance(group_values, list):
                        errors.append(
                            f"{md.name} mutex_groups.{group_name} 必须是 list"
                        )
                        continue
                    missing = [v for v in group_values if v not in ps]
                    if missing:
                        errors.append(
                            f"{md.name} mutex_groups.{group_name} 中的 {missing} "
                            f"在 prompt_sections 中找不到对应段"
                        )

        # parameters 结构（list of dict）
        params = fm.get("parameters")
        if params is not None:
            if not isinstance(params, list):
                errors.append(f"{md.name} parameters 必须是 list")
            else:
                for idx, p in enumerate(params):
                    if not isinstance(p, dict):
                        errors.append(
                            f"{md.name} parameters[{idx}] 必须是 dict"
                        )
                        continue
                    if "name" not in p:
                        errors.append(f"{md.name} parameters[{idx}] 缺少 name")
                    if "param_type" in p and p["param_type"] not in (
                        "flag",
                        "value",
                        "positional",
                    ):
                        errors.append(
                            f"{md.name} parameters[{idx}].param_type "
                            f"必须是 flag/value/positional"
                        )

                    # value_options 校验：必须是 list，且仅在 value 类型时有效
                    vo = p.get("value_options", p.get("enum"))
                    if vo is not None:
                        if not isinstance(vo, list):
                            errors.append(
                                f"{md.name} parameters[{idx}].value_options "
                                f"必须是 list"
                            )
                        ptype = p.get("param_type", "")
                        if ptype and ptype != "value":
                            warnings.append(
                                f"{md.name} parameters[{idx}].value_options "
                                f"仅在 param_type=value 时有效，当前为 {ptype!r}"
                            )

        # body 中 prompt_sections 段必须存在
        if isinstance(ps, dict):
            body = content.split("---", 2)[-1] if content.count("---") >= 2 else content
            for section_id in ps.values():
                if f"<!-- section:{section_id} -->" not in body:
                    warnings.append(
                        f"{md.name} prompt_sections 引用了 {section_id!r} "
                        f"但正文中未找到对应 <!-- section:{section_id} --> 标记"
                    )


def check_hooks_dir(
    plugin_dir: Path, manifest: dict, errors: list[str], warnings: list[str]
) -> None:
    if not manifest.get("components", {}).get("hooks"):
        return

    hooks_dir = plugin_dir / "hooks"
    if not hooks_dir.exists():
        errors.append("components.hooks=true 但 hooks/ 目录不存在")
        return

    hooks_json = hooks_dir / "hooks.json"
    if not hooks_json.exists():
        errors.append("hooks/hooks.json 不存在")
        return

    try:
        hooks_cfg = json.loads(hooks_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"hooks/hooks.json 不是合法 JSON: {e}")
        return

    if "hooks" not in hooks_cfg or not isinstance(hooks_cfg["hooks"], dict):
        errors.append("hooks/hooks.json 缺少 hooks 字典")
        return

    referenced_modules: set[str] = set()

    for event_name, event_configs in hooks_cfg["hooks"].items():
        if event_name not in SUPPORTED_EVENTS:
            warnings.append(f"hooks/hooks.json 引用了未支持的事件: {event_name}")

        if not isinstance(event_configs, list):
            errors.append(f"hooks/hooks.json 事件 {event_name} 的值必须是 list")
            continue

        for event_config in event_configs:
            for hook in event_config.get("hooks", []):
                if hook.get("type") != "python":
                    errors.append(
                        f"事件 {event_name} 上的钩子 type 必须是 python，"
                        f"当前 {hook.get('type')!r}"
                    )
                    continue

                func_ref = hook.get("function", "")
                if ":" not in func_ref:
                    errors.append(
                        f"事件 {event_name} 上的钩子 function 必须为 "
                        f"'module:func' 形式: {func_ref!r}"
                    )
                    continue

                mod_name, func_name = func_ref.split(":", 1)
                if not mod_name.startswith("."):
                    warnings.append(
                        f"事件 {event_name} 上的钩子 function {func_ref!r} "
                        f"的 module 应以 . 开头"
                    )

                referenced_modules.add(mod_name.lstrip("."))

    for mod_name in referenced_modules:
        py_path = hooks_dir / f"{mod_name}.py"
        if not py_path.exists():
            errors.append(f"被引用的钩子模块不存在: hooks/{mod_name}.py")
            continue

        try:
            ast.parse(py_path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            errors.append(f"hooks/{mod_name}.py 语法错误: {e}")


def check_skills_dir(
    plugin_dir: Path, manifest: dict, errors: list[str], warnings: list[str]
) -> None:
    if not manifest.get("components", {}).get("skills"):
        return

    skills_dir = plugin_dir / "skills"
    if not skills_dir.exists():
        errors.append("components.skills=true 但 skills/ 目录不存在")
        return

    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
    if not skill_dirs:
        errors.append("components.skills=true 但 skills/ 下没有技能目录")
        return

    for sd in skill_dirs:
        skill_md = sd / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"技能 {sd.name} 缺少 SKILL.md")
            continue

        content = skill_md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            errors.append(f"skills/{sd.name}/SKILL.md 缺少 frontmatter")
            continue

        try:
            fm, _ = _parse_frontmatter(content)
        except ValueError as e:
            errors.append(f"skills/{sd.name}/SKILL.md frontmatter 解析失败: {e}")
            continue

        if "name" not in fm:
            errors.append(f"skills/{sd.name}/SKILL.md 缺少 name")
        elif fm["name"] != sd.name:
            errors.append(
                f"skills/{sd.name}/SKILL.md 的 name {fm['name']!r} 与目录名不一致"
            )

        if "description" not in fm:
            errors.append(f"skills/{sd.name}/SKILL.md 缺少 description")
        else:
            desc = fm["description"]
            if isinstance(desc, str) and len(desc) < 20:
                warnings.append(
                    f"skills/{sd.name}/SKILL.md description 过短"
                    f"（{len(desc)} 字符），AI 可能无法正确识别触发场景"
                )


def check_agents_dir(
    plugin_dir: Path, manifest: dict, errors: list[str], warnings: list[str]
) -> None:
    if not manifest.get("components", {}).get("agents"):
        return

    agents_dir = plugin_dir / "agents"
    if not agents_dir.exists():
        errors.append("components.agents=true 但 agents/ 目录不存在")
        return

    md_files = sorted(agents_dir.glob("*.md"))
    if not md_files:
        errors.append("components.agents=true 但 agents/ 下没有 .md 文件")
        return

    for md in md_files:
        content = md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            errors.append(f"agents/{md.name} 缺少 frontmatter")
            continue

        try:
            fm, _ = _parse_frontmatter(content)
        except ValueError as e:
            errors.append(f"agents/{md.name} frontmatter 解析失败: {e}")
            continue

        if "description" not in fm:
            errors.append(f"agents/{md.name} 缺少 description")

        mode = fm.get("mode")
        if mode is not None and mode not in VALID_AGENT_MODES:
            errors.append(
                f"agents/{md.name} mode 必须是 {sorted(VALID_AGENT_MODES)} 之一，"
                f"当前 {mode!r}"
            )

        steps = fm.get("steps")
        if steps is not None and not isinstance(steps, int):
            errors.append(f"agents/{md.name} steps 必须是整数")


def check_themes_dir(
    plugin_dir: Path, manifest: dict, errors: list[str], warnings: list[str]
) -> None:
    if not manifest.get("components", {}).get("themes"):
        return

    themes_dir = plugin_dir / "themes"
    if not themes_dir.exists():
        errors.append("components.themes=true 但 themes/ 目录不存在")
        return

    theme_dirs = [d for d in themes_dir.iterdir() if d.is_dir()]
    if not theme_dirs:
        errors.append("components.themes=true 但 themes/ 下没有主题目录")
        return

    for td in theme_dirs:
        # 找 yaml 文件（约定是 td.name/td.name.yaml 或任意 *.yaml）
        yaml_files = list(td.glob("*.yaml")) + list(td.glob("*.yml"))
        if not yaml_files:
            errors.append(f"主题 {td.name} 目录下没有 .yaml 文件")
            continue

        for yf in yaml_files:
            try:
                content = yf.read_text(encoding="utf-8")
                if not content.strip():
                    errors.append(f"themes/{td.name}/{yf.name} 是空文件")
            except OSError as e:
                errors.append(f"themes/{td.name}/{yf.name} 读取失败: {e}")


def check_mcp_file(
    plugin_dir: Path, manifest: dict, errors: list[str], warnings: list[str]
) -> None:
    if not manifest.get("components", {}).get("mcp"):
        return

    mcp_file = plugin_dir / ".mcp.json"
    if not mcp_file.exists():
        errors.append("components.mcp=true 但 .mcp.json 不存在")
        return

    try:
        cfg = json.loads(mcp_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f".mcp.json 不是合法 JSON: {e}")
        return

    servers = cfg.get("mcpServers")
    if not isinstance(servers, dict):
        errors.append(".mcp.json 缺少 mcpServers 字典")
        return

    for name, server in servers.items():
        if not isinstance(server, dict):
            errors.append(f".mcp.json mcpServers.{name} 必须是对象")
            continue
        if "command" not in server and "url" not in server:
            warnings.append(
                f".mcp.json mcpServers.{name} 缺少 command 或 url 字段"
            )


def check_lsp_file(
    plugin_dir: Path, manifest: dict, errors: list[str], warnings: list[str]
) -> None:
    if not manifest.get("components", {}).get("lsp"):
        return

    lsp_file = plugin_dir / ".lsp.json"
    if not lsp_file.exists():
        errors.append("components.lsp=true 但 .lsp.json 不存在")
        return

    try:
        cfg = json.loads(lsp_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f".lsp.json 不是合法 JSON: {e}")
        return

    if not isinstance(cfg, dict) or not cfg:
        errors.append(".lsp.json 必须是包含至少一个语言服务器的对象")
        return

    for name, server in cfg.items():
        if not isinstance(server, dict):
            errors.append(f".lsp.json.{name} 必须是对象")
            continue
        if "command" not in server:
            errors.append(f".lsp.json.{name} 缺少 command 字段")


def check_consistency(
    plugin_dir: Path, manifest: dict, errors: list[str], warnings: list[str]
) -> None:
    if manifest.get("name") and manifest["name"] != plugin_dir.name:
        errors.append(
            f"plugin.json name={manifest['name']!r} 与目录名 {plugin_dir.name!r} 不一致"
        )

    if not (plugin_dir / "README.md").exists():
        warnings.append("缺少 README.md")

    if not (plugin_dir / "__init__.py").exists():
        warnings.append("缺少 __init__.py（影响钩子模块导入）")


def check_dependencies(
    plugin_dir: Path, manifest: dict, errors: list[str], warnings: list[str]
) -> None:
    """校验 dependencies 中引用的插件名是否存在于 plugins/ 目录。"""
    deps = manifest.get("dependencies")
    if not deps or not isinstance(deps, dict):
        return

    available = {
        d.name for d in PLUGINS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")
    } if PLUGINS_DIR.exists() else set()

    for dep_name in deps:
        if dep_name not in available:
            errors.append(f"dependencies 引用的插件不存在: {dep_name}")


def check_marketplace_consistency(
    all_plugins: list[Path], errors: list[str], warnings: list[str]
) -> None:
    """校验 marketplace.json 与各 plugin.json 的关键字段是否一致。

    此函数在所有插件校验完成后单独调用，不属于单个插件的校验。
    """
    if not MARKETPLACE_PATH.exists():
        warnings.append("marketplace.json 不存在（运行 generate_marketplace.py 生成）")
        return

    try:
        marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"marketplace.json 不是合法 JSON: {e}")
        return

    mp_plugins = {p.get("name"): p for p in marketplace.get("plugins", [])}
    actual_names = {p.name for p in all_plugins}

    # 检查 marketplace.json 中引用了不存在的插件
    for name in mp_plugins:
        if name not in actual_names:
            errors.append(f"marketplace.json 引用了不存在的插件: {name}")

    # 检查实际插件未收录到 marketplace.json
    for name in actual_names:
        if name not in mp_plugins:
            errors.append(f"插件 {name} 未收录到 marketplace.json（运行 generate_marketplace.py 更新）")

    # 逐插件比对关键字段
    for plugin_dir in all_plugins:
        manifest_path = plugin_dir / MANIFEST_PATH
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        name = manifest.get("name", plugin_dir.name)
        mp_entry = mp_plugins.get(name)
        if mp_entry is None:
            continue

        for field in ("description", "version", "license"):
            if manifest.get(field) and mp_entry.get(field) and manifest[field] != mp_entry[field]:
                errors.append(
                    f"marketplace.json 中 {name} 的 {field} 与 plugin.json 不一致: "
                    f"marketplace={mp_entry[field]!r} vs plugin.json={manifest[field]!r}"
                )

        # components 一致性
        mp_comps = mp_entry.get("components", {})
        pj_comps = manifest.get("components", {})
        for comp in ("commands", "agents", "skills", "themes", "hooks", "mcp", "lsp"):
            if comp in pj_comps and comp in mp_comps:
                if pj_comps[comp] != mp_comps[comp]:
                    errors.append(
                        f"marketplace.json 中 {name} 的 components.{comp} 与 plugin.json 不一致: "
                        f"marketplace={mp_comps[comp]!r} vs plugin.json={pj_comps[comp]!r}"
                    )


# ============================================================
# 主流程
# ============================================================


def validate_one(plugin_dir: Path) -> CheckResult:
    result = CheckResult(plugin=plugin_dir.name, ok=True)
    manifest_path = plugin_dir / MANIFEST_PATH

    if not manifest_path.exists():
        result.ok = False
        result.errors.append(f"缺少 manifest: {MANIFEST_PATH.as_posix()}")
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        result.ok = False
        result.errors.append(f"plugin.json 不是合法 JSON: {e}")
        return result

    schema_errors = schema_validate(manifest)
    if schema_errors:
        if any("未安装 jsonschema" in e for e in schema_errors):
            result.warnings.extend(schema_errors)
            basic_errors = basic_manifest_check(manifest)
            if basic_errors:
                result.ok = False
                result.errors.extend(basic_errors)
        else:
            result.ok = False
            result.errors.extend(schema_errors)

    check_consistency(plugin_dir, manifest, result.errors, result.warnings)
    check_dependencies(plugin_dir, manifest, result.errors, result.warnings)
    check_commands_dir(plugin_dir, manifest, result.errors, result.warnings)
    check_hooks_dir(plugin_dir, manifest, result.errors, result.warnings)
    check_skills_dir(plugin_dir, manifest, result.errors, result.warnings)
    check_agents_dir(plugin_dir, manifest, result.errors, result.warnings)
    check_themes_dir(plugin_dir, manifest, result.errors, result.warnings)
    check_mcp_file(plugin_dir, manifest, result.errors, result.warnings)
    check_lsp_file(plugin_dir, manifest, result.errors, result.warnings)

    if result.errors:
        result.ok = False

    return result


def discover_plugins(targets: list[Path] | None = None) -> list[Path]:
    if targets:
        return [t for t in targets if t.is_dir()]

    if not PLUGINS_DIR.exists():
        return []

    return sorted(
        d for d in PLUGINS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def print_result(r: CheckResult) -> None:
    if r.ok and not r.warnings:
        print(f"  {_green('OK')}   {r.plugin}")
        return

    if r.ok:
        print(f"  {_yellow('WARN')} {r.plugin}")
    else:
        print(f"  {_red('FAIL')} {r.plugin}")

    for w in r.warnings:
        print(f"        {_yellow('warn')}: {w}")
    for e in r.errors:
        print(f"        {_red('err')}: {e}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 drifox-plugins 仓库中所有插件的 manifest 与组件完整性"
    )
    parser.add_argument(
        "targets",
        nargs="*",
        type=Path,
        help="指定要校验的插件目录（相对或绝对路径），省略则校验 plugins/* 下所有",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="把 warning 当作 error 处理",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    print(_bold("DriFox plugin validator"))
    print(f"  repo:   {REPO_ROOT}")
    print(
        f"  schema: {SCHEMA_PATH.relative_to(REPO_ROOT) if SCHEMA_PATH.exists() else '(missing)'}"
    )
    if not has_jsonschema():
        print(
            f"  {_yellow('注意')}: 未安装 jsonschema 库，仅做基础校验（pip install jsonschema）"
        )
    print()

    targets = discover_plugins(args.targets or None)
    if not targets:
        print(_yellow("未发现任何插件目录。"))
        return 0

    results = [validate_one(p) for p in targets]

    # 全局校验：marketplace.json 与所有插件的一致性（不限制 targets）
    marketplace_errors: list[str] = []
    marketplace_warnings: list[str] = []
    all_plugins_in_repo = discover_plugins(None)
    check_marketplace_consistency(all_plugins_in_repo, marketplace_errors, marketplace_warnings)
    if marketplace_errors or marketplace_warnings:
        mp_result = CheckResult(plugin="marketplace.json", ok=not marketplace_errors)
        mp_result.errors = marketplace_errors
        mp_result.warnings = marketplace_warnings
        results.append(mp_result)

    print(_bold("结果："))
    for r in results:
        print_result(r)
    print()

    ok_count = sum(
        1 for r in results if r.ok and not (args.strict and r.warnings)
    )
    fail_count = len(results) - ok_count

    if fail_count == 0:
        print(_green(f"✓ 全部 {len(results)} 个插件通过校验"))
        return 0
    else:
        print(_red(f"✗ {fail_count}/{len(results)} 个插件校验失败"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
