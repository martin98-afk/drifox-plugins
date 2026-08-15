# -*- coding: utf-8 -*-
"""
示例工具插件 — tools 组件的标准写法

约定（PluginToolLoader）：
- 文件位于 `tools/<tool>.py`（插件根目录下）
- 必须暴露顶层 `register(registry)` 函数
- `registry.register(...)` 必须显式声明 `danger`（registry 层拒绝未声明危险级别的插件工具）
- `impl` 通过 `tool_ctx` 获取上下文（如 `tool_ctx["workdir"]`），不依赖主程序 services

本文件演示一个最简工具：把输入文本重复 N 次。
"""
from app.tools.result import ToolResult


def _repeat_impl(tool_ctx, **kwargs):
    """impl：唯一入参约定为 (tool_ctx, **kwargs)"""
    text = kwargs.get("text", "")
    times = int(kwargs.get("times") or 1)
    times = max(1, min(times, 10))  # 防御：限制最大重复次数
    return ToolResult(True, content=f"{text}\n" * times)


_REPEAT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "example_repeat",
        "description": "示例工具：把输入文本重复 N 次（1-10 次）",
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


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "example_repeat", _REPEAT_SCHEMA, impl=_repeat_impl,
        danger="safe", icon="Repeat", cn_name="示例重复",
        group="示例", description="把输入文本重复 N 次",
        aliases=["ExampleRepeat", "repeat_text"],
    )
