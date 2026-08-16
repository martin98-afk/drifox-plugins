# -*- coding: utf-8 -*-
"""
dsh_plugin_self_test — 插件自检（源自 dsh-super-injector dev_self_test 降级）

校验目标插件的目录结构完整性：
- .drifox-plugin/plugin.json 存在且为合法 JSON（含 name/version/components 必填字段）
- __init__.py 存在（Python 包标记）
- README.md 存在

纯标准库实现，无第三方依赖。
"""

import json
from pathlib import Path

from app.tools.result import ToolResult

_REQUIRED_MANIFEST_KEYS = ("name", "description", "version", "components")

_SELF_TEST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "dsh_plugin_self_test",
        "description": (
            "校验插件目录结构完整性：manifest 存在且合法、__init__.py 与 README.md 齐备。"
            "target 为空时自检当前插件（dsh-super-injector）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "要自检的插件目录（绝对路径或相对 workdir）；缺省自检当前插件",
                },
            },
        },
    },
}


def _check_plugin(plugin_dir: Path) -> tuple[list[str], list[str]]:
    """返回 (ok_lines, problem_lines)。"""
    ok: list[str] = []
    problems: list[str] = []

    manifest_path = plugin_dir / ".drifox-plugin" / "plugin.json"
    if not manifest_path.exists():
        problems.append("✗ .drifox-plugin/plugin.json 不存在")
    else:
        ok.append("✓ .drifox-plugin/plugin.json 存在")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            ok.append("✓ manifest 为合法 JSON")
            missing = [k for k in _REQUIRED_MANIFEST_KEYS if k not in manifest]
            if missing:
                problems.append(f"✗ manifest 缺少必填字段: {', '.join(missing)}")
            else:
                ok.append("✓ manifest 必填字段齐备（name/description/version/components）")
        except json.JSONDecodeError as e:
            problems.append(f"✗ manifest 不是合法 JSON: {e}")

    for fname in ("__init__.py", "README.md"):
        if (plugin_dir / fname).exists():
            ok.append(f"✓ {fname} 存在")
        else:
            problems.append(f"✗ {fname} 不存在")

    return ok, problems


def _self_test_impl(tool_ctx, **kwargs):
    workdir = tool_ctx.get("workdir") or str(Path.cwd())
    target = kwargs.get("target") or ""
    plugin_dir = (
        Path(target) if target else Path(__file__).resolve().parent.parent
    )
    if not plugin_dir.is_absolute():
        plugin_dir = Path(workdir) / plugin_dir

    lines = [f"# dsh_plugin_self_test — 插件自检: {plugin_dir}"]
    if not plugin_dir.is_dir():
        return ToolResult(False, error=f"目标不是目录: {plugin_dir}")

    ok, problems = _check_plugin(plugin_dir)
    lines.extend(ok)
    if problems:
        lines.extend(problems)
        return ToolResult(False, error="\n".join(lines))
    lines.append("结论：结构完整 ✓")
    return ToolResult(True, content="\n".join(lines))


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "dsh_plugin_self_test",
        _SELF_TEST_SCHEMA,
        impl=_self_test_impl,
        danger="safe",
        icon="check",
        cn_name="插件自检",
        group="dsh-super-injector",
        description="校验插件目录结构与 manifest 完整性",
    )
