# -*- coding: utf-8 -*-
"""
evolution_validate — 自进化工具 2：校验 DriFox 插件结构合规性。

校验规则与官方 tools/validate_plugins.py 对齐（子集，自包含实现，不依赖仓库）：
- manifest：必填字段 / name kebab-case / version SemVer / description 长度 / components 至少一个
- components flag=true 时对应目录/文件存在
- tools/providers：每个 *.py 能 ast.parse + 有顶层 register()
- ui：__init__.py 能 ast.parse + 有顶层 register_ui()
- hooks：hooks.json 合法 JSON + 引用的 py 文件存在且可编译
- commands：文件名规则 + frontmatter（description+type）
- skills：SKILL.md frontmatter（name+description）
- .mcp.json / .lsp.json：合法 JSON
"""
import ast
import json
import re
from pathlib import Path

from app.tools.result import ToolResult

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
_VALID_COMPS = (
    "commands", "agents", "skills", "themes", "hooks", "mcp", "lsp",
    "ui", "tools", "providers", "team_templates",
)
_CMD_RE = re.compile(r"^[a-z][a-z0-9-]*\.md$")


def _plugin_roots():
    """system 根 + user 根（与主加载器一致）"""
    roots = []
    try:
        from app.plugins.loaders.plugin_tool_loader import _plugin_roots as _lr

        for p in _lr():
            roots.append(Path(p))
    except Exception:
        pass
    if not roots:
        try:
            import app

            app_file = getattr(app, "__file__", None)
            if app_file:
                sys_root = Path(app_file).resolve().parent.parent / "plugins"
                if sys_root.is_dir():
                    roots.append(sys_root)
        except Exception:
            pass
    try:
        from app.utils.utils import get_app_data_dir

        roots.append(Path(get_app_data_dir()) / "plugins")
    except Exception:
        roots.append(Path.home() / ".drifox" / "plugins")
    return [r for r in roots if r.is_dir()]


def _find_plugin(plugin_name: str) -> Path | None:
    for root in _plugin_roots():
        cand = root / plugin_name
        if cand.is_dir():
            return cand
    return None


