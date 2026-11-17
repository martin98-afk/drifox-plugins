# git-panel 插件 — DriFox 官方插件

一个基于 DriFox UI 组件机制的「Git 控制面板」浮动卡片，覆盖日常 Git 操作全流程：查看变更、暂存/取消暂存、提交（含 amend）、Stash、分支管理、与远程同步（Push/Pull/Fetch）、Diff 预览。

## 功能

| 功能 | 说明 |
|------|------|
| 📝 **变更视图** | `git status --porcelain=v2` 按「合并更改 / 已暂存的更改 / 更改」分组；**列表与文件树一键切换**（QSettings 记忆），树只展示有变更的目录并保留展开状态；文件名优先、目录弱化，长路径省略并用 tooltip 显示完整路径 |
| ⌨ **键盘与就地操作** | 单击或 Enter 打开 Diff；行尾悬停出现 `+ / − / !` 就地暂存、取消暂存或解决冲突；右键保留放弃修改、复制路径、添加 .gitignore、在文件管理器中显示等完整菜单 |
| 🗂 **变更 / 历史切页** | 变更页只保留提交与文件，历史页显示提交图；切到历史时按需读取日志，不再和分支、搁置列表挤在同屏；底部常驻文件计数或「工作区干净」状态 |
| ➕ **暂存 / 取消暂存 / 放弃** | 单文件与「全部」批量操作；**放弃未暂存修改**按钮常驻（有未暂存修改即显示），一键恢复所有已跟踪修改 + 删除未跟踪文件/目录，已暂存内容不受影响，有确认弹窗保护 |
| 💬 **提交 / Amend** | **多行提交描述框**（右上角内嵌 **AI 生成图标按钮**：根据暂存区 diff 由 LLM 生成提交描述，失败自动重试最多 3 次，自动剥离围栏/引导句/尾注；提示词与模型在系统设置「Git 提交描述生成」配置，留空模型沿用当前窗口）+ **提交模式按钮占满一行**（VSCode 风格右侧下拉切换：提交 / 暂存全部并提交 ｜ 提交并推送，分组分隔线，选中即记忆）；支持 `--amend` 修改上次提交 |
| 📦 **Stash 管理** | 顶栏「更多 → 管理搁置」按需加载列表，支持新建搁置、查看内容、应用并保留、应用并删除、删除；破坏性操作保留确认弹窗 |
| 🌿 **分支管理** | 点击分支徽章打开分支菜单：查看全部分支（含 worktree 占用标记）、新建并切换、切换、删除；长分支名中间省略不撑高头部 |
| ⬆⬇🔄 **远程同步** | 头部紧凑的 ↑ / ↓ / ↻ 按钮：Push（无 upstream 自动 `--set-upstream`）、Pull（`--rebase --autostash` 失败回退普通 pull）、Fetch（`--all --prune`），徽章显示 ahead/behind |
| 📜 **提交历史（Graph 视图）** | 最近 30 条 commit：**并行分支点线图**（分叉斜出/汇合斜入/HEAD 空心高亮，多色区分分支列）+ 分支/标签徽章（当前分支绿、远程蓝、tag 黄）+ 相对时间 + 单行省略描述；**悬停显示详情卡**（作者/完整时间/文件增删统计），**单击展开该提交的文件列表**（+N −M 着色，点击文件看单文件 diff），**双击查看完整 diff**；折叠状态跨刷新记忆 |
| 🧭 **紧凑头部** | 标题行（图标 + 源代码管理 + 刷新 + 更多 + 关闭）与操作区（仓库分支徽章 + 同步按钮 + 提交栏）分离；「更多」集中暂存全部、取消暂存、放弃、搁置、分支、修改上次提交与远程操作 |
| ⌨ **快捷提交** | 提交框支持 Ctrl / ⌘ + Enter；提交模式下拉（提交 / 暂存全部并提交 ｜ 提交并推送）选中即记忆，暂存全部与提交在同一后台事务内完成 |
| 👁 **Diff 预览** | 点击文件路径弹出语法着色 Diff 对话框（右上角叉号关闭），**词级高亮**（difflib 计算 +/- 行新增/删除词）；**未跟踪文件直接预览文件内容**（全新增视图），空文件提示「空文件」 |
| ⚔️ **冲突解决** | 冲突文件（UU/AA/DU 等）显示「解决冲突」菜单：使用 ours / theirs、标记已解决、打开文件 |
| 🖱 **文件右键菜单** | 暂存/取消暂存、放弃修改/未跟踪、复制相对路径、添加到 .gitignore（去重）、在文件管理器中显示 |
| 🔔 **悬浮 InfoBar** | 操作结果以 qfluentwidgets InfoBar **悬浮**提示（成功 3s / 失败 5s / 信息不消失，不占卡片布局，顶部居中滑入）；已有数据时刷新失败只提示不清空当前内容 |
| ⚡ **全异步与按需刷新** | 所有 git 命令经单一串行队列执行，主线程不阻塞；刷新合并为一次，变更页只查 `status_v2`，历史与分支/搁置按需读取；写入期间刷新不丢弃请求；切换仓库后旧回调不会覆盖新项目 |
| 🚀 **轻量渲染** | 文件列表用 `QStandardItemModel + QTreeView` 委托绘制，1000 个变更文件仅约 97 个子控件；数据未变化时不重建模型，保留选择、滚动与树展开；一项变更只重建一次模型（实测 1000 文件首次 10ms、无变化 0.5ms、单文件变更 9ms） |
| 🌓 **主题适配** | 颜色方案自动跟随浅色/深色主题切换，标签与按钮的字体/字号跟随系统主题设置 |
| 🃏 **区块卡片化** | 提交栏浅底容器突出主操作区，历史页保留独立圆角区块 |
| 🔁 **热重载** | 子模块缓存自动清理，避免热重载 NameError |

