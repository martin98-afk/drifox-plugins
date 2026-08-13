# git-panel 插件 — DriFox 官方插件

一个基于 DriFox UI 组件机制的「Git 控制面板」浮动卡片，覆盖日常 Git 操作全流程：查看变更、暂存/取消暂存、提交（含 amend）、Stash、分支管理、与远程同步（Push/Pull/Fetch）、Diff 预览。

## 功能

| 功能 | 说明 |
|------|------|
| 📝 **文件变更列表** | `git status --porcelain` 实时展示已暂存 / 未暂存变更，**VSCode 风格状态字母**（M/A/D/R/U/! + 颜色）区分类型，长路径自动换行不撑宽侧栏 |
| ➕ **暂存 / 取消暂存 / 放弃** | 单文件与「全部」批量操作；**放弃未暂存修改**按钮常驻（有未暂存修改即显示），一键恢复所有已跟踪修改 + 删除未跟踪文件/目录，已暂存内容不受影响，有确认弹窗保护 |
| 💬 **提交 / Amend** | 提交消息输入框，支持 `--amend` 修改上次提交 |
| 📦 **Stash 管理** | 创建 / 列表 / 应用 / 弹出 / 删除，一键保存工作进度 |
| 🌿 **分支管理** | 查看当前分支、创建并切换、切换分支、删除分支（长分支名自动换行） |
| ⬆⬇🔄 **远程同步** | Push（无 upstream 自动 `--set-upstream`）、Pull（`--rebase --autostash` 失败回退普通 pull）、Fetch（`--all --prune`），头部显示 ahead/behind 数量 |
| 📜 **提交历史** | 最近 30 条 commit，彩色 hash + 作者 + 日期 + 描述 + 引用标签；**双击查看详情**（元信息 + 完整 diff，hash 点击复制） |
| 🧭 **两行头部** | 标题行（图标+标题+状态+刷新+关闭）与信息行（**分支徽章**+Push/Pull/Fetch）分离，长分支名中间省略不撑高头部 |
| 👁 **Diff 预览** | 点击文件路径弹出语法着色 Diff 对话框（右上角叉号关闭），**词级高亮**（difflib 计算 +/- 行新增/删除词）；**未跟踪文件直接预览文件内容**（全新增视图），空文件提示「空文件」 |
| ⚔️ **冲突解决** | 冲突文件（UU/AA/DU 等）显示「解决冲突」菜单：使用 ours / theirs、标记已解决、打开文件 |
| 🖱 **文件右键菜单** | 暂存/取消暂存、放弃修改/未跟踪、复制相对路径、添加到 .gitignore（去重）、在文件管理器中显示 |
| 🔔 **悬浮 InfoBar** | 操作结果以 qfluentwidgets InfoBar **悬浮**提示（成功 3s / 失败 5s / 信息不消失，不占卡片布局，顶部居中滑入） |
| ⚡ **全异步** | 所有 git 命令在 `QThread` 后台执行，不阻塞 UI；刷新时 6 个查询（状态/分支/日志等）**线程池并行执行**，耗时降至最慢单个查询；同步操作按钮置灰防重复，刷新中操作不静默丢弃 |
| 🌓 **主题适配** | 颜色方案自动跟随浅色/深色主题切换 |
| 🃏 **区块卡片化** | 变更/搁置/分支/提交历史各区块独立圆角卡片，提交栏浅底容器突出主操作区 |
| 🔁 **热重载** | 子模块缓存自动清理，避免热重载 NameError |

## 依赖

- `git` 命令行工具（系统已安装即可）
- 无需 Python 第三方包（运行时依赖 PyQt5 / qfluentwidgets，由 DriFox 提供）

## 安装

插件位于 `plugins/git-panel/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\git-panel %USERPROFILE%\.drifox\plugins\git-panel /E /I /Y

# Linux / macOS
cp -r plugins/git-panel ~/.drifox/plugins/
```

启动 DriFox，输入 `/git-panel` 打开控制面板（默认停靠在**左侧边栏**，VSCode 同款体验，宽度可拖拽调节）。

## 目录结构

```
plugins/git-panel/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.ui=true，含 icon）
├── __init__.py              # Python 包标记
├── ui/
│   ├── __init__.py          # register_ui(registry) 入口
│   ├── git_core.py          # GitRepo / GitResult 封装层（所有 git 命令入口）
│   ├── diff_renderer.py     # diff → 词级高亮 HTML 纯函数渲染器
│   └── cards.py             # GitPanelCard 浮动卡片 + 行控件 + Diff/Commit 对话框
├── tests/
│   ├── test_smoke.py        # GitRepo 端到端 + 渲染器/解析器单元测试（stdlib unittest）
│   └── test_ui_p1.py        # P1 UI 功能验证（offscreen 平台）
└── README.md                # 本文件
```

## UI 注册接口

UI 插件通过 `ui/__init__.py` 暴露 `register_ui(registry)` 函数，DriFox 启动时由 `UIPluginRegistry.load_plugin` 调用。

```python
def register_ui(registry: UIPluginRegistry) -> None:
    from .cards import GitPanelCard
    registry.register_floating_card(
        plugin_name="git-panel",
        card_id="git-panel",
        widget_class=GitPanelCard,
        container="left",   # 默认停靠左侧边栏（VSCode 同款体验，可 move_floating_card 换位）
        title="Git 面板",
        default_visible=False,
    )
```

## 上下文集成

本插件利用 **context_provider 机制**（DriFox 0.5+）自动获取当前项目的路径：

1. DriFox 的 `MainWidget` 通过 `UIPluginRegistry.set_context_provider()` 注册全局上下文提供者
2. 用户输入 `/git-panel` 触发卡片显示
3. `_apply_latest_theme()` 从 context 读取 `project_root` 作为仓库路径

### context dict 字段

| 字段 | 类型 | 含义 | 来源 |
|------|------|------|------|
| `project_root` | str | 当前工作目录（git 仓库根） | `tool_executor.get_workdir()` |
| `colors` | dict | 主题色板 | `main_widget._build_ui_context` |

## 架构说明

```
GitPanelCard (UI 层)
    │  调用
    ▼
GitRepo (git_core.py 封装层)  ←── 统一返回 GitResult(ok, stdout, stderr, code)
    │
    ▼
_run_git (git_core.py)  ←── 唯一 subprocess 执行点（QThread 外执行）

依赖方向：cards.py → git_core.py（单向，git_core 仅 stdlib）
```

- 所有 git 操作走 `_Worker` + `QThread` 异步模式，回调中更新 UI
- `GitRepo.status()` 保留 porcelain 前导空格（`strip=False`），保证暂存/工作区判定正确
- Push / Pull 失败时自动重试降级路径，完整 stderr 写入 loguru 日志并显示状态栏摘要

## 设计约束

- 不导入 `app.core` 或 `app.widgets` 内部模块
- 所有 git 命令通过 `subprocess.run()` 完成，单次超时 15 秒
- 同步操作期间按钮置灰，避免并发触发

## 参考

- DriFox UI 插件注册表：`DriFox/app/core/ui_plugin_registry.py`
- context_provider 机制：`DriFox/app/main_widget.py`
- 同类插件：[git-dashboard](../git-dashboard/)（可视化仪表盘，与本面板互补）
