# project-dashboard 插件 — DriFox 官方插件

项目信息看板 — 在欢迎卡片新增「📊 项目看板」tab，用 **echarts** 展示当前 git 仓库的 commit 趋势、语言分布、贡献者与文件统计。

## 功能

| 功能 | 说明 |
|------|------|
| 📊 **欢迎卡片 tab** | 在欢迎卡片新增「📊 项目看板」tab，与会话/更新等 tab 并列 |
| 📈 **近 30 天 Commit 趋势** | 按日聚合 commit 数柱状图（echarts） |
| 👥 **贡献者 Top** | `git shortlog` 统计贡献者 commit 数横向条形图 |
| 🗂 **语言分布** | 按扩展名归类语言，环形图展示文件数占比 |
| 📄 **文件类型 Top** | 常见文件扩展名数量横向条形图 |
| 🌓 **明暗适配** | 图表配色跟随 Qt 主题（读 `ctx["is_dark"]`） |
| ⚡ **异步采集** | git/文件系统扫描在 `QThread` 后台执行，不阻塞 UI 主线程 |
| 🔁 **缓存失效** | 缓存 key = git 根 + HEAD + 日期，提交变化自动重采 |

## 依赖

- **git** 命令行工具（系统已安装即可）
- **DriFox ≥ 0.4.15**：欢迎卡片骨架需加载 echarts vendor（`window.echarts` 存在），
  见主程序 `app/widgets/message_card.py` `_load_skeleton`（`_SKELETON_CACHE_VERSION >= 9`）
- 无需 Python 第三方包（`PyQt5`/`loguru` 由 DriFox 运行时提供）

## 安装

插件位于 `plugins/project-dashboard/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\project-dashboard %USERPROFILE%\.drifox\plugins\project-dashboard /E /I /Y

# Linux / macOS
cp -r plugins/project-dashboard ~/.drifox/plugins/
```

启动 DriFox，在欢迎卡片点击「📊 项目看板」tab 查看图表。

## 目录结构

```
plugins/project-dashboard/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.ui=true）
├── __init__.py              # Python 包标记
├── ui/
│   ├── __init__.py          # register_ui(registry) → register_welcome_tab
│   ├── collector.py         # QThread 异步采集 + 模块级缓存 + 欢迎卡片重渲染
│   └── dashboard.py         # git/文件统计采集 + echarts option 生成（纯 stdlib）
├── icon.svg / icon_dark.svg # 插件图标
└── README.md                # 本文件
```

## UI 注册接口

UI 插件通过 `ui/__init__.py` 暴露 `register_ui(registry)` 函数，DriFox 启动时由 `UIPluginRegistry.load_plugin` 调用。

```python
def register_ui(registry: UIPluginRegistry) -> None:
    registry.register_welcome_tab(
        plugin_name="project-dashboard",
        mode_key="project-dashboard",   # 避开内置 sessions/projects/changelog
        label="📊 项目看板",
        render_func=_render_welcome_tab,
        priority=0,
    )
```

## 渲染链路

`render_func` 返回 markdown 片段（概要行 + ` ```echarts ` 代码块），拼进欢迎卡片 body 后走主程序 markdown 管线：

```
```echarts {JSON}
→ _wrap_code_blocks_with_copy_button_web（lang=="echarts"）
→ echarts-container div（data-echarts-json=base64）
→ 骨架 JS if(window.echarts) → echarts.init 渲染
```

## 数据源

| 数据 | Git 命令 / 来源 |
|------|----------------|
| 仓库名 / 分支 | `git rev-parse --show-toplevel` / `git branch --show-current` |
| Commit 趋势 | `git log --since=30 days ago --pretty=format:%ad --date=short` → 按日聚合 |
| 贡献者 Top | `git shortlog -sne --no-merges HEAD`（取前 8，去 email） |
| 语言分布 | 文件系统扫描，扩展名映射语言（跳过 `.git`/`node_modules` 等噪音目录） |
| 文件类型 | 扩展名计数 Top 10 |

## 设计约束

- 不导入 `app.core` 或 `app.widgets` 内部模块（仅通过 `UIPluginRegistry` 实例回调）
- `render_func` 主线程同步调用 → 数据采集全部异步（QThread worker 单例，幂等启动）
- git 命令通过 `subprocess.run()` 完成，单次超时 8 秒，失败静默降级；Windows 下加 `CREATE_NO_WINDOW` 隐藏子进程控制台窗口
- 性能：语言/文件类型扫描仅对已知文本扩展名读取行数（二进制/未知扩展名只计数），行数统计用线程池并行；`build_cache_key` 的 HEAD 查询带 5s TTL 缓存，避免主线程频繁启动 git 子进程
- 项目根解析：主程序渲染 welcome tab 只注入 `is_dark`，插件用候选链解析 project_root（活跃窗口 provider → 全部窗口 provider → 全局兼容 provider），逐级 `find_git_root` 验证，全部无效返回空串显示友好提示；**不回退 `os.getcwd()`**（软件启动目录/源码根本身可能是 git 仓库，会把启动目录误当项目根展示其 git 信息，见 v0.2.2 修复）；error 采集结果缓存 60s TTL，避免错误被永久固定
- 热重载：`register_ui` 清理 `ui_plugin_project_dashboard.` sys.modules 前缀

## 参考

- DriFox UI 插件注册表：[app/core/ui_plugin_registry.py](../../../../D:/work/DriFox/app/core/ui_plugin_registry.py)
- 欢迎卡片渲染：[app/widgets/message_card.py](../../../../D:/work/DriFox/app/widgets/message_card.py) `_render_welcome_body`
- 同类插件：[context-stats](../context-stats/)（欢迎卡片用量统计）、[git-dashboard](../git-dashboard/)（Git 仪表盘浮动卡片）
