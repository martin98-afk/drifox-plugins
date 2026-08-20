# -*- coding: utf-8 -*-
"""
查工具插件路径 — 开发期工具。

背景：DriFox 的工具都是可热重载的插件（位于 ~/.drifox/plugins/<name>/tools/*.py）。
本工具输入工具名，返回其实现文件的绝对路径，让大模型（或用户）可以直接用
read/edit/write 修改实现，保存后 DriFox 自动热重载生效，无需重启。

若现有工具不足以满足需求，提示可加载 plugin-creator 技能自行开发新工具。

实现自包含：仅用标准库扫描用户插件目录的 tools/*.py，通过 AST 提取
registry.register("工具名", ...) 的第一个参数（或关键字 name=）建立映射，
不依赖主程序内部 API。
"""
import ast
import glob
import os

from app.tools.result import ToolResult

# 用户可热重载工具插件根目录（标准约定）
PLUGINS_ROOT = os.path.expanduser(os.path.join("~", ".drifox", "plugins"))


def _scan_tools():
    """扫描用户插件目录下所有 tools/*.py，建立 工具名 -> (插件名, 绝对路径) 映射。"""
    mapping = {}
    if not os.path.isdir(PLUGINS_ROOT):
        return mapping
    for py in glob.glob(os.path.join(PLUGINS_ROOT, "*", "tools", "*.py")):
        plugin_name = os.path.basename(os.path.dirname(os.path.dirname(py)))
        try:
            tree = ast.parse(open(py, encoding="utf-8").read())
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "register"
            ):
                name = None
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    name = node.args[0].value
                else:
                    for kw in node.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            name = kw.value.value
                            break
                if name and name not in mapping:
                    mapping[name] = (plugin_name, os.path.abspath(py))
    return mapping


def _impl(tool_ctx, **kwargs):
    tool_name = (kwargs.get("tool_name") or "").strip()
    list_all = bool(kwargs.get("list_all"))
    mapping = _scan_tools()

    if list_all:
        if not mapping:
            return ToolResult(
                False,
                content="未在 ~/.drifox/plugins 下扫描到任何已注册的工具（无 tools/*.py）。",
            )
        lines = ["已发现的工具插件（工具名 → 所属插件 → 实现路径）：", ""]
        for name in sorted(mapping):
            plugin_name, path = mapping[name]
            lines.append(f"• {name}  [{plugin_name}]\n  {path}")
        lines.append("")
        lines.append("提示：直接用 read/edit/write 修改对应文件，DriFox 热重载自动生效；")
        lines.append("若现有工具不足，可加载 plugin-creator 技能开发新工具。")
        return ToolResult(True, content="\n".join(lines))

    if not tool_name:
        return ToolResult(
            False,
            content="请提供 tool_name 参数，或将 list_all 设为 true 列出全部工具。",
        )

    if tool_name not in mapping:
        known = sorted(mapping)
        hint = "已知工具：" + (", ".join(known) if known else "（无）")
        return ToolResult(
            False,
            content=f"未找到工具「{tool_name}」。{hint}\n可用 list_all=true 查看全部。",
        )

    plugin_name, path = mapping[tool_name]
    content = (
        f"工具「{tool_name}」实现文件：\n"
        f"{path}\n\n"
        f"所属插件：{plugin_name}（位于 ~/.drifox/plugins/{plugin_name}/）\n\n"
        f"💡 可直接用 read/edit/write 修改此文件，保存后 DriFox 热重载自动生效，无需重启。\n"
        f"💡 若现有工具不足以满足需求，可加载 plugin-creator 技能自行开发新工具。"
    )
    return ToolResult(True, content=content)


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "find_tool_path",
        "description": (
            "查找某个已注册工具插件的实现文件路径（~/.drifox/plugins 下的 tools/*.py）。"
            "DriFox 的工具都是可热重载的插件：拿到路径后可直接修改实现，保存即生效。"
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
        render_mode="expand",  # 无折叠展开：路径与提示直接可见
    )
