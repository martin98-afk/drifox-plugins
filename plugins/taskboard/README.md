# taskboard 插件 — DriFox 官方插件

> 任务看板对话引擎 — 类 Teambition 四列看板，每列绑定专属智能体，多任务并行流水线。

## 简介

taskboard 把「多智能体协作」做成一张竖向任务看板：

```
┌─ 待办 @tb_todo ─┬─ 进行中 @tb_build ─┬─ 审查 @tb_review ─┬─ 完成 @tb_done ─┐
│  任务 A          │  任务 C (⏳处理中)  │                   │  任务 E (报告)   │
│  任务 B          │                   │                   │                │
└─────────────────┴───────────────────┴───────────────────┴────────────────┘
```

- **todo（待办）** → `@tb_todo` 评估师：评估任务价值与可行性，细化执行建议，决定任务是否进入执行
- **inprogress（进行中）** → `@tb_build` 执行者：实际完成任务（写代码/跑验证）
- **review（审查）** → `@tb_review` 审查者：独立审查执行结果，质量关卡
- **done（完成）** → `@tb_done` 归档师：生成任务总结报告，点击卡片 📄 查看

## 核心特性

- 📋 **四列看板**：todo / inprogress / review / done，任务卡实时显示处理状态与结论摘要
- 🤖 **每列一智能体**：任务流到哪列就由该列智能体处理；处理完成后智能体**自主决定去留**
  - `TASK_ADVANCE` — 推进到下一列
  - `TASK_HOLD` — 保留当前列（等用户再次触发）
  - `TASK_DROP` — 删除任务
- ⚡ **并行多任务**：每个任务独立 QThread + 独立对话栈，可同时处理多个任务
- 🔀 **两种模式**：
  - **自动流转**：任务状态变化后，对应列智能体立即开始处理（形成全自动流水线）
  - **手动触发**：全部由用户点击 ▶ 决定何时开始（默认）
- ✋ **用户全权控制**：任意状态下可 ▶ 开始 / ⏹ 停止 / 🗑 删除任务；←→ 按钮或**拖拽**在列间移动
- 💾 **持久化**：看板数据存 `<工作目录>/.taskboard/board.json`；done 报告存 `.taskboard/reports/<task_id>.md`；处理日志存 `.taskboard/logs/`

## 使用方法

1. 输入区点击 **📋** 按钮（或命令 `/taskboard`）打开看板
   - 看板停靠右侧（与浏览器卡同插槽互斥——打开看板自动替换浏览器卡）
2. 点击「＋ 发布任务」：填写标题与描述，任务进入待办列
3. 切换「自动流转 / 手动触发」开关决定驱动方式
4. 手动模式下点击任务卡 **▶** 触发当前列智能体处理；处理中可 **⏹** 停止
5. 完成列任务卡点击 **📄** 查看智能体生成的任务报告

## 架构

```
plugins/taskboard/
├── .drifox-plugin/plugin.json     # manifest（ui + agents）
├── agents/                        # 四列智能体（hidden subagent）
│   ├── tb_todo.md                 # 待办评估师（只读）
│   ├── tb_build.md                # 执行者（全工具）
│   ├── tb_review.md               # 审查者（只读 + bash 验证）
│   └── tb_done.md                 # 归档师（只读，产出报告）
├── taskboard_core/                # 核心逻辑（自包含包）
│   ├── config.py                  # 列定义 / 智能体映射 / 信号协议
│   ├── models.py                  # Task 数据类 + BoardStore 持久化
│   ├── adapter.py                 # 线程同步对话适配器
│   └── worker.py                  # TaskWorker（单任务一次完整对话）
└── ui/
    ├── __init__.py                # register_ui：right 浮动卡 + 输入按钮
    ├── board_card.py              # 看板主卡（四列 + 工具栏 + 对话框）
    ├── task_card.py               # 任务卡（按钮操作 + 拖拽源）
    └── controller.py              # 控制器（生命周期 / 并行 worker / 持久化）
```

### 对话引擎对接（与 autoloop 同契约）

- Worker 自建 `ConversationCore` 执行栈（经 `services["conversation_stack"]()` 工厂）
- 每任务独立栈，并行互不干扰
- 工具集按各列智能体 permission 过滤（`get_tools_schema(agent_name)`）
- 全部对话能力经 UI context services 注入，与主程序松耦合

## 依赖与运行要求

| 依赖 | 说明 |
|------|------|
| DriFox ≥ 0.5.0 | 主程序需支持 `UIPluginRegistry.load_plugin` + `conversation_stack` EP2 契约 |
| PyQt5 | UI 控件 |

## 安装

```bash
# Windows
xcopy plugins\taskboard %USERPROFILE%\.drifox\plugins\taskboard /E /I /Y
# Linux / macOS
cp -r plugins/taskboard ~/.drifox/plugins/taskboard
```

## 许可证

MIT — 详见仓库根 LICENSE。
