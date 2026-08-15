# -*- coding: utf-8 -*-
"""example-plugin UI 组件入口 — 最小 register_ui(registry) 示例

约定（UIPluginRegistry.load_plugin）：
- `ui/__init__.py` 必须暴露顶层 `register_ui(registry)` 函数
- 通过 registry 注册浮动卡片 / 内容块渲染器 / 消息元素工厂

本文件仅演示注册骨架，不注册真实组件（示例插件不解决真实问题）。
"""


def register_ui(registry):
    """UI 组件注册入口（DriFox 启动时调用）"""
    # 示例：注册一个无操作浮动卡片骨架（仅演示调用方式，未挂载 widget）
    # registry.register_floating_card(card_id="example", widget_factory=...)
    pass
