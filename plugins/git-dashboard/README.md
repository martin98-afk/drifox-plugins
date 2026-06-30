# git-dashboard 插件 — DriFox 官方插件

一个基于 DriFox UI 组件机制的「Git 仓库可视化仪表盘」，在当前工作目录的 git 仓库上构建 GitHub 风格的提交日历、最近提交列表和分支图。

## 功能

| 功能 | 说明 |
|------|------|
| 🔀 **头部状态栏** | 仓库名、当前分支、与 upstream 的 ahead/behind 差异数 |
| ☀ **提交日历热力图** | GitHub 贡献图风格，展示过去一年每天的提交数，5 级颜色密度 |
| 📜 **最近提交列表** | 最近 20 条 commit，彩色 hash + 描述 |
| 🌿 **分支图** | `git log --graph` 可视化，等宽字体渲染分支线 |
| ⚡ **异步加载** | 所有 git 命令在 `QThread` 后台执行，不阻塞 UI |
| 🌓 **主题适配** | 颜色方案自动跟随浅色/深色主题切换 |
| 🔁 **热重载** | 子模块缓存自动清理，避免热重载 NameError |

## 依赖

- `git` 命令行工具（系统已安装即可）
- 无需 Python 第三方包

## 安装

插件位于 `plugins/git-dashboard/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\git-dashboard %USERPROFILE%\.drifox\plugins\git-dashboard /E /I /Y

# Linux / macOS
cp -r plugins/git-dashboard ~/.drifox/plugins/
```

启动 DriFox，输入 `/git-dashboard` 打开仪表盘。

## 目录结构

```
plugins/git-dashboard/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.ui=true）
├── __init__.py              # Python 包标记
├── ui/
│   ├── __init__.py          # register_ui(registry) 入口
│   └── cards.py             # GitDashboardCard 浮动卡片
└── README.md                # 本文件
```

## UI 注册接口

UI 插件通过 `ui/__init__.py` 暴露 `register_ui(registry)` 函数，DriFox 启动时由 `UIPluginRegistry.load_plugin` 调用。

```python
def register_ui(registry: UIPluginRegistry) -> None:
    from .cards import GitDashboardCard
    registry.register_floating_card(
        plugin_name="git-dashboard",
        card_id="git-dashboard",
        widget_class=GitDashboardCard,
        container="bottom",
        title="Git 仪表盘",
        default_visible=False,
    )
```

## 上下文集成

本插件利用 **context_provider 机制**（DriFox 0.5+）自动获取当前项目的路径和名称：

1. DriFox 的 `MainWidget` 在初始化时通过 `UIPluginRegistry.set_context_provider()` 注册全局上下文提供者
2. 用户输入 `/git-dashboard` 触发卡片显示
3. `UIPluginRegistry._show_floating_card()` 调用 context provider 获取当前项目信息
4. 通过 `widget.set_context(context)` 注入到 `GitDashboardCard`
5. 卡片拿到 `project_root` 后启动 `QThread` 执行 git 命令采集数据

### context dict 字段

| 字段 | 类型 | 含义 | 来源 |
|------|------|------|------|
| `project_root` | str | 当前工作目录（git 仓库根） | `tool_executor.get_workdir()` |
| `project_name` | str | 当前项目名 | `main_widget._current_project` |
| `session_id` | str | 当前会话 ID | `main_widget._current_session_id` |
| `window_id` | str | 当前窗口 ID | `main_widget._window_id` |

## 数据源

| 数据 | Git 命令 |
|------|---------|
| 仓库名 | `git rev-parse --show-toplevel` → basename |
| 当前分支 | `git branch --show-current` |
| ahead/behind | `git rev-list --left-right --count HEAD...@{u}` |
| 提交日历 | `git log --after=1 year ago --format=%ai --all --no-merges` → 按日聚合 |
| 最近提交 | `git log -n20 --oneline --decorate --no-merges` |
| 分支图 | `git log --all --oneline --graph -n30 --decorate` |

## 设计约束

- 不导入 `app.core` 或 `app.widgets` 内部模块
- 所有 git 命令通过 `subprocess.run()` 完成
- 单次 git 命令超时 5 秒
- 颜色方案通过 `isDarkTheme()` 自动跟随主题

## 参考

- DriFox UI 插件注册表：[DriFoxx/app/core/ui_plugin_registry.py](../../../../D:/work/DriFoxx/app/core/ui_plugin_registry.py)
- context_provider 机制：[DriFoxx/app/main_widget.py](../../../../D:/work/DriFoxx/app/main_widget.py) `_build_ui_context`
- 浮动卡片管理：[DriFoxx/app/widgets/cards/card_manager.py](../../../../D:/work/DriFoxx/app/widgets/cards/card_manager.py)
- 同类插件：[context-usage-stats](../context-usage-stats/)（数据驱动仪表盘）
