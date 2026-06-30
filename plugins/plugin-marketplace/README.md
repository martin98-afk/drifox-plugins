# plugin-marketplace 插件 — DriFox 官方插件市场

在 DriFox 主窗口里直接浏览、安装、管理插件市场的官方插件。无需退出 DriFox、无需命令行 — 一个浮动卡片 + 两个内容块渲染器，把整个生态装进 GUI。

## 功能

| 功能 | 说明 |
|------|------|
| 🛒 **浏览市场** | 浮动卡片拉取 `drifox-plugins` 仓库的 `marketplace.json`，按分类过滤 |
| 🔍 **插件搜索** | 名称 / 关键词 / 描述关键字实时过滤 |
| ⚙️ **一键安装** | 异步从 git 子目录下载到 `~/.drifox/plugins/`，不阻塞 UI |
| 🗑️ **一键卸载** | 调用插件管理器完成卸载 |
| 📊 **市场网格内容渲染器** | 在消息流中渲染 `custom_type: plugin_marketplace_grid` 内容块 |
| 🪪 **详情卡内容渲染器** | 在消息流中渲染 `custom_type: plugin_marketplace_card` 内容块 |
| 🌓 **主题适配** | 颜色方案自动跟随浅色 / 深色主题切换 |
| 🔁 **热重载** | 子模块缓存自动清理，避免热重载 NameError |

## 安装

```bash
# Windows
xcopy plugins\plugin-marketplace %USERPROFILE%\.drifox\plugins\plugin-marketplace /E /I /Y

# Linux / macOS
cp -r plugins/plugin-marketplace ~/.drifox/plugins/
```

启动 DriFox，输入 `/plugin-marketplace` 打开市场面板。

## 目录结构

```
plugins/plugin-marketplace/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.ui=true）
├── __init__.py              # Python 包标记
├── ui/
│   ├── __init__.py          # register_ui(registry) 入口
│   ├── cards.py             # MarketplaceCard 浮动卡片
│   ├── data.py              # marketplace.json 拉取与本地缓存
│   ├── installer.py         # 插件下载 / 安装 / 卸载实现
│   └── renderers.py         # 两个 content renderer
└── README.md
```

## UI 注册接口

```python
def register_ui(registry: UIPluginRegistry) -> None:
    from .renderers import render_plugin_grid, render_plugin_card
    from .cards import MarketplaceCard

    # 注册内容块渲染器（2 个）
    registry.register_content_renderer(
        plugin_name="plugin-marketplace",
        type_name="plugin_marketplace_grid",
        render_func=render_plugin_grid,
        priority=10,
    )
    registry.register_content_renderer(
        plugin_name="plugin-marketplace",
        type_name="plugin_marketplace_card",
        render_func=render_plugin_card,
        priority=10,
    )

    # 注册浮动卡片（自动注册 /plugin-marketplace 命令）
    registry.register_floating_card(
        plugin_name="plugin-marketplace",
        card_id="plugin-marketplace",
        widget_class=MarketplaceCard,
        container="bottom",
        title="插件市场",
        default_visible=False,
    )
```

## 数据源

| 数据 | 来源 |
|------|------|
| 插件市场清单 | [drifox-plugins/marketplace.json](../../marketplace.json) |
| 插件源代码 | `https://github.com/martin98-afk/drifox-plugins`（git-subdir 方式按需拉取） |
| 已安装列表 | 扫描 `~/.drifox/plugins/` 与 `<项目根>/plugins/` |
| 安装状态 | 通过 `plugin.json` 的 `name` / `version` 字段对比本地 |

## 与 context-usage-stats / plugin-manager 的关系

| 维度 | plugin-marketplace | context-usage-stats | plugin-manager |
|------|:---:|:---:|:---:|
| 浮动卡片 | ✅ | ✅ | ✅ |
| 内容块渲染器 | ✅（2 个） | — | — |
| 消息元素工厂 | — | — | — |
| type | system | user | system |

> **建议三件套**：用 `plugin-marketplace` 找插件 → 用 `plugin-manager` 启用/禁用 → 用 `context-usage-stats` 看使用情况。

## 参考

- [DriFoxx/plugins/plugin-marketplace](../../../../D:/work/DriFoxx/plugins/plugin-marketplace/)（运行时实现）
- [plugins/README.md](../README.md)（官方插件索引）
- [marketplace.json](../../marketplace.json)（市场清单数据源）
