# -*- coding: utf-8 -*-
"""
查工具插件路径 — 开发期工具。

背景：DriFox 的工具都是可热重载的插件（位于 ~/.drifox/plugins/<name>/tools/*.py）。
本工具输入工具名，返回其实现文件的绝对路径，让大模型（或用户）可以直接用
read/edit/write 修改实现，保存后 DriFox 自动热重载生效，无需重启。

若现有工具不足以满足需求，提示可加载 plugin-creator 技能自行开发新工具。

实现自包含：仅用标准库 AST 扫描插件目录的 tools/*.py，通过提取
registry.register("工具名", ...) 的第一个参数（或关键字 name=）建立映射。
扫描根与主程序 PluginToolLoader 保持一致（优先复用其根列表，失败时按同样规则推导）：
- system 根：主程序工作树 plugins/（read/edit/bash/lsp 等系统工具所在）
- user 根：用户数据目录 <app_data>/plugins/（~/.drifox/plugins）
同名工具跨根覆盖规则与主加载器一致：user 覆盖 system，同根先扫者优先。
"""
import ast
import glob
import os
from pathlib import Path

from app.tools.result import ToolResult


def _plugin_roots():
    """插件扫描根列表 [(路径, system|user)]，顺序与主程序 PluginToolLoader 一致（system 在前）。

    优先直接复用主加载器的根列表（单一数据源）；不可用时按同样规则推导：
    - system：app 包所在工作树下的 plugins/
    - user：get_app_data_dir()/plugins，再回退 ~/.drifox/plugins
    """
    roots = []
    try:
        from app.plugins.loaders.plugin_tool_loader import _plugin_roots as _loader_roots

        for p in _loader_roots():
            roots.append((p, _root_kind(p)))
        if roots:
            return roots
    except Exception:
        pass
    try:
        import app

        app_file = getattr(app, "__file__", None)
        if app_file:
            system_root = Path(app_file).resolve().parent.parent / "plugins"
            if system_root.is_dir():
                roots.append((system_root, "system"))
    except Exception:
        pass
    try:
        from app.utils.utils import get_app_data_dir

        user_root = Path(get_app_data_dir()) / "plugins"
    except Exception:
        user_root = Path.home() / ".drifox" / "plugins"
    roots.append((user_root, "user"))
    return roots


def _root_kind(root: Path) -> str:
    """判定扫描根等级：app_data/plugins → user，其余（工作树 plugins/）→ system"""
    try:
        from app.utils.utils import get_app_data_dir

        if Path(get_app_data_dir()) / "plugins" == Path(root):
            return "user"
    except Exception:
        if Path.home() / ".drifox" / "plugins" == Path(root):
            return "user"
    return "system"


def _iter_plugin_files(root: Path):
    """遍历插件根下所有工具实现文件，yield (插件名, 文件路径)。

    与主加载器 _iter_tool_modules 同构：<name>/tools/*.py 优先，
    单文件插件 <name>/<name>.py 兑底；跳过 _ 开头文件。
    """
    if not root.is_dir():
        return
    for plugin_dir in sorted(root.iterdir()):
        if not plugin_dir.is_dir():
            continue
        tools_dir = plugin_dir / "tools"
        if tools_dir.is_dir():
            for py in sorted(tools_dir.glob("*.py")):
                if not py.name.startswith("_"):
                    yield plugin_dir.name, py
        else:
            single = plugin_dir / f"{plugin_dir.name}.py"
            if single.exists():
                yield plugin_dir.name, single


def _extract_registered_names(py: Path):
    """AST 提取单文件内 registry.register("name", ...) 的全部工具名"""
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    names = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "register"
        ):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                names.append(node.args[0].value)
            else:
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        names.append(kw.value.value)
                        break
    return names


def _scan_tools():
    """扫描全部插件根（system + user），建立 工具名 -> (插件名, 绝对路径, 根等级) 映射。

    覆盖规则与主加载器一致：跨根 user 覆盖 system；同根内先扫到的优先。
    """
    mapping = {}
    for root, kind in _plugin_roots():
        for plugin_name, py in _iter_plugin_files(root):
            for name in _extract_registered_names(py):
                if name not in mapping or mapping[name][2] != kind:
                    mapping[name] = (plugin_name, str(py.resolve()), kind)
    return mapping


def _impl(tool_ctx, **kwargs):
    try:
        tool_name = (kwargs.get("tool_name") or "").strip()
        list_all = bool(kwargs.get("list_all"))
        mapping = _scan_tools()

        if list_all:
            if not mapping:
                return ToolResult(
                    False,
                    error="未扫描到任何已注册的工具插件（system 根与 user 根均无 tools/*.py）。",
                )
            lines = ["已发现的工具（工具名 → 所属插件[根] → 实现路径）：", ""]
            for name in sorted(mapping):
                plugin_name, path, kind = mapping[name]
                label = plugin_name if plugin_name == kind else f"{plugin_name}·{kind}"
                lines.append(f"• {name}  [{label}]\n  {path}")
            lines.append("")
            lines.append("提示：user 根（~/.drifox/plugins）文件可直接 read/edit/write 修改，热重载自动生效；")
            lines.append("system 根为主程序工作树插件，修改需同步到主程序仓库。")
            lines.append("若现有工具不足，可加载 plugin-creator 技能开发新工具。")
            return ToolResult(True, content="\n".join(lines))

        if not tool_name:
            return ToolResult(
                False,
                error="请提供 tool_name 参数，或将 list_all 设为 true 列出全部工具。",
            )

        if tool_name not in mapping:
            known = sorted(mapping)
            hint = "已知工具：" + (", ".join(known) if known else "（无）")
            return ToolResult(
                False,
                error=f"未找到工具「{tool_name}」。{hint}\n可用 list_all=true 查看全部。",
            )

        plugin_name, path, kind = mapping[tool_name]
        if kind == "user":
            tip = "user 根文件可直接 read/edit/write 修改，保存后 DriFox 热重载自动生效。"
        else:
            tip = "system 根为主程序工作树插件（~/.drifox/plugins 之外），修改后需同步主程序仓库。"
        content = (
            f"工具「{tool_name}」实现文件：\n"
            f"{path}\n\n"
            f"所属插件：{plugin_name}（根：{kind}）\n\n"
            f"💡 {tip}\n"
            f"💡 若现有工具不足以满足需求，可加载 plugin-creator 技能自行开发新工具。"
        )
        return ToolResult(True, content=content)
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"find_tool_path 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "find_tool_path",
        "description": (
            "查找某个已注册工具的实现文件路径。"
            "扫描范围与主程序一致：system 根（主程序工作树 plugins/，含 read/edit/bash/lsp 等系统工具）"
            "+ user 根（~/.drifox/plugins 可热重载插件）。"
            "拿到路径后可直接修改实现（user 根保存即生效）。"
            "若现有工具不足，可加载 plugin-creator 技能开发新工具。"
            "不确定工具名时可设 list_all=true 列出全部。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "要查找的工具名（如 example_repeat）。不确定时可空置并设 list_all=true",
                },
                "list_all": {
                    "type": "boolean",
                    "description": "true 时列出所有已发现工具及其实现路径",
                    "default": False,
                },
            },
            "required": [],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "find_tool_path", _SCHEMA, impl=_impl,
        danger="safe", icon="magnifier", cn_name="查工具路径",
        group="开发工具", description="查找工具插件的实现文件路径（可热重载）",
        render_mode="",  # 默认折叠卡：与 powershell 等工具一致
    )
