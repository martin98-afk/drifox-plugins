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
import shutil
import subprocess
import tempfile
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
    "model_adapters", "loop_policies", "storages", "serializers", "gateways", "engines",
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

    if comps.get("themes"):
        d = base / "themes"
        if not d.is_dir():
            errors.append("components.themes=true 但 themes/ 不存在")
        else:
            # 真实结构：themes/<theme-id>/<theme-id>.yaml（对齐 laputa-fog/fe-fw）
            yamls = sorted(d.glob("*/*.yaml"))
            if not yamls:
                errors.append("components.themes=true 但 themes/<id>/ 下无 .yaml（结构应为 themes/<id>/<id>.yaml）")
            for y in yamls:
                rel = f"themes/{y.parent.name}/{y.name}"
                if y.stem != y.parent.name:
                    warnings.append(f"{rel} 文件名与所在目录名不一致（惯例要求同名）")
                text = y.read_text(encoding="utf-8")
                for field in ("id:", "mode:", "colors:"):
                    if field not in text:
                        errors.append(f"{rel} 缺关键字段 {field.rstrip(':')}")
                if "TODO" in text:
                    warnings.append(f"{rel} 仍含 TODO 标记（骨架未填充）")

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
        else:
            import re as _re
            for y in yamls:
                text = y.read_text(encoding="utf-8")
                if "schema_version:" not in text or "template_name:" not in text:
                    errors.append(f"team_templates/{y.name} 缺 schema_version/template_name")
                if "agents:" not in text:
                    errors.append(f"team_templates/{y.name} 缺 agents 列表")

    # 运行时组件（与 tools/providers 对称：目录 + *.py + register 入口）
    for kind in ("model_adapters", "loop_policies", "storages", "serializers", "gateways", "engines"):
        if comps.get(kind):
            d = base / kind
            if not d.is_dir():
                errors.append(f"components.{kind}=true 但 {kind}/ 不存在")
            else:
                pys = [p for p in sorted(d.glob("*.py")) if not p.name.startswith("_")]
                if not pys:
                    errors.append(f"components.{kind}=true 但 {kind}/ 无 .py 文件")
                for py in pys:
                    _check_register_entry(py, f"{kind}/{py.name}", "register", errors)

    return errors, warnings


# ---------- deep 层：隔离子进程实跑 tools（Harbor 等价物） ----------
# 设计要点：绝不污染主进程 sys.modules / 绝不写入任何 tools/ 目录。
# 复制 tools/*.py 到临时目录 → 系统 Python 子进程内注入 app 轻量垫片 +
# MockRegistry → 加载每个工具 register() → 按 schema.required 构造最小 kwargs
# 调 impl(tool_ctx) → json 输出结果。主进程解析汇总。


def _python_exe() -> list[str]:
    """定位系统 Python 解释器（返回参数列表前段）。

    DriFox 是 PyInstaller 打包，主进程内 sys.executable == Drifox.exe，
    直接 [sys.executable, ...] 会启动主程序新实例。必须用系统 Python。
    """
    for cand in ("python.exe", "python", "python3.exe", "python3"):
        p = shutil.which(cand)
        if p and "WindowsApps" not in p:
            return [p]
    py = shutil.which("py.exe") or shutil.which("py")
    if py:
        return [py, "-3"]
    raise RuntimeError(
        "找不到系统 Python 解释器（python.exe 或 py.exe）。"
        "deep 验证需要系统 Python 实跑工具，请安装 Python 3 并加入 PATH。"
    )


# 子进程内执行的 runner 源码（仅用标准库，注入 app 轻量垫片，绝不回写主进程）
_DEEP_RUNNER = r'''
import sys, json, types, importlib.util
from pathlib import Path


class ToolResult:
    def __init__(self, success, content=None, error=None):
        self.success = success
        self.content = content
        self.error = error


_app = types.ModuleType("app")
_tools = types.ModuleType("app.tools")
_res = types.ModuleType("app.tools.result")
_res.ToolResult = ToolResult
_app.tools = _tools
_tools.result = _res
sys.modules["app"] = _app
sys.modules["app.tools"] = _tools
sys.modules["app.tools.result"] = _res


class MockRegistry:
    def __init__(self):
        self.tools = []

    def register(self, name, schema, impl=None, **kw):
        self.tools.append((name, schema, impl, None))


def main():
    tools_dir = Path(sys.argv[1])
    reg = MockRegistry()
    for py in sorted(tools_dir.glob("*.py")):
        if py.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location("bench_" + py.stem, py)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            reg.tools.append((py.stem, None, None, "加载失败: %s: %s" % (type(e).__name__, e)))
            continue
        if not hasattr(mod, "register"):
            reg.tools.append((py.stem, None, None, "缺少顶层 register(registry)"))
            continue
        try:
            mod.register(reg)
        except Exception as e:
            reg.tools.append((py.stem, None, None, "register 抛异常: %s: %s" % (type(e).__name__, e)))
    results = []
    tool_ctx = {"workdir": str(tools_dir), "env": {"app_data_dir": str(tools_dir)}, "services": {}}
    for name, schema, impl, load_err in reg.tools:
        entry = {"name": name, "register": "ok", "call": "ok", "error": None}
        if load_err is not None:
            entry["register"] = "fail"
            entry["error"] = load_err
        elif impl is None:
            entry["register"] = "fail"
            entry["error"] = "register 未提供 impl"
        else:
            try:
                params = (schema or {}).get("function", {}).get("parameters", {}) or {}
                props = params.get("properties", {}) or {}
                required = params.get("required", []) or []
                kwargs = {k: "" if props.get(k, {}).get("type") == "string" else None for k in required}
                out = impl(tool_ctx, **kwargs)
                if not (hasattr(out, "success") and hasattr(out, "content")):
                    entry["call"] = "fail"
                    entry["error"] = "impl 返回非 ToolResult 实例"
            except Exception as e:
                entry["call"] = "fail"
                entry["error"] = "%s: %s" % (type(e).__name__, e)
        results.append(entry)
    print(json.dumps(results, ensure_ascii=False))


main()
'''


