# plugin-manager 插件 — DriFox 插件管理器

在 DriFox 主窗口里直接管理已安装的插件：列出 / 搜索 / 启用 / 禁用 / 卸载。比命令行更直观，所有操作在主窗口浮动卡片里完成。

## 功能

| 功能 | 说明 |
|------|------|
| 📋 **列出插件** | 扫描 `~/.drifox/plugins/` 与项目级 `plugins/`，按 system / user 分类展示 |
| 🔍 **搜索过滤** | 按名称 / 描述关键字实时过滤 |
| ✅ **启用插件** | 把 `.drifox/plugins-disabled/<name>/` 移回 `.drifox/plugins/` |
| ⛔ **禁用插件** | 把 `.drifox/plugins/<name>/` 移到 `.drifox/plugins-disabled/` |
| 🗑️ **卸载插件** | 删除 `~/.drifox/plugins/<name>/`（仅 user 插件可卸载，system 插件不提供） |
| ⚡ **异步操作** | 文件移动 / 删除在 `QThread` 后台执行，不阻塞 UI |
| 🌓 **主题适配** | 颜色方案自动跟随浅色 / 深色主题切换 |
| 🔁 **热重载** | 子模块缓存自动清理，避免热重载 NameError |

## 安装

```bash
# Windows
xcopy plugins\plugin-manager %USERPROFILE%\.drifox\plugins\plugin-manager /E /I /Y

# Linux / macOS
cp -r plugins/plugin-manager ~/.drifox/plugins/
```

启动 DriFox，输入 `/plugin-manager` 打开管理面板。

## 目录结构

```
plugins/plugin-manager/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.ui=true，type=system）
├── __init__.py              # Python 包标记
├── ui/
│   ├── __init__.py          # register_ui(registry) 入口
│   └── cards.py             # PluginManagerCard 浮动卡片
└── README.md
```

## UI 注册接口

```python
def register_ui(registry: UIPluginRegistry) -> None:
    from .cards import PluginManagerCard

    # 注册浮动卡片（自动注册 /plugin-manager 命令）
    registry.register_floating_card(
        plugin_name="plugin-manager",
        card_id="plugin-manager",
        widget_class=PluginManagerCard,
        container="bottom",
        title="插件管理",
        default_visible=False,
    )
```

## 启 / 禁 / 卸 约定

| 操作 | user 插件 | system 插件 |
|------|:---:|:---:|
| 启用 | ✅ | ❌（始终启用） |
| 禁用 | ✅ | ❌（始终启用） |
| 卸载 | ✅ | ❌（保护系统插件） |

禁用流程：

```
~/.drifox/plugins/<name>/            # 启用状态
        ⬇  禁用
~/.drifox/plugins-disabled/<name>/   # 禁用状态
        ⬇  启用
~/.drifox/plugins/<name>/            # 回到启用
```

> 禁用通过目录移动实现，UIPluginRegistry 启动时只扫描 `~/.drifox/plugins/`，从而自然屏蔽被禁用的插件。

## 与 plugin-marketplace 的关系

`plugin-marketplace` 提供安装入口；安装后通过 `plugin-manager` 进行启 / 禁 / 卸。两个插件建议同时启用，形成完整的「装 → 配 → 卸」闭环。

## 参考

- [DriFoxx/plugins/plugin-manager](../../../../D:/work/DriFoxx/plugins/plugin-manager/)（运行时实现）
- [plugins/README.md](../README.md)（官方插件索引）
- [plugins/plugin-marketplace/](../plugin-marketplace/)（配套市场插件）