def _parse_frontmatter(text: str) -> dict | None:
    """极简 frontmatter 解析（只取 key: value 一层）"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None
    result = {}
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, rest = stripped.partition(":")
        result[key.strip()] = rest.strip().strip("'\"")
    return result


def _check_manifest(manifest: dict, errors: list, warnings: list) -> None:
    for key in ("name", "description", "version", "components"):
        if key not in manifest:
            errors.append(f"manifest 缺少必填字段: {key}")
    if errors:
        return
    if not _NAME_RE.match(manifest["name"]):
        errors.append(f"name 不符合 kebab-case: {manifest['name']!r}")
    if not _SEMVER_RE.match(str(manifest["version"])):
        errors.append(f"version 不是合法 SemVer: {manifest['version']!r}")
    if not (1 <= len(manifest["description"]) <= 200):
        errors.append(f"description 长度需 1-200，当前 {len(manifest['description'])}")
    comps = manifest.get("components", {})
    for k in comps:
        if k not in _VALID_COMPS:
            warnings.append(f"components 含未知组件类型: {k}")
    if not any(comps.get(k) for k in _VALID_COMPS):
        errors.append("components 至少需要启用一个组件")


def _check_register_entry(py: Path, fname: str, func_name: str, errors: list) -> None:
    """检查 py 文件能 ast.parse 且含顶层 func_name 函数"""
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except SyntaxError as e:
        errors.append(f"{fname} 语法错误: {e}")
        return
    except OSError as e:
        errors.append(f"{fname} 读取失败: {e}")
        return
    if not any(isinstance(n, ast.FunctionDef) and n.name == func_name for n in tree.body):
        errors.append(f"{fname} 缺少顶层 {func_name}(registry) 函数")


def _check_plugin_dir(base: Path, manifest: dict, name: str) -> tuple[list, list]:
    errors, warnings = [], []
    _check_manifest(manifest, errors, warnings)
    comps = manifest.get("components", {})

    if comps.get("tools"):
        d = base / "tools"
        if not d.is_dir():
            errors.append("components.tools=true 但 tools/ 不存在")
        else:
            pys = [p for p in sorted(d.glob("*.py")) if not p.name.startswith("_")]
            if not pys:
                errors.append("components.tools=true 但 tools/ 无 .py 文件")
            for py in pys:
                _check_register_entry(py, f"tools/{py.name}", "register", errors)

    if comps.get("providers"):
        d = base / "providers"
        if not d.is_dir():
            errors.append("components.providers=true 但 providers/ 不存在")
        else:
            pys = [p for p in sorted(d.glob("*.py")) if not p.name.startswith("_")]
            if not pys:
                errors.append("components.providers=true 但 providers/ 无 .py 文件")
            for py in pys:
                _check_register_entry(py, f"providers/{py.name}", "register", errors)

    if comps.get("commands"):
        d = base / "commands"
        if not d.is_dir():
            errors.append("components.commands=true 但 commands/ 不存在")
        else:
            mds = sorted(d.glob("*.md"))
            if not mds:
                errors.append("components.commands=true 但 commands/ 无 .md 文件")
            for md in mds:
                rel = f"commands/{md.name}"
                if not _CMD_RE.match(md.name):
                    errors.append(f"{rel} 文件名需匹配 ^[a-z][a-z0-9-]*.md$")
                fm = _parse_frontmatter(md.read_text(encoding="utf-8"))
                if fm is None:
                    errors.append(f"{rel} 缺少 frontmatter")
                else:
                    if not fm.get("description"):
                        errors.append(f"{rel} frontmatter 缺 description")
                    if fm.get("type") not in ("prompt", "function", "agent"):
                        errors.append(f"{rel} frontmatter type 需为 prompt/function/agent")

    if comps.get("skills"):
        d = base / "skills"
        if not d.is_dir():
            errors.append("components.skills=true 但 skills/ 不存在")
        else:
            skills = [p for p in sorted(d.rglob("SKILL.md"))]
            if not skills:
                errors.append("components.skills=true 但 skills/ 下无 SKILL.md")
            for sk in skills:
                rel = f"skills/{sk.parent.name}/SKILL.md"
                fm = _parse_frontmatter(sk.read_text(encoding="utf-8"))
                if fm is None:
                    errors.append(f"{rel} 缺少 frontmatter")
                else:
                    if not fm.get("name"):
                        errors.append(f"{rel} frontmatter 缺 name")
                    if not fm.get("description"):
                        errors.append(f"{rel} frontmatter 缺 description")

    if comps.get("agents"):
        d = base / "agents"
        if not d.is_dir() or not list(d.glob("*.md")):
            errors.append("components.agents=true 但 agents/ 无 .md 文件")
        else:
            for md in sorted(d.glob("*.md")):
                fm = _parse_frontmatter(md.read_text(encoding="utf-8"))
                if fm is None or not fm.get("description"):
                    errors.append(f"agents/{md.name} 缺 frontmatter description")

    if comps.get("hooks"):
        hj = base / "hooks" / "hooks.json"
        if not hj.exists():
            errors.append("components.hooks=true 但 hooks/hooks.json 不存在")
        else:
            try:
                cfg = json.loads(hj.read_text(encoding="utf-8"))
                hooks_map = cfg.get("hooks", {})
                for event, groups in hooks_map.items():
                    for grp in groups or []:
                        for h in grp.get("hooks", []):
                            fn = h.get("function", "")
                            # ".<module>:<func>" → hooks/<module>.py
                            if fn.startswith("."):
                                mod = fn.split(":", 1)[0].lstrip(".")
                                py = base / "hooks" / f"{mod}.py"
                                if not py.exists():
                                    errors.append(f"hooks.json 引用的 {py.relative_to(base)} 不存在")
                                else:
                                    try:
                                        ast.parse(py.read_text(encoding="utf-8"))
                                    except SyntaxError as e:
                                        errors.append(f"hooks/{mod}.py 语法错误: {e}")
            except json.JSONDecodeError as e:
                errors.append(f"hooks/hooks.json 不是合法 JSON: {e}")

    if comps.get("mcp"):
        f = base / ".mcp.json"
        if not f.exists():
            errors.append("components.mcp=true 但 .mcp.json 不存在")
        else:
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                errors.append(f".mcp.json 不是合法 JSON: {e}")

    if comps.get("lsp"):
        f = base / ".lsp.json"
        if not f.exists():
            errors.append("components.lsp=true 但 .lsp.json 不存在")
        else:
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                errors.append(f".lsp.json 不是合法 JSON: {e}")

    if comps.get("ui"):
        init = base / "ui" / "__init__.py"
        if not init.exists():
            errors.append("components.ui=true 但 ui/__init__.py 不存在")
        else:
            _check_register_entry(init, "ui/__init__.py", "register_ui", errors)

    if comps.get("team_templates"):
        d = base / "team_templates"
        yamls = sorted(d.glob("*.yaml")) if d.is_dir() else []
        if not yamls:
            errors.append("components.team_templates=true 但 team_templates/ 无 .yaml")

    return errors, warnings


def _impl(tool_ctx, **kwargs):
    try:
        plugin_name = (kwargs.get("plugin_name") or "").strip()
        if not plugin_name:
            return ToolResult(False, error="必须提供 plugin_name")

        base = _find_plugin(plugin_name)
        if base is None:
            return ToolResult(
                False,
                error=f"未找到插件 {plugin_name}（搜索了 system + user 根）",
            )

        mf = base / ".drifox-plugin" / "plugin.json"
        if not mf.exists():
            return ToolResult(False, error=f"{base} 缺少 .drifox-plugin/plugin.json")

        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return ToolResult(False, error=f"plugin.json 不是合法 JSON: {e}")

        if manifest.get("name") != plugin_name:
            return ToolResult(
                False,
                error=f"manifest.name={manifest.get('name')!r} 与目录名 {plugin_name!r} 不一致",
            )

        errors, warnings = _check_plugin_dir(base, manifest, plugin_name)

        lines = [f"插件 {plugin_name} 校验{'✅ 通过' if not errors else '❌ 未通过'}（{base}）", ""]
        if errors:
            lines.append("错误：")
            lines += [f"  ✗ {e}" for e in errors]
        if warnings:
            lines.append("警告：")
            lines += [f"  ⚠ {w}" for w in warnings]
        if not errors and not warnings:
            lines.append("无错误无警告。")
        if not errors:
            lines.append("")
            lines.append("提示：修改后 watchfiles 热重载自动生效（hooks/mcp/lsp 可能需重启 DriFox）。")
        return ToolResult(
            not errors,
            content="\n".join(lines),
            error="\n".join(errors) if errors else None,
        )
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"evolution_validate 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "evolution_validate",
        "description": (
            "自进化：校验指定 DriFox 插件的结构合规性（manifest 字段/组件文件存在性/"
            "register 入口/py 语法/frontmatter/mcp-lsp JSON 合法性）。"
            "规则对齐官方 validate_plugins.py。用于新插件准入或修改后复验。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "要校验的插件名（system+user 根中查找）",
                },
            },
            "required": ["plugin_name"],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "evolution_validate", _SCHEMA, impl=_impl,
        danger="safe", icon="evolution_validate", cn_name="校验插件结构",
        group="自进化", description="校验插件结构合规（对齐官方 validate_plugins 规则）",
        metadata={"permission_arg": "plugin_name"},
    )
