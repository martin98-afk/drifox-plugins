# file-tree 插件 — DriFox 官方插件

一个基于 DriFox UI 组件机制的「项目文件树浏览」浮动卡片，直观展示当前工作项目的目录结构，支持右键菜单与实时文件监听。

## 功能

| 功能 | 说明 |
|------|------|
| 🌳 **树形文件浏览** | 以树形结构展示当前工作项目的文件和目录，支持异步扫描 |
| 🔍 **智能过滤** | 自动隐藏 `.git/__pycache__/node_modules/.venv` 等常见忽略目录 |
| 🔎 **搜索过滤** | 顶栏搜索框实时过滤树节点，快速定位目标文件 |
| 🖱 **右键菜单** | 复制路径、复制文件名、在资源管理器中打开 |
| 🔄 **实时文件监听** | 已展开的目录自动监听变更并刷新，文件变更防抖处理 |
| 🌓 **主题适配** | 颜色方案自动跟随浅色/深色主题切换 |
| 🔁 **热重载兼容** | 子模块缓存自动清理，避免热重载 `NameError` |

## 依赖

- 无需 Python 第三方包（仅使用 PyQt5 和 stdlib）
- 无需系统命令行工具

## 安装

插件位于 `plugins/file-tree/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\file-tree %USERPROFILE%\.drifox\plugins\file-tree /E /I /Y

# Linux / macOS
cp -r plugins/file-tree ~/.drifox/plugins/
```

启动 DriFox，输入 `/file-tree` 打开文件树卡片。

## 目录结构

```
plugins/file-tree/
├── .drifox-plugin/
│   └── plugin.json              # manifest（components.ui=true）
├── __init__.py                  # Python 包标记
├── ui/
│   ├── __init__.py              # register_ui(registry) 入口
│   └── cards.py                 # FileTreeCard 浮动卡片
└── README.md                    # 本文件
```

## UI 注册接口

UI 插件通过 `ui/__init__.py` 暴露 `register_ui(registry)` 函数，DriFox 启动时由 `UIPluginRegistry.load_plugin` 调用。

```python
def register_ui(registry):
    from .cards import FileTreeCard
    registry.register_floating_card(
        plugin_name="file-tree",
        card_id="file-tree",
        widget_class=FileTreeCard,
        container="bottom",
        title="项目文件树",
        default_visible=False,
    )
```

## 上下文集成

本插件利用 **context_provider 机制**（DriFox 0.5+）自动获取当前项目的路径和名称：

1. DriFox 的 `MainWidget` 在初始化时通过 `UIPluginRegistry.set_context_provider()` 注册全局上下文提供者
2. 用户输入 `/file-tree` 触发卡片显示
3. `UIPluginRegistry._show_floating_card()` 调用 context provider 获取当前项目信息
4. 通过 `widget.set_context(context)` 注入到 `FileTreeCard`
5. 卡片拿到 `project_root` 后启动异步扫描线程加载文件树

### context dict 字段

| 字段 | 类型 | 含义 | 来源 |
|------|------|------|------|
| `project_root` | str | 当前工作目录 | `tool_executor.get_workdir()` |
| `project_name` | str | 当前项目名 | `main_widget._current_project` |
| `session_id` | str | 当前会话 ID | `main_widget._current_session_id` |
| `window_id` | str | 当前窗口 ID | `main_widget._window_id` |
| `colors` | dict | 主题色映射 | `main_widget._build_ui_context()` |
| `is_dark` | bool | 是否深色主题 | `main_widget._build_ui_context()` |

## 技术细节

### 异步目录扫描

使用 `QThread` + `_TreeScanner` 工作器在后台线程中扫描目录，避免阻塞 UI。

- 目录以排序方式展示（目录在前，文件在后，均按名称字母序）
- 仅扫描即时子条目（非递归），展开时再延迟加载子目录
- 扫描结果缓存在 `QTreeWidgetItem` 中，展开时自动填充

### 文件变更监听

已展开的目录自动注册到 `QFileSystemWatcher`，变更时防抖 500ms 后自动刷新。

- 最大监听路径数：50（超出则移除最早展开的路径）
- 仅监听已展开的目录，收起后自动移除监听
- 防抖避免短时间内重复刷新

### 搜索过滤

顶栏搜索框输入关键词，300ms 防抖后对树节点进行递归过滤。

- 匹配名称中包含关键词的节点
- 非匹配节点自动隐藏，但如果是目录且其子节点匹配，则保留父目录

## 设计约束

- 不导入 `app.core` 或 `app.widgets` 内部模块
- 所有文件操作直接通过 stdlib 完成
- 基于 `ctx["project_root"]` 获取项目路径
- 隐藏 `.git/__pycache__/node_modules/.venv` 等常见忽略目录
- 隐藏以 `.` 开头的文件（保留 `.gitkeep` 等特殊文件）

## 参考

- DriFox UI 插件注册表：[DriFoxx/app/core/ui_plugin_registry.py](../../../../D:/work/DriFoxx/app/core/ui_plugin_registry.py)
- context_provider 机制：[DriFoxx/app/main_widget.py](../../../../D:/work/DriFoxx/app/main_widget.py) `_build_ui_context`
- 浮动卡片管理：[DriFoxx/app/widgets/cards/card_manager.py](../../../../D:/work/DriFoxx/app/widgets/cards/card_manager.py)
- 同类插件：[git-dashboard](../git-dashboard/)（数据驱动仪表盘）
