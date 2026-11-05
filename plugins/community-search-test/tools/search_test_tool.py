# -*- coding: utf-8 -*-
"""
community-search-test — 机制验证插件的最小工具

用途：验证「fork 即源」发布链路。市场源添加后本插件可被搜索并安装，
安装后出现一枚回声工具。验证完成后整插件删除即可。
"""
from app.tools.result import ToolResult


def _echo_impl(tool_ctx, **kwargs):
    text = str(kwargs.get("text") or "")
    return ToolResult(True, content=f"[community-search-test] 收到: {text}")


_ECHO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "community_search_test_echo",
        "description": "机制验证工具：原样返回输入文本，证明插件安装成功。",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要回显的文本"},
            },
            "required": ["text"],
        },
    },
}


def register(registry):
    registry.register(
        "community_search_test_echo", _ECHO_SCHEMA, impl=_echo_impl,
        danger="safe", cn_name="社区测试回声",
        group="测试", description="原样返回输入文本",
        render_mode="inline",
        preview=lambda tool_args: f"回显 {str(tool_args.get('text') or '')[:30]}",
    )