def _run_deep_tools(base: Path, plugin_name: str) -> tuple[list, list]:
    """deep 层：隔离子进程实跑 tools 的 register+impl（Harbor 等价物）。

    返回 (runtime_errors, runtime_lines)。绝不污染主进程 sys.modules。
    任何异常都降级为非阻断警告（deep 是增强验证，不应阻断主流程）。
    """
    tools_dir = base / "tools"
    if not tools_dir.is_dir():
        return [], ["（无 tools 组件，跳过运行时验证）"]
    try:
        py = _python_exe()
    except RuntimeError as e:
        return [], [f"⚠ 跳过运行时验证（{e}）"]
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "plugin" / "tools"
        dst.mkdir(parents=True)
        for f in tools_dir.glob("*.py"):
            if f.name.startswith("_"):
                continue
            shutil.copy(f, dst / f.name)
        runner = Path(td) / "__deep_runner__.py"
        runner.write_text(_DEEP_RUNNER, encoding="utf-8")
        try:
            r = subprocess.run(
                py + [str(runner), str(dst)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return [], ["⚠ 运行时验证超时（>120s），跳过"]
        if r.returncode != 0:
            return [], [f"⚠ 运行时验证子进程异常：{(r.stderr or '')[:500]}"]
        try:
            results = json.loads(r.stdout.strip() or "[]")
        except json.JSONDecodeError:
            return [], [f"⚠ 运行时验证输出解析失败：{(r.stdout or '')[:300]}"]
    errors, lines = [], ["运行时验证（deep=true，隔离进程实跑 tools）："]
    for it in results:
        name = it.get("name", "?")
        if it.get("register") != "ok":
            errors.append(f"runtime: {name} register 失败 → {it.get('error')}")
            lines.append(f"  ✗ {name}: register 失败 → {it.get('error')}")
        elif it.get("call") != "ok":
            errors.append(f"runtime: {name} impl 抛异常 → {it.get('error')}")
            lines.append(f"  ✗ {name}: impl 异常 → {it.get('error')}")
        else:
            lines.append(f"  ✅ {name}: register OK / impl OK")
    return errors, lines


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

        # deep 层：静态通过后启隔离子进程实跑 tools（Harbor 等价物）
        deep = bool(kwargs.get("deep"))
        runtime_errors, runtime_lines = [], []
        if deep and not errors:
            runtime_errors, runtime_lines = _run_deep_tools(base, plugin_name)
            errors.extend(runtime_errors)
        elif not deep and manifest.get("components", {}).get("tools"):
            runtime_lines = [
                "提示：检测到 tools 组件，结构 OK 但运行时未验证 → 加 deep=true 实跑确认 impl 不崩",
            ]

        lines = [f"插件 {plugin_name} 校验{'✅ 通过' if not errors else '❌ 未通过'}（{base}）", ""]
        if errors:
            lines.append("错误：")
            lines += [f"  ✗ {e}" for e in errors]
        if warnings:
            lines.append("警告：")
            lines += [f"  ⚠ {w}" for w in warnings]
        if not errors and not warnings:
            lines.append("无错误无警告。")
        if runtime_lines:
            lines.append("")
            lines += runtime_lines
        if not errors:
            lines.append("")
            lines.append("提示：修改后 watchfiles 热重载自动生效（hooks/mcp/lsp 通常自动重连；如未生效再重启 DriFox）。")
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
                "deep": {
                    "type": "boolean",
                    "description": (
                        "true 时静态校验通过后，额外启隔离子进程实跑 tools 的 register+impl"
                        "（Harbor 等价物：验证不抛异常且返回合法 ToolResult）。"
                        "默认 false（仅静态结构校验，毫秒级、零执行）。改了工具逻辑或发布前建议 true。"
                    ),
                    "default": False,
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
