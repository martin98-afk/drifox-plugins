# -*- coding: utf-8 -*-
"""
dsh_injector_info — 注入器能力声明（源自 dsh-super-injector，DriFox 重写版降级）

返回能力声明文本：说明本环境已装配的运行时注入能力（插件安装/状态/自检路径）。
"""

from app.tools.result import ToolResult

CAPABILITY_TEXT = (
    "本环境装有 dsh-super-injector（dev_* 能力，DriFox 重写版）："
    "本地插件可一键装配——插件安装、状态查询、自检、运行时注入同一通道；"
    "注入即完整生效（host+UI）、可热重载与卸载，卸载即净。"
    "插件自身的提示词/工具/钩子皆可自我优化；"
    "建新插件优先克隆/借鉴/重构生态已有资源，不重复造轮子。"
    "若注入器无法支撑此闭环，优先修复注入器。"
    "从零体验路径：dsh_plugin_status → dsh_plugin_self_test → 安装插件 → 校验状态。"
)

_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "dsh_injector_info",
        "description": "返回 dsh-super-injector 能力声明（注入/装配/自检路径总览）。",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}


def _info_impl(tool_ctx, **kwargs):
    return ToolResult(True, content=CAPABILITY_TEXT)


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "dsh_injector_info",
        _INFO_SCHEMA,
        impl=_info_impl,
        danger="safe",
        icon="info",
        cn_name="注入器信息",
        group="dsh-super-injector",
        description="返回注入器能力声明",
    )
