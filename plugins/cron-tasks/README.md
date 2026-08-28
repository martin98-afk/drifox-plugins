# cron-tasks 插件 — DriFox 定时任务中心

> 参考开源项目 [openhanako](https://github.com/)（lib/desk/cron-scheduler.ts + cron-store.ts + AutomationPanel）
> 移植的**可视化定时任务 UI 插件**：在 DriFox 里配置定时任务，到期自动驱动对话执行 prompt。

## 功能特性

- 🕐 **三种任务类型**（对齐 openhanako）：
  - `单次（at）`：指定日期时间执行一次，跑完自动禁用
  - `周期间隔（every）`：每 N 分钟/小时/天
  - `Cron 表达式`：标准 5 字段（分 时 日 月 周），内置解析器支持 `*`、`a-b`、`*/n`、逗号组合、dow `7`=周日
- 🗓 **6 种调度编辑模式**（对齐 openhanako ScheduleEditor）：周期间隔 / 每天 / 每周 / 每月 / 单次 / 高级 Cron，自动互转 + 实时预览人话描述
- 🤖 **任务可绑定智能体**：执行时用所选 agent 的系统提示词 + agent 视角工具集；留空跟随主程序默认
- 💠 **任务可指定模型**：每个服务商的全部模型可选（模型列表展开），执行时覆盖 模型名称；留空跟随当前会话模型
- 📁 **可选工作目录**：任务执行前切换 workdir，结束后自动还原
- ▶️ **手动控制**：启用/禁用开关、立即运行、编辑、删除
- 📜 **运行历史**：每任务保留最近 30 次运行，记录状态/耗时/工具调用次数/智能体/模型/**响应全文**，UI 可查看
- 🔔 **执行通知**：任务开始/结束经主程序 InfoBar 通知
- ✨ **模板快捷新建**：任务列表下方内置常见模板（早报/天气/周报/站会/清理/健康检查），一键预填编辑表单
- ⏱ **调度常驻**：插件加载即启动调度器（30s tick），UI 卡片不开也按时执行
- 🛠 **AI 工具 `cron_tasks`**：大模型可直接建/查/改/删/启停/立即运行定时任务（单工具多 action，无需打开 UI）

## 架构

```
plugins/cron-tasks/
├── .drifox-plugin/plugin.json      # manifest（ui + tools 组件）
├── icons/                          # 时钟图标（深/浅主题）
├── tools/
│   └── cron_tasks.py               # cron_tasks 工具（list/get/create/update/delete/toggle/run）
├── crontasks_core/                 # 核心逻辑（插件根注入 sys.path 自包含）
│   ├── models.py                   # CronJob 数据模型 + cron 解析 + next_run + 人话描述
│   ├── store.py                    # jobs.json 存储 + runs/<jobId>.jsonl 运行历史
│   ├── scheduler.py                # QTimer 调度器（30s tick，串行执行，自愈补算）
│   └── executor.py                 # CronExecutor(QThread) — EngineSession.turn() 驱动对话
└── ui/
    ├── __init__.py                 # register_ui / unload_ui
    ├── cards.py                    # 任务中心卡（列表/编辑/历史三页栈）
    └── controller.py               # 调度器生命周期 + 信号接线 + UI 刷新
```

### 与主程序的边界

对话能力全部经 **UI context services**（`main_widget._build_ui_services` 注入）：

| 服务 | 用途 |
|---|---|
| `create_engine_session` | EP3 契约：`turn(user=..., system=..., tools=..., timeout=...)` 驱动一轮对话（阻塞，QThread 中调用） |
| `get_agent_prompt` / `get_tools_schema` | 组装任务执行上下文（指定 agent 的提示词 + 工具集） |
| `get_workdir` / `set_workdir` | 任务工作目录切换与还原 |
| `notify` | InfoBar 执行通知 |

调度器每次 tick 经 `UIPluginRegistry` 活跃窗口 provider 拉最新 services（多窗口自适应），
拉不到时退回 controller 缓存；无可用 services 时任务推迟到下一轮 tick（不丢任务）。

### 调度设计（对齐 openhanako）

- **调度与执行分离**：调度逻辑不涉及 LLM，只有执行回调驱动对话（确定性代码层）
- **串行执行**：同一时刻仅一个任务在跑（tool_executor 为共享单例，并行会互相干扰）；其余到期任务下一轮 tick 依次派发
- **自愈**：jobs.json 缺失/失效的 next_run_at 自动补算；单次任务过期自动禁用
- **单次执行超时**：20 分钟（对齐 openhanako DEFAULT_CRON_EXECUTION_TIMEOUT_MS）

## 使用方法

1. 输入区点击 **🕐 时钟按钮**（位于「长期记忆」按钮左侧，或命令 `/cron-tasks:tasks`）打开任务中心
2. 点「＋ 新建任务」：填任务名称 + 提示词（到期后让 AI 做什么）
3. 选调度方式（6 种模式，实时预览人话描述）、执行智能体、可选工作目录
4. 保存后任务进入调度；到期自动执行，结果写运行历史并弹通知
5. 任务行内：▶ 立即运行 / ✎ 编辑 / 📜 历史 / 🗑 删除；左上开关启用禁用

任务示例：

| 场景 | 调度方式 | prompt 示例 |
|---|---|---|
| 每天早报 | 每天 09:00 | 「搜索今日 AI 领域重要新闻，汇总成 5 条要点」 |
| 工作日站会提醒 | 高级 Cron `0 9 * * 1-5` | 「提醒：站会时间到」 |
| 每小时检查 | 每 1 小时 | 「检查 D:/work/logs 下最新错误日志并摘要」 |
| 一次性延时 | 单次 `2026-09-01 09:00` | 「生成 9 月工作报告初稿」 |

### AI 工具用法（`cron_tasks`）

大模型经工具调用直接管理任务，`action` 一共 7 个：`list` / `get` / `create` / `update` / `delete` / `toggle` / `run`。

| action | 必填参数 | 说明 |
|---|---|---|
| `list` | — | 列出全部任务（id/调度/状态/下次运行） |
| `get` | `job_id` | 查看单个任务详情（含 prompt 全文） |
| `create` | `type` + `schedule` + `prompt` | 新建任务；可选 `label`/`agent`/`model_key`/`workdir`/`notify`/`enabled` |
| `update` | `job_id` | 修改任务（传哪些字段改哪些） |
| `delete` | `job_id` | 删除任务 |
| `toggle` | `job_id` | 启用/禁用切换 |
| `run` | `job_id` | 立即执行一次 |

`type` 三选一：`at`（schedule=ISO 本地时间 `"2026-09-01T09:00:00"`）、`every`（schedule=分钟数字符串 `"30"`）、`cron`（5 字段 `"30 9 * * 1-5"`）。

数据通路：优先复用 UI 侧调度器单例（写操作即时生效 + 通知 + 卡片刷新）；任务中心未加载时回退 `CronStore` 磁盘直写，调度器下一轮 tick（≤30s）自动同步。

## 数据位置

```
<app_data>/plugin_data/cron-tasks/
├── jobs.json           # 任务列表（可手改，调度器每轮 reload 自愈）
└── runs/<job_id>.jsonl # 运行历史（每任务保留上限见 store.py）
```

> 独立于插件安装目录（v0.2.3 起）：插件更新/重装不丢任务数据。

## 依赖与运行要求

| 依赖 | 说明 |
|------|------|
| DriFox ≥ 0.5.0 | 需支持 `create_engine_session` 服务（EP3 契约）+ `register_input_button` |
| PyQt5 / qfluentwidgets / loguru | UI 与日志 |

## 已知限制

- 串行执行：多任务同时到期时依次排队（间隔 30s tick）
- 调度精度为分钟级（30s tick + cron 分钟粒度）
- 主程序退出时任务不执行（无系统级守护；与 openhanako 常驻进程不同）

## 安装

```bash
# Windows
xcopy plugins\cron-tasks %USERPROFILE%\.drifox\plugins\cron-tasks /E /I /Y
# Linux / macOS
cp -r plugins/cron-tasks ~/.drifox/plugins/cron-tasks
```

启动 DriFox 自动加载；输入区出现 🕐 按钮即安装成功。

## 许可证

MIT — 详见仓库根 LICENSE。
