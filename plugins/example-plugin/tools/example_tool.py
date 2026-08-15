# -*- coding: utf-8 -*-
"""
示例工具插件 — tools 组件的标准写法

约定（PluginToolLoader）：
- 文件位于 `tools/<tool>.py`（插件根目录下）
- 必须暴露顶层 `register(registry)` 函数
- `registry.register(...)` 必须显式声明 `danger`（registry 层拒绝未声明危险级别的插件工具）
- `impl` 通过 `tool_ctx` 获取上下文（如 `tool_ctx["workdir"]`），不依赖主程序 services

本文件演示三个重点：
1. 插件 icon 自包含 — tools/icons/（深色）+ tools/icons_light/（浅色）
2. render / preview / summarize 渲染三闭包 + render_mode
3. make_summarize_from_preview 工具函数（preview → summarize 复用）
"""
from html import escape

from app.tools.registry import make_summarize_from_preview
from app.tools.result import ToolResult


# ========== 示例 1：最简工具（重点演示「插件 icon 自包含」） ==========

def _repeat_impl(tool_ctx, **kwargs):
    """impl：唯一入参约定为 (tool_ctx, **kwargs)"""
    text = kwargs.get("text", "")
    times = int(kwargs.get("times") or 1)
    times = max(1, min(times, 10))  # 防御：限制最大重复次数
    content = (f"{text}\n" * times).rstrip()
    return ToolResult(True, content=content)


_REPEAT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "example_repeat",
        "description": "示例工具：把输入文本重复 N 次（1-10 次）。"
                       "icon 字段演示插件自带 SVG 的自包含用法。",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要重复的文本"},
                "times": {"type": "integer", "description": "重复次数（默认 1）", "default": 1},
            },
            "required": ["text"],
        },
    },
}


def _preview_repeat(tool_args: dict) -> str:
    """自然语言预览：用于 inline 卡 / 折叠头显示"""
    text = tool_args.get("text", "")
    times = int(tool_args.get("times") or 1)
    return f"重复 {times} 次：{escape(text)[:30]}"


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    # ── icon 字段约定 ───────────────────────────────────────────────
    # 渲染层（render_helpers._get_tool_icon_html）查找顺序：
    #   1. <插件>/tools/icons_light/<icon>.svg  ← 浅色主题
    #   2. <插件>/tools/icons/<icon>.svg        ← 深色主题
    #   3. 回退主程序 qrc 资源（主题感知）
    #
    # icon 文件名大小写敏感，可包含中文 / 数字开头 / 字母；
    # 浅色版缺失时自动回退深色版（registry 层行为）。
    #
    # 本示例：icon="工具" 对应 tools/icons/工具.svg + tools/icons_light/工具.svg
    _register_repeat(registry)


def _register_repeat(registry):
    """示例 1：最简工具 — 重点演示「插件 icon 自包含」"""
    registry.register(
        "example_repeat", _REPEAT_SCHEMA, impl=_repeat_impl,
        danger="safe", icon="工具", cn_name="示例重复",
        group="示例", description="把输入文本重复 N 次",
        aliases=["ExampleRepeat", "repeat_text"],
        render_mode="inline",  # 单行紧凑：preview 即信息，无需 body
        preview=_preview_repeat,
        summarize=make_summarize_from_preview(_preview_repeat),
    )


# ========== 示例 2：含完整 body 渲染的工具（演示 render 闭包 + render_mode） ==========

# 说明：默认不启用第二个工具，避免污染工具列表。
# 把下面整段代码取消注释，然后在 register() 末尾追加一行 _register_greet(registry) 即可。

# def _greet_impl(tool_ctx, **kwargs):
#     name = kwargs.get("name", "世界")
#     return ToolResult(True, content=f"你好，{name}！")
#
#
# _GREET_SCHEMA = {
#     "type": "function",
#     "function": {
#         "name": "example_greet",
#         "description": "示例工具：返回问候语。演示 render 闭包自定义 body。",
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "name": {"type": "string", "description": "被问候的名字"},
#             },
#         },
#     },
# }
#
#
# def _preview_greet(tool_args: dict) -> str:
#     name = tool_args.get("name", "世界")
#     return f"问候 {escape(name)}"
#
#
# def _render_greet_body(result: ToolResult, tool_name: str, tool_args: dict, success: bool) -> str:
#     """body 渲染闭包：返回 HTML 字符串，渲染层直接嵌入。
#
#     签名：render(result, tool_name, tool_args, success) -> str | None
#     返回 None 时回退通用渲染（文本 / 表格 / diff / echarts）。
#     """
#     if not success:
#         return None
#     name = tool_args.get("name", "世界")
#     return (
#         f'<div style="padding:8px 12px; border-left:3px solid #4caf50; '
#         f'background:rgba(76,175,80,0.08); border-radius:4px;">'
#         f'👋 你好，<b>{escape(name)}</b>！'
#         f'</div>'
#     )
#
#
# def _register_greet(registry):
#     """示例 2：含 render 闭包的 expand 模式工具"""
#     registry.register(
#         "example_greet", _GREET_SCHEMA, impl=_greet_impl,
#         danger="safe", icon="工具", cn_name="示例问候",
#         group="示例", description="返回问候语，演示 render 闭包",
#         render_mode="expand",  # 无折叠：render body 永远可见
#         render=_render_greet_body,
#         preview=_preview_greet,
#         summarize=make_summarize_from_preview(_preview_greet),
#     )