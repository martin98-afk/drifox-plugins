# -*- coding: utf-8 -*-
"""example-plugin UI 组件入口 — 最小 register_ui(registry) 示例

约定（UIPluginRegistry.load_plugin）：
- `ui/__init__.py` 必须暴露顶层 `register_ui(registry)` 函数
- 通过 registry 注册浮动卡片 / 内容块渲染器 / 消息元素工厂

本文件仅演示注册骨架，不注册真实组件（示例插件不解决真实问题）。
"""


def register_ui(registry):
    """UI 组件注册入口（DriFox 启动时调用）。

    真实插件四步骨架（详见 docs/community-cookbook.md §6.1）：
      1. 清理旧 sys.modules 缓存（热重载关键）
      2. 注入插件根到 sys.path（ui 子模块跨模块导入必需）
      3. 调 registry 对应扩展点（浮动卡片 / 欢迎 tab / 内容渲染器）
      4. 错误隔离（单步异常不阻断其他 UI 组件加载）
    """
    # ① 清旧缓存（如 ui_plugin_example-plugin.*）
    # prefix = "ui_plugin_example-plugin."
    # for k in [k for k in sys.modules if k.startswith(prefix)]:
    #     del sys.modules[k]

    # ② 注入插件根到 sys.path（ui_dir = str(Path(__file__).resolve().parent)）
    # if ui_dir not in sys.path: sys.path.insert(0, ui_dir)

    # ③ 注册扩展点（示例：浮动卡片，自动获得 /example 命令，toggle 行为）
    # registry.register_floating_card(
    #     plugin_name="example-plugin", card_id="example",
    #     widget_class=ExampleCard, container="right", title="示例", default_visible=False,
    # )

    # ④ 错误隔离：单步注册包在 try/except 中，异常只记日志不阻断其他组件
    pass
