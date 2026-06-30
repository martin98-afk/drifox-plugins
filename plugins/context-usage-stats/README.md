# context-usage-stats 插件 — DriFox 官方插件

一个基于 DriFox UI 组件机制的「对话上下文用量统计」面板，把 SQLite 里沉淀的会话数据变成可读的图表与统计指标，帮用户回顾 LLM 的真实使用情况。

## 功能

| 功能 | 说明 |
|------|------|
| 📊 **会话活跃度柱状图** | 最近 14 天每天新发起的会话数 |
| 📈 **消息量趋势折线图** | 最近 14 天累计消息数趋势 |
| 🔢 **Token 用量趋势** | 优先从 `context_usage` 列读精确值，缺失时回退到 messages 字段估算 |
| 🗂️ **总体统计** | 总会话数 / 总消息数 / 平均消息数 / 压缩率 |
| 🧩 **项目分布** | 按 project 字段聚合的会话数分布 |
| ⚡ **异步加载** | 数据读取在 `QThread` 后台执行，不阻塞 UI |
| 🌓 **主题适配** | 颜色方案自动跟随浅色 / 深色主题切换 |
| 🔁 **热重载** | 清理 `sys.modules` 中残留的子模块缓存，避免热重载 NameError |

## 安装

插件位于 `plugins/context-usage-stats/`，DriFox 启动时自动发现（需在 `~/.drifox/plugins/` 下有对应目录）。

```bash
# Windows
xcopy plugins\context-usage-stats %USERPROFILE%\.drifox\plugins\context-usage-stats /E /I /Y

# Linux / macOS
cp -r plugins/context-usage-stats ~/.drifox/plugins/
```

启动 DriFox，输入 `/context-usage-stats` 打开统计面板。

## 目录结构

```
plugins/context-usage-stats/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.ui=true）
├── __init__.py              # Python 包标记
├── ui/                      # UI 组件（components.ui=true 必需）
│   ├── __init__.py          # register_ui(registry) 入口
│   └── cards.py             # ContextUsageStatsCard 浮动卡片
└── README.md                # 本文件
```

## UI 注册接口

UI 插件通过 `ui/__init__.py` 暴露 `register_ui(registry)` 函数，DriFox 启动时由 `UIPluginRegistry.load_plugin` 调用。

```python
def register_ui(registry: UIPluginRegistry) -> None:
    from .cards import ContextUsageStatsCard
    registry.register_floating_card(
        plugin_name="context-usage-stats",
        card_id="context-usage-stats",
        widget_class=ContextUsageStatsCard,
        container="bottom",            # 顶部/底部容器
        title="上下文用量统计",
        default_visible=False,
    )
```

`register_floating_card` 会在内部自动为 `card_id` 注册一个同名斜杠命令（本插件即 `/context-usage-stats`），用户通过命令触发卡片的显示/隐藏。

## 数据源

| 数据 | 来源 |
|------|------|
| 会话列表、消息数、创建时间 | `.drifox/sessions.db` 中 `sessions` 表（SQLite） |
| Token 精确值 | `sessions.context_usage` 列（运行时写入） |
| Token 估算值 | 当 `context_usage` 为 0 时，从 `sessions.messages` 字段按经验公式估算（中文 2 字符/token、英文/混合 4 字符/token） |
| 压缩率 | 扫描 `sessions.compaction_state` 中 `"active":true` 的会话数 |

> **设计约束**：卡片不直接依赖 `app.core` / `app.widgets` 内部模块，所有数据读取通过 `sqlite3` 标准库完成，方便独立打包与热重载。

## 与官方 UI 三件套的关系

| 维度 | context-usage-stats | plugin-marketplace | plugin-manager |
|------|:---:|:---:|:---:|
| 浮动卡片 | ✅ | ✅ | ✅ |
| 内容块渲染器 | — | ✅（2 个） | — |
| type | user | system | system |
| 数据源 | `~/.drifox/sessions.db` | `drifox-plugins/marketplace.json` | 文件系统扫描 |

> 建议同时启用 `plugin-marketplace` + `plugin-manager` + `context-usage-stats` 形成完整的「装 / 配 / 卸 / 查」闭环。

## 数据库自动发现顺序

```python
# 1. 开发环境：项目根目录下 .drifox/sessions.db
_DEV_DB_PATH = <plugin>/../../../../.drifox/sessions.db

# 2. 用户环境：~/.drifox/sessions.db（兜底）
_USER_DB_PATH = Path.home() / ".drifox" / "sessions.db"
```

任一存在即使用，全部缺失则在面板上显示「无法连接到数据库」占位文案。

## 与其他组件类型的关系

| 维度 | 说明 |
|------|------|
| 是否触发命令 | 是 — 自动注册 `/context-usage-stats` |
| 是否需要 frontmatter | 否（纯 Python 实现，不走 commands/*.md 流程） |
| 是否需要 hooks | 否 |
| 是否需要 skills | 否 |
| 是否需要 themes | 否 — 卡片内置浅色/深色颜色方案并通过 `isDarkTheme()` 自动切换 |
| 是否需要 mcp / lsp | 否 |

## 参考

- DriFox UI 插件注册表：[DriFoxx/app/core/ui_plugin_registry.py](../../../../D:/work/DriFoxx/app/core/ui_plugin_registry.py)
- 浮动卡片管理：[DriFoxx/app/widgets/cards/card_manager.py](../../../../D:/work/DriFoxx/app/widgets/cards/card_manager.py)