## 依赖

- `git` 命令行工具（系统已安装即可）
- 宿主需支持 `engine.session` / `model.config` 能力（plugin.json `capabilities` 已声明；缺失会导致「主程序未提供 create_engine_session 服务」报错）
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
│   ├── changes_view.py      # 变更列表/文件树（QStandardItemModel + 委托绘制）
│   ├── task_runner.py       # 串行后台任务队列（合并刷新、丢弃过期回调）
│   ├── diff_renderer.py     # diff → 词级高亮 HTML 纯函数渲染器
│   └── cards.py             # GitPanelCard 浮动卡片 + 菜单 + Diff/Commit 对话框
├── tests/
│   ├── test_smoke.py        # GitRepo 端到端 + 渲染器/解析器单元测试（stdlib unittest）
│   ├── test_ui_p1.py        # P1 UI 功能验证（offscreen 平台）
│   ├── test_workflow.py     # 列表/树切换、选择保留、任务串行回归
│   └── bench_refresh.py     # 固定输入的渲染基准（100 / 1000 文件）
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

- 所有 git 写操作经 `task_runner.TaskRunner` 串行执行，刷新同类请求合并；回调在主线程分发
- 变更页读取 `status_v2`（分支 / ahead / behind / 文件状态一次子进程），日志、分支、搁置按需读取
- 后台任务捕获仓库路径和请求版本，切仓库后旧结果直接丢弃；任务对象保活到真正结束，销毁不阻塞等待网络
- 文件列表使用 `QStandardItemModel`，同一快照不重建模型，选择、滚动、目录展开跨刷新保留
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

## LLM 调用通道（重要）
本插件的 AI 生成提交描述走宿主 `services["create_engine_session"]`（EP3 契约），
经 ModelAdapter / Serializer / Transport 三层分派发出请求。

**不要**自建 openai client 直发 `chat.completions.create`：那会绕过三层分派，
导致服务商伪装头缺失（CodeBuddy `X-Product` + 动态 `Authorization`、OpenCode
`x-opencode-session`）→ 401 / 400 MissingSessionID，且 GPT-5 系应走
`/v1/responses`、思考参数映射与智能重试全部失效。

取配置仍走 `get_provider_config`；两者分工：前者管「发给谁」，后者管「怎么发」。

生成失败（网络抖动/服务商 429、5xx/思考型模型空输出）自动重试最多 3 次（指数退避），
用户主动取消不重试；回填前自动剥离 ``` 围栏、「好的/以下是」引导句、
Co-Authored-By 尾注与 `<think>` 块。

## 密钥获取（重要）
插件需要「切到指定服务商跑一次 LLM 调用」时，**必须**经宿主公开服务取配置：
```python
cfg = ctx["services"]["get_provider_config"]("MiniMax", "MiniMax-M2.7")
# → {"API_KEY": "sk-…已解密明文", "API_URL": "…", "模型名称": …}
```
**不要**自行 `json.load(~/.drifox/app.config)` 取 `LLM.SavedProviders[*].API_KEY`：
主程序 `SecretMode` 非 `none` 时，该字段是密文（`password` 模式 `enc:v2:…`）
或空串（`keyring` 模式密钥已入系统凭证库），拿去发请求会得到
`401 log in fail: Please carry the API secret key`。只有主程序内存态持有明文。

服务商/模型两级下拉走能力池 `provider.list` / `model.enumerate`（内存态，不含
密钥）；能力不可用（旧宿主 / 无活跃窗口）时下拉为空，已存配置保留不丢。取完整
配置（含明文 key）优先 `ctx["services"]["get_provider_config"]`，无上下文时走
能力池 `model.config`（`pool_for(...).legacy("get_provider_config", "model.config")`，
两者同签名）。绝不读磁盘 `app.config`。
