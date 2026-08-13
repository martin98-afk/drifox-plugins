# context-stats 插件 — DriFox 官方插件

欢迎卡片用量统计 — 在欢迎卡片新增「📊 用量」tab，用 **echarts** 展示模型上下文（token）用量与消息量趋势。

## 功能

| 功能 | 说明 |
|------|------|
| 📊 **欢迎卡片 tab** | 在欢迎卡片新增「📊 用量」tab，与会话/更新 tab 并列 |
| 🔤 **上下文用量趋势** | 近 14 天估算 token 用量面积图（echarts） |
| 📈 **消息量趋势** | 近 14 天每日消息量柱状图（echarts） |
| 🌓 **明暗适配** | 图表配色跟随 Qt 主题（读 `ctx["is_dark"]`） |
| ⚡ **模块级缓存** | 数据按 db mtime + 日期 + 60s TTL 缓存，切换 tab 不重复查询 |

## 依赖

- **DriFox ≥ 0.4.15**：欢迎卡片骨架需加载 echarts vendor（`window.echarts` 存在），
  见主程序 `app/widgets/message_card.py` `_load_skeleton`（`_SKELETON_CACHE_VERSION >= 9`）
- 无需 Python 第三方包

## 安装

插件位于 `plugins/context-stats/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\context-stats %USERPROFILE%\.drifox\plugins\context-stats /E /I /Y

# Linux / macOS
cp -r plugins/context-stats ~/.drifox/plugins/
```

启动 DriFox，在欢迎卡片点击「📊 用量」tab 查看图表。

## 目录结构

```
plugins/context-stats/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.ui=true）
├── __init__.py              # Python 包标记
├── ui/
│   ├── __init__.py          # register_ui(registry) → register_welcome_tab
│   ├── data.py              # SQLite 读取（近 14 天聚合 + token 估算 + 模块级缓存）
│   └── render.py            # echarts option 生成（明暗适配）
├── icon.svg / icon_dark.svg # 插件图标
└── README.md                # 本文件
```

## UI 注册接口

UI 插件通过 `ui/__init__.py` 暴露 `register_ui(registry)` 函数，DriFox 启动时由 `UIPluginRegistry.load_plugin` 调用。

```python
def register_ui(registry: UIPluginRegistry) -> None:
    from .render import render_welcome_tab
    registry.register_welcome_tab(
        plugin_name="context-stats",
        mode_key="context-stats",   # 避开内置 sessions/projects/changelog
        label="📊 用量",
        render_func=render_welcome_tab,
    )
```

## 渲染链路

`render_func` 返回 markdown 片段（含 ` ```echarts ` 代码块），拼进欢迎卡片 body 后走主程序 markdown 管线：

```
```echarts {JSON}
→ _wrap_code_blocks_with_copy_button_web（lang=="echarts"）
→ echarts-container div（data-echarts-json=base64）
→ 骨架 JS if(window.echarts) → echarts.init 渲染
```

## 数据源

| 数据 | 来源 |
|------|------|
| token 用量 | `.drifox/sessions.db` `sessions.context_usage` 按日求和；缺失/为 0 的旧会话用 `messages` 文本快速估算 |
| 消息量 | `sessions.message_count` 按日求和 |
| 窗口 | 近 14 天，排除 `__archived__%` 项目 |

## 设计约束

- 不导入 `app.core` 或 `app.widgets` 内部模块
- SQLite 通过 `sqlite3` stdlib 直读（只读连接）
- `render_func` 主线程同步调用 → 查询轻量聚合 + 模块级缓存（db mtime + 日期作 key，60s TTL 防快速切 tab 反复查询）
- 性能：聚合查询合并为单次全表扫描（轻量列）；回退估算在 SQL 侧 `substr` 截断 + `LIMIT` 限制，避免超大 `messages` 字段全量传输；token 估算用 `str.translate` 删除表（C 层）替代逐字符循环
- 热重载：`register_ui` 清理 `ui_plugin_context_stats.` sys.modules 前缀

## 参考

- DriFox UI 插件注册表：[app/core/ui_plugin_registry.py](../../../../D:/work/DriFox/app/core/ui_plugin_registry.py)
- 欢迎卡片渲染：[app/widgets/message_card.py](../../../../D:/work/DriFox/app/widgets/message_card.py) `_render_welcome_body`
- 数据模式参考：`context-usage-stats`（DriFox 运行时内置）
- 同类插件：[git-dashboard](../git-dashboard/)（浮动卡片 UI）
