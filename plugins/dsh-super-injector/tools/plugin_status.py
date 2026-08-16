# -*- coding: utf-8 -*-
"""
dsh_plugin_status — 插件状态查询（源自 dsh-super-injector dev_plugin_status + dev_injected_list 合并降级）

列出两处插件目录并读取各 plugin.json 显示 name/version/components：
1. 用户级：~/.drifox/plugins/
2. 项目级：<workdir>/.drifox/plugins/

纯标准库实现，无第三方依赖。
"""

import json
from pathlib import Path

from app.tools.result import ToolResult

_STATUS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "dsh_plugin_status",
        "description": (
            "列出已安装插件（用户级 ~/.drifox/plugins/ 与项目级 .drifox/plugins/），"
            "读取各插件 manifest 显示 name/version/components。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["all", "user", "project"],
                    "description": "查询范围：all=两者（默认），user=仅用户级，project=仅项目级",
                },
            },
        },
    },
}


def _scan_dir(plugins_dir: Path, label: str, lines: list[str]) -> None:
    if not plugins_dir.is_dir():
        lines.append(f"## {label}: {plugins_dir}（不存在）")
        return
    lines.append(f"## {label}: {plugins_dir}")
    entries = sorted(p for p in plugins_dir.iterdir() if p.is_dir())
    if not entries:
        lines.append("  （空）")
        return
    for p in entries:
        manifest_path = p / ".drifox-plugin" / "plugin.json"
        if not manifest_path.exists():
            lines.append(f"- {p.name}: 缺少 .drifox-plugin/plugin.json")
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            lines.append(f"- {p.name}: manifest 解析失败（{e}）")
            continue
        name = manifest.get("name", "?")
        version = manifest.get("version", "?")
        components = ",".join(sorted(manifest.get("components", {}).keys())) or "-"
        lines.append(f"- {name} v{version} [components: {components}]")


def _status_impl(tool_ctx, **kwargs):
    scope = kwargs.get("scope", "all")
    lines: list[str] = ["# dsh_plugin_status — 插件状态"]
    workdir = tool_ctx.get("workdir") or str(Path.cwd())
    user_dir = Path.home() / ".drifox" / "plugins"
    project_dir = Path(workdir) / ".drifox" / "plugins"
    if scope in ("user", "all"):
        _scan_dir(user_dir, "用户级", lines)
    if scope in ("project", "all"):
        _scan_dir(project_dir, "项目级", lines)
    return ToolResult(True, content="\n".join(lines))


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "dsh_plugin_status",
        _STATUS_SCHEMA,
        impl=_status_impl,
        danger="safe",
        icon="list",
        cn_name="插件状态",
        group="dsh-super-injector",
        description="列出已安装插件的 name/version/components",
    )
