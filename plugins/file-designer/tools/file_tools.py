# -*- coding: utf-8 -*-
"""open_file 工具：打开多格式文件设计预览窗口。

impl 通过 tool_ctx 获取上下文；UI 联动走 UIPluginRegistry（同 autoloop 模式）。
已知约束：若宿主将工具 impl 调度到非主线程，此处需改主线程派发
（参考 browser/ui/control_server.py 的主线程派发器）。
"""

from pathlib import Path

import importlib
import importlib.util

from app.tools.result import ToolResult


def _load_formats():
    """加载格式注册表 formats.py（tools/ui 共享契约）。

    本模块由 PluginToolLoader 以顶层模块身份 exec（无父包），不能用相对导入：
    优先复用 UI 侧已注册的 ui_plugin_file_designer.formats（单一状态源），
    UI 未加载时按路径 exec 独立副本兜底（formats 为模块级静态注册表，副本内容恒等）。
    """
    try:
        return importlib.import_module("ui_plugin_file_designer.formats")
    except Exception:
        pass
    path = Path(__file__).resolve().parent.parent / "ui" / "formats.py"
    spec = importlib.util.spec_from_file_location("_plugin_tool_file_designer_formats", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _open_file_impl(tool_ctx, **kwargs):
    formats = _load_formats()
    path = (kwargs.get("path") or "").strip()
    if not path:
        return ToolResult(False, content=f"缺少 path 参数（{formats.suffix_label()} 文件绝对路径）")
    p = Path(path).expanduser()
    if not p.is_file():
        return ToolResult(False, content=f"文件不存在: {path}")
    if p.suffix.lower() not in formats.SUPPORTED_SUFFIXES:
        return ToolResult(False, content=f"仅支持 {formats.suffix_label()}，收到: {p.suffix}")
    try:
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        registry = UIPluginRegistry.get_instance()
        registry.toggle_floating_card(
            "file-designer", main_widget=tool_ctx.get("main_widget")
        )
        card = registry.get_card_widget("file-designer")
        if card is None:
            return ToolResult(False, content="预览窗口初始化失败")
        ok = card.open_path(str(p))
        if ok:
            return ToolResult(
                True,
                content=(
                    f"已打开预览: {p.name}\n"
                    "窗口内点「拾取」按钮后点击文档元素，锚点+文本+截图会回填到输入框。"
                ),
            )
        return ToolResult(False, content=f"解析失败: {p.name}")
    except Exception as e:
        return ToolResult(False, content=f"打开预览失败: {e}")

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "open_file",
        "description": (
            "打开多格式文件设计预览窗口：解析 Word/PPT/Excel/CSV/XMind/Mermaid 并渲染可拾取预览，"
            "用户在窗口内点「拾取」后点击任意元素，"
            "元素的锚点+文本+截图会自动回填到输入框，供你针对精确元素做修改。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "支持格式的文件绝对路径"},
            },
            "required": ["path"],
        },
    },
}

def register(registry):
    """PluginToolLoader 注册入口。"""
    registry.register(
        "open_file", _SCHEMA, impl=_open_file_impl,
        danger="safe", cn_name="打开文件预览",
        group="文档", description="打开多格式文件设计预览窗口（可拾取元素回填）",
    )
