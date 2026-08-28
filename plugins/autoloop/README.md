# AutoLoop 插件 — DriFox 官方插件

> AutoLoop 自动循环模式：规划 → 执行 → 归档 三阶段长任务自动执行。
> 对话引擎插件化首例：从 DriFox 主程序 `app/core/engines/auto_loop/` 整体迁移而来。

## 简介

AutoLoop 是 DriFox 的「长任务自动循环」执行模式。它把单个用户任务拆解为：

1. **规划阶段**：智能体只允许只读 + 笔记写入工具，强制输出可拆解的执行计划并写入 `SHARED_TASK_NOTES.md`
2. **执行阶段**：按计划逐轮迭代，每轮必须运行验证命令、记录结果、接力文档只追加不覆盖
3. **归档阶段**：清理临时文件、归档日志、生成任务元信息索引

三阶段通过 `PLANNING_COMPLETE` / `MISSION_COMPLETE` / `ARCHIVE_COMPLETE` 信号驱动，**`MISSION_COMPLETE` 必须连续 3 次输出** 才真正结束循环（防止误判提前完成）。

## 功能特性

- ♾️ 输入区工具栏新增「AutoLoop」按钮，一键弹出配置卡
- ⚙️ 配置卡：填任务描述 + 调整循环上限（迭代次数 / token 上限 / 时长上限 / 完成阈值）
- ▶️ 运行卡：覆盖对话区，实时显示当前轮次 / token 消耗 / 累计时长 / 当前阶段
- 🛑 运行中可手动停止 / 归档结束
- 🔁 Worker 自建 `ConversationCore` 执行栈，不依赖主程序 UIEngine 实例
- 🔌 全部对话能力经 UI context services 注入（`main_widget._build_ui_services`），与主程序结构松耦合

## 迁移来源

本插件从 DriFox 主程序内置对话引擎 **整体迁移**而来。源路径：

```
DriFox/app/core/engines/auto_loop/
```

迁移到独立插件目录 `plugins/autoloop/`，目的是让对话引擎本身也可以作为用户插件分发、独立迭代。代码结构与运行行为保持一致：

| 模块 | 职责 |
|------|------|
| `autoloop_core/config.py` | `AutoLoopConfig` 数据类（迭代/token/时长上限 + 完成信号/任务笔记路径等） |
| `autoloop_core/engine.py` | `AutoLoopEngine` 状态机（纯逻辑，无 Qt） |
| `autoloop_core/prompt_composer.py` | 三阶段提示词模板（规划/执行/归档） |
| `autoloop_core/adapter.py` | 线程同步对话适配器（`threading.Event` 等待 Worker 完成） |
| `autoloop_core/worker.py` | `AutoLoopWorker`（QThread 主循环） |
| `ui/cards.py` | 配置卡 + 运行卡（full 覆盖层） |
| `ui/controller.py` | Worker 生命周期 / 信号接线 / 多窗口会话管理 |
| `ui/__init__.py` | `register_ui`：注册两张浮动卡 + 输入区按钮 |
| `agents/auto_loop.md` | `@auto_loop` 智能体定义（三阶段规则 + 接力文档格式 + 验证策略） |

## 架构

```
plugins/autoloop/
├── .drifox-plugin/plugin.json     # manifest（ui + agents）
├── __init__.py                    # 标记为 Python 包
├── agents/auto_loop.md            # @auto_loop 智能体定义
├── icons/                         # 工具栏按钮图标（深 / 浅）
├── autoloop_core/                 # 核心逻辑（插件根注入 sys.path 自包含）
│   ├── config.py
│   ├── engine.py
│   ├── prompt_composer.py
│   ├── adapter.py
│   ├── worker.py
│   └── __init__.py
└── ui/
    ├── __init__.py                # register_ui
    ├── cards.py                   # 配置卡 + 运行卡
    └── controller.py              # Worker 生命周期
```

## 与主程序的边界

对话能力全部经 **ui context services**（`main_widget._build_ui_services` 注入）：

