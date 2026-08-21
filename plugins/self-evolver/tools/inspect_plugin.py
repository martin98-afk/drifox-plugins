# -*- coding: utf-8 -*-
"""
evolution_inspect — 自进化工具 3：扫描分析已安装 DriFox 插件。

- 列出 system+user 根的全部插件（含版本/组件/文件数）
- 深查单个插件：目录树、manifest 摘要、各组件文件清单、TODO 标记定位
  （TODO 定位帮助 AI 快速找到骨架中待填充的位置）

自包含：纯标准库实现，扫描根与主加载器一致。
"""
import json
from pathlib import Path

from app.tools.result import ToolResult

_MAX_TREE_DEPTH = 3
_MAX_TREE_LINES = 80


def _plugin_roots():
    roots = []
    try:
        from app.plugins.loaders.plugin_tool_loader import _plugin_roots as _lr

        for p in _lr():
            roots.append((Path(p), "system" if "drifox-plugins2" not in str(p) else "system"))
    except Exception:
        pass
    try:
        from app.utils.utils import get_app_data_dir

        roots.append((Path(get_app_data_dir()) / "plugins", "user"))
    except Exception:
        roots.append((Path.home() / ".drifox" / "plugins", "user"))
    seen, uniq = set(), []
    for p, kind in roots:
        if p.is_dir() and str(p) not in seen:
            seen.add(str(p))
            uniq.append((p, kind))
    return uniq


def _plugin_summary(base: Path) -> dict | None:
    """读取单个插件 manifest 摘要；无 manifest 返回 None"""
    mf = base / ".drifox-plugin" / "plugin.json"
    if not mf.exists():
        return None
    try:
        m = json.loads(mf.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        m = {}
    comps = [k for k, v in (m.get("components") or {}).items() if v]
    return {
        "version": m.get("version", "?"),
        "components": comps or ["?"],
        "desc": (m.get("description") or "")[:60],
    }


def _list_plugins() -> str:
    lines = ["已安装插件清单（system 根 + user 根）：", ""]
    for root, kind in _plugin_roots():
        plugins = []
        for d in sorted(root.iterdir()):
            if d.is_dir() and not d.name.startswith((".", "_")):
                s = _plugin_summary(d)
                if s:
                    plugins.append((d.name, s))
        label = f"[{kind}] {root}"
        lines.append(label)
        lines.append("─" * min(len(label) + 2, 60))
        if not plugins:
            lines.append("  （无 manifest 插件）")
        for name, s in plugins:
            lines.append(f"  {name} v{s['version']}  [{', '.join(s['components'])}]")
        lines.append("")
    lines.append("深查单个插件：evolution_inspect plugin_name=<name>")
    return "\n".join(lines)


def _dir_tree(base: Path, max_depth: int = _MAX_TREE_DEPTH) -> list:
    """目录树（限深度/行数）"""
    lines = []

    def walk(d: Path, prefix: str, depth: int):
        if depth > max_depth or len(lines) >= _MAX_TREE_LINES:
            return
        entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        entries = [e for e in entries if e.name != "__pycache__" and not e.name.startswith(".")]
        # 隐藏目录也要展示（.drifox-plugin/.mcp.json 重要）
        entries = sorted(
            [e for e in d.iterdir() if e.name != "__pycache__"],
            key=lambda p: (p.is_file(), p.name.lower()),
        )
        for i, e in enumerate(entries):
            if len(lines) >= _MAX_TREE_LINES:
                lines.append(prefix + "…（截断）")
                return
            last = i == len(entries) - 1
            mark = "└─ " if last else "├─ "
            lines.append(prefix + mark + e.name + ("/" if e.is_dir() else ""))
            if e.is_dir():
                walk(e, prefix + ("   " if last else "│  "), depth + 1)

    walk(base, "", 1)
    return lines


def _find_todos(base: Path) -> list:
    """定位骨架中待填充的 TODO（前 10 处）"""
    todos = []
    for p in sorted(base.rglob("*")):
        if (
            p.is_file()
            and p.suffix in (".py", ".md", ".json")
            and "__pycache__" not in str(p)
            and len(todos) < 10
        ):
            try:
                for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                    if "TODO" in line and len(todos) < 10:
                        rel = p.relative_to(base)
                        todos.append(f"  {rel}:{ln}  {line.strip()[:70]}")
            except (OSError, UnicodeDecodeError):
                continue
    return todos


def _impl(tool_ctx, **kwargs):
    try:
        plugin_name = (kwargs.get("plugin_name") or "").strip()
        list_all = bool(kwargs.get("list_all"))

        if list_all or not plugin_name:
            return ToolResult(True, content=_list_plugins())

        base = None
        for root, kind in _plugin_roots():
            cand = root / plugin_name
            if cand.is_dir():
                base = cand
                break
        if base is None:
            return ToolResult(False, error=f"未找到插件 {plugin_name}（system+user 根均无）")

        s = _plugin_summary(base)
        lines = [f"插件 {plugin_name}（{base}）", ""]
        if s:
            lines.append(f"版本：{s['version']}")
            lines.append(f"组件：{', '.join(s['components'])}")
            lines.append(f"描述：{s['desc']}")
            lines.append("")

        lines.append("目录结构：")
        lines += ["  " + t for t in _dir_tree(base)]

        todos = _find_todos(base)
        if todos:
            lines.append("")
            lines.append("待填充 TODO（骨架未完成标记）：")
            lines += todos

        lines.append("")
        lines.append(
            "提示：user 根插件直接 read/edit 修改即热重载；"
            "修改后用 evolution_validate 复验。"
        )
        return ToolResult(True, content="\n".join(lines))
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"evolution_inspect 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "evolution_inspect",
        "description": (
            "自进化：扫描分析已安装的 DriFox 插件。"
            "list_all=true 列出全部插件（版本/组件）；指定 plugin_name 深查单个插件"
            "（目录树/manifest 摘要/TODO 定位）。用于优化/修复插件前摸清结构。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "深查的插件名；不填则列出全部插件",
                },
                "list_all": {
                    "type": "boolean",
                    "description": "true 时列出全部已装插件清单",
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
        "evolution_inspect", _SCHEMA, impl=_impl,
        danger="safe", icon="evolution_inspect", cn_name="扫描分析插件",
        group="自进化", description="扫描已装插件结构（清单/目录树/TODO 定位）",
    )
