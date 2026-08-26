# CronChat 插件 — DriFox 官方插件

> 定时任务对话引擎：定时触发自动化对话任务，到点自动执行，结果存运行记录并通知。

把 DriFox 的对话能力放到时间轴上：你设定频率与提示词，指定时间一到 DriFox 自动以该提示词驱动一次「带工具的自主对话」（LLM 可自主调用工具完成多步任务），执行完成后通过 InfoBar 通知你，并在「运行记录」页可查阅全文。

## 简介

CronChat 提供三种调度频率：

- **周期**：每天 / 每周（多选星期几）固定时刻执行
- **按间隔**：每 N 分钟（5–10080）滚动执行
- **单次**：指定日期时间执行一次后自动禁用

并支持：

- 生效日期区间（可选，留空表示始终生效）
- 允许使用工具（默认开；关闭后该任务仅凭模型已有知识对话，不调用任何工具）
- 立即运行（手动触发，不影响下次调度）

## 功能特性

- 🕒 输入区工具栏新增「⏰ 定时」按钮，一键弹出主卡
- 📋 任务列表：空状态引导 + 12 个内置模板一键预填
- ✏️ 编辑页：表单化配置（名称/提示词/频率/生效区间/开关）
- 🕘 运行记录：执行流（状态/耗时/结果摘要）+ 点击行展开全文
- 📨 执行结束 InfoBar 通知（成功/超时/失败三种消息）
- 🔌 对话能力经主程序 `services["create_engine_session"]`（EP3）注入，不依赖主程序 UIEngine

## 12 个内置模板

| 模板 | 频率 | 简介 |
|---|---|---|
| 每日 AI 新闻推送 | 每天 09:00 | AI coding + 具身智能方向 3-5 条要点 |
| 每日 5 个英语单词 | 每天 08:00 | 音标/词性/例句/记忆技巧 |
| 每日儿童睡前故事 | 每天 20:30 | 3-5 分钟温馨小狐狸故事 |
| 每周工作周报 | 周五 17:00 | 汇总当前仓库 PR/Issue 进展 |
| 经典电影推荐 | 周六 20:00 | 介绍剧情与推荐理由（不剧透） |
| 历史上的今天 | 每天 12:00 | 科技/电影/音乐等领域挑一件大事 |
| 每日一个为什么 | 每天 10:00 | 物理/生物/天文等有趣科学问题 |
| 父母联系提醒 | 周日 10:00 | 问候语 + 两个聊天话题 |
| 体检预约提醒 | 单次（默认） | 体检前注意事项清单 |
| 面试准备提醒 | 每 120 分钟 | 大模型面试要点复习卡 |
| 会议前准备 | 每天 09:30 | 议题/目标/效率建议 |
| 可爱萌宠手机壁纸 | 每天 08:30 | 7 种风格随机画面描述 |

## 架构

```
plugins/cron-chat/
├── .drifox-plugin/plugin.json     # manifest（ui + config_schema）
├── __init__.py
├── README.md
├── icons/
│   ├── 定时.svg                   # 工具栏按钮图标（深色主题）
│   └── 定时_light.svg             # 浅色主题图标
├── cron_core/
│   ├── __init__.py
│   ├── models.py                  # CronTask / RunRecord + 下次执行时间计算
│   ├── store.py                   # JSON 持久化（线程安全）
│   ├── scheduler.py               # QTimer 调度器（UI 线程轮询）
│   └── runner.py                  # TaskRunnerWorker(QThread) — EP3 执行
└── ui/
    ├── __init__.py                # register_ui / unload_ui
    ├── cards.py                   # 主卡（任务列表/编辑/运行记录三页 QStackedWidget）
    └── controller.py              # 调度器生命周期 + Worker 编排
```

## 与主程序的边界

对话能力经 **ui context services** 注入：

| 服务 | 用途 |
|---|---|
| `create_engine_session("cron-chat")` | EP3 同步阻塞驱动原语；构造独立 SessionManager 不污染主窗口 |
| `get_tools_schema("cron-chat")` | 取工具集（agent 不存在时主程序返回全量工具） |
| `notify(title, message)` | InfoBar 通知 |

任务配置（轮询间隔/超时/记录上限）走 **PluginConfigStore**（settings 卡显示字段）。

## 执行模型

1. **调度器**（UI 线程 QTimer，每 30s tick）扫 `tasks.json`，到点触发回调
2. **controller._on_due**：并发检查（已有执行则跳过）→ UI 线程 `create_engine_session()` 构造 EngineSession
3. **TaskRunnerWorker**（QThread）：`session.turn(system, user=task.prompt, tools=..., timeout=...)` 阻塞执行
4. **执行结束**：`finished_run(dict)` 信号回 UI 线程，写 `runs.json` + InfoBar 通知 + 刷新卡片
5. **scheduler** 滚动下次执行时间（单次则禁用任务）

> 调度器只决定「何时触发」，执行完全交给 EP3 同步驱动原语——worker 可自主多轮工具调用，与用户手动对话等价。

## 数据存储

| 文件 | 路径 |
|---|---|
| `tasks.json` | `<app_data_dir>/plugins/cron-chat/data/tasks.json` |
| `runs.json`  | `<app_data_dir>/plugins/cron-chat/data/runs.json` |
| `config.json` | `<app_data_dir>/plugins/cron-chat/config.json`（PluginConfigStore 维护） |

`<app_data_dir>` 通常为 `~/.drifox/`。插件热重载与卸载不影响数据。

## 配置项

| 字段 | 默认 | 说明 |
|---|---|---|
| 调度轮询间隔（秒） | 30 | 越小触发越准时；< 10s 不会更快（已 clamp） |
| 单任务超时（秒） | 600 | 任务执行上限；超时记为 timeout |
| 运行记录保留条数 | 200 | 每个任务保留上限；超出按时间清理最旧 |

## 热重载

- `ui/` / `cron_core/` 改动 → `watchfiles` 自动重载
- `register_ui` 显式清理 `ui_plugin_cron_chat.*` 与 `cron_core.*` 缓存
- `unload_ui` 调用 `controller.shutdown()`：停调度器 + 取消执行中的 worker + 归零单例（防热重载单例分裂）

## 已知限制

- 全局单并发：同一任务执行中不可重复触发；不同任务可并行（受 worker 资源约束）
- 单次执行依赖会话资源：UI 关闭后到时若未打开过一次任务面板（无 ctx），任务会跳过并推迟到下个 tick
- 长 duration（> 60s）会触发默认 worker watchdog——已通过 `services["create_engine_session"]` EP3 路径规避

## 安装

```bash
# Windows
xcopy plugins\cron-chat %USERPROFILE%\.drifox\plugins\cron-chat /E /I /Y
# Linux / macOS
cp -r plugins/cron-chat ~/.drifox/plugins/cron-chat
```

启动 DriFox，插件会被自动发现并加载（依赖主程序 ≥ 0.5.0 且提供 `create_engine_session` 服务键）。

## 许可证

MIT — 详见仓库根 LICENSE。