| 服务 | 用途 |
|---|---|
| `get_model_config` / `get_tool_executor` / `get_agent_manager` | 驱动自建 `ConversationCore` |
| `get_tools_schema("auto_loop")` | agent 视角工具集（deny 过滤） |
| `set_workdir` / `get_workdir` / `sync_working_directory` | 工作目录管理 |
| `enter/exit_exclusive_ui_mode` | 运行期独占锁定（隐藏输入区 / 禁新建会话） |
| `save_messages_to_session` | 结束后消息并入当前会话 |
| `hide_card` / `notify` | 卡片切换与 InfoBar 通知 |

Worker 内部通过 `ConversationCore.create()` 自建执行栈，**不依赖主程序 UIEngine 实例**，因此卸载 / 热替换不影响运行中的对话循环（worker 仅在卡片 destroyed 时取消）。

## 使用方法

1. 在输入区点击工具栏 **♾** 按钮（或输入 `/autoloop:config`）
2. 弹出配置卡：填任务描述、调整循环上限
3. 点击「开始」→ 全屏切换到运行卡，显示进度（轮次 / token / 时长 / 阶段）
4. 运行中可点「停止」随时终止，归档时点「归档」收尾
5. 全局单会话：任一时刻仅一个 AutoLoop 循环在跑

## 依赖与运行要求

> **本插件为「主程序配套型」插件**，需要 DriFox 主程序提供 UI context services 与对话栈接口才能完整运行。

| 依赖 | 说明 |
|------|------|
| DriFox ≥ 0.5.0 | 主程序需支持 `UIPluginRegistry.load_plugin` + `main_widget._build_ui_services` 注入约定 |
| PySide6 | UI 控件 |
| loguru | 日志 |
| watchfiles | 热重载 |

执行栈构建经主程序 services `conversation_stack()` 入口注入（EP2 契约：`app/plugins/contracts/conversation_stack.py`），`worker.py` 不再模块级 deep import `ConversationCore`/`ConversationExecutor`（仅 config 家族与 fallback 兼容路径保留少量延迟 import）。主程序需 ≥ 0.5.0 且提供该服务键。

## 热重载

- `ui/` / `autoloop_core/` 文件改动 → `watchfiles` 自动重载
- `register_ui` 入口显式清理 `sys.modules` 中的 `ui_plugin_autoloop.*` 与 `autoloop_core.*` 缓存，确保重新编译
- 运行中卸载插件 → `controller` 经卡片 `destroyed` 信号取消 worker 并收尾

## 智能体要点（`agents/auto_loop.md`）

- `mode: subagent` / `hidden: true`：不暴露给普通 `@` 切换，仅由 AutoLoop Worker 内部委派
- `steps: 100` + `permission: { "*": allow, "question/...": deny }`：禁用追问、todo 工具、子智能体委派，防止循环逃逸
- 三阶段规则（规划 / 执行 / 归档）与「接力文档 `SHARED_TASK_NOTES.md`」格式强制约束
- 每轮独立日志写入 `.autoloop/logs/round_XXX.md`，归档时同步到 `.autoloop/archive/latest/`

## 已知限制

- 全局单 AutoLoop 会话；多窗口也共享同一 worker 实例（按 `window_id` 隔离会话而非多实例）
- 规划阶段硬性禁用 `edit/bash/delete` 等修改工具（仅 `write` 写笔记 + 扫描工具），防止「规划时偷偷改代码」
- `MISSION_COMPLETE` 需连续 3 次输出才真正结束（防止智能体一次草率收尾）

## 安装

```bash
# Windows
xcopy plugins\autoloop %USERPROFILE%\.drifox\plugins\autoloop /E /I /Y
# Linux / macOS
cp -r plugins/autoloop ~/.drifox/plugins/autoloop
```

启动 DriFox，插件会被自动发现并加载（依赖主程序 UI services 与对话栈）。

## 许可证

MIT — 详见仓库根 LICENSE。