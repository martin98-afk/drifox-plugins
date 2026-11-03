# -*- coding: utf-8 -*-
"""open_docx 工具：让模型打开 docx 设计预览窗口。

impl 通过 tool_ctx 获取上下文；UI 联动走 UIPluginRegistry（同 autoloop 模式）。
已知约束：若宿主将工具 impl 调度到非主线程，此处需改主线程派发
（参考 browser/ui/control_server.py 的主线程派发器）。
"""

from pathlib import Path

from app.tools.result import ToolResult


def _open_docx_impl(tool_ctx, **kwargs):
    path = (kwargs.get("path") or "").strip()
    if not path:
        return ToolResult(False, content="缺少 path 参数（.docx 文件路径）")
    p = Path(path).expanduser()
    if not p.is_file():
        return ToolResult(False, content=f"文件不存在: {path}")
    if p.suffix.lower() != ".docx":
        return ToolResult(False, content=f"仅支持 .docx，收到: {p.suffix}")
    try:
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        registry = UIPluginRegistry.get_instance()
        registry.toggle_floating_card(
            "docx-designer", main_widget=tool_ctx.get("main_widget")
        )
        card = registry.get_card_widget("docx-designer")
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
        "name": "open_docx",
        "description": (
            "打开 docx 文档设计预览窗口：解析 Word 文档并渲染可拾取预览，"
            "用户在窗口内点「拾取」后点击任意段落/表格/公式/图片，"
            "元素的锚点+文本+截图会自动回填到输入框，供你针对精确元素做修改。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "docx 文件绝对路径"},
            },
            "required": ["path"],
        },
    },
}


def register(registry):
    """PluginToolLoader 注册入口。"""
    registry.register(
        "open_docx", _SCHEMA, impl=_open_docx_impl,
        danger="safe", cn_name="打开文档预览",
        group="文档", description="打开 docx 设计预览窗口（可拾取元素回填）",
    )
