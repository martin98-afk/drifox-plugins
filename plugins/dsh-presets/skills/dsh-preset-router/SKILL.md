---
name: dsh-preset-router
description: DeepSeek Harness 三种 agent preset（standard / code / cordis）的自动选择启发 — 当用户提到「cordis 插件」「@pluginId」「cordis_define」「纯写代码」「标准模式」等关键词时，匹配对应 preset 并采用其工作流。
---

# DSH Preset Router（自动匹配三种 preset 的工作流）

DeepSeek Harness 暴露三种 agent preset，本 skill 帮助你在 DriFox 中**自动选用正确的 preset 工作流**，无需用户显式调用 `/dsh-mode`。

## 三种 preset 的差异化摘要

| preset | system prompt 体量 | 核心定位 | 工具集 | 步骤预算 | 温度 |
|--------|------------------|---------|--------|---------|------|
| standard | ~6.5k chars | 通用编码，模糊任务默认起点 | 全工具 + goal/subagent/workflow/ralph | 25 | 0.4 |
| code | ~6.5k chars | 纯写代码专注模式，产出更收敛 | 全工具（同 standard） | 35 | 0.3 |
| cordis | ~18k chars | Cordis 插件框架开发专用 | 全工具 + cordis_* 七步（仅 DSH GUI 可用） | 30 | 0.5 |

## 自动选择启发（按优先级）

### 1. 强信号 → cordis

命中以下任一关键词，必须按 cordis 工作流走：

- `cordis` / `cordis 插件` / `cordis plugin` / `cordis preset`
- `cordis_define` / `cordis_run` / `cordis_stop` / `cordis_undefine`
- `cordis_inspect_list` / `cordis_inspect_query` / `cordis_inspect_self`
- `@pluginId`（用户在消息里出现 `@xxx` 形式）
- `cordis.yml` / `cordis composition` / `HOST composition` / `AGENT PRESET`
- `pluginId` / `packageId` / `pluginRunId` / `currentPackageId` / `nextPackageId`
- `动态插件` / `动态 Cordis` / `Dynamic Cordis Plugin`
- `editing-cordis-compositions` skill 加载请求

### 2. 中信号 → code

用户明确要求"纯写代码"、"不要讨论"、"不要重构"、"专注实现"、"直接改"、"快速改完"，按 code preset 工作流走（更长 step 预算、更低温度、紧验证回路）。

### 3. 弱信号 → standard

其余情况（含模糊任务、长任务、混合需求），按 standard preset 默认工作流走。

## 关键约束（cordis 模式必须规避的高频错误）

- **Services**：用 `ctx.get('serviceName')` 读可选 service；只在硬依赖时声明 `inject: ['serviceName']`，绝不在未声明时通过 `ctx.serviceName` 访问
- **Code**：Host/Client 都是**纯 JavaScript**，不写 TypeScript / JSX / `<Component />`；不假设 `process` / `Buffer` / `window` / `document` / `fetch` 等全局存在
- **Data**：不要对 Services / Events / Slots / Sessions 做 `JSON.stringify` / `structuredClone` / 全对象 dump，只读需要的叶子字段
- **Lifecycle**：所有副作用（service / event / timer / slot / theme）必须可逆，用 `ctx.effect()` / `ctx.on()` / 官方 disposer API

## 何时回退到 standard / code

- 用户说「写个 Python 脚本」、「修个 bug」、「重构一下」→ 这是普通编码任务，**不是** cordis 任务
- cordis 工具在 DriFox 中不可用 → 切回 standard 流程，告知用户需在 DSH GUI 中执行 cordis 部分
- 任务要求"一次性临时扩展运行时" → 才是 cordis 的合理用例
