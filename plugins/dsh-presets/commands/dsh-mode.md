---
description: 切换 DeepSeek Harness agent preset — standard / code / cordis 三选一，写入会话状态
type: prompt
parameters:
  - name: "<preset>"
    description: "目标 preset：standard（通用）/ code（纯写代码）/ cordis（Cordis 框架开发）"
    param_type: positional
prompt_sections:
  preset: "preset"
---

# /dsh-mode — 切换 DSH agent preset

你正在处理 `/dsh-mode` 命令。解析 `$ARGUMENTS` 中的 preset 名，为当前会话切换到对应的 DeepSeek Harness preset 工作流。

## 参数解析

- `$ARGUMENTS` = preset 名（standard / code / cordis 之一）

## preset 总览

<!-- section:preset -->
| preset | 中文 | 工具集 | 步骤预算 | 温度 | 触发词 |
|--------|------|--------|---------|------|--------|
| `standard` | 标准编码 | 全工具 + goal/subagent/workflow/ralph | 25 | 0.4 | 默认、通用、standard |
| `code` | 纯写代码 | 全工具（同 standard） | 35 | 0.3 | code、纯写、专注编码 |
| `cordis` | Cordis 框架开发 | 全工具 + cordis_*（仅 DSH GUI） | 30 | 0.5 | cordis、cordis 插件、cordis_define、@pluginId |
<!-- end -->

## 切换流程

1. 调用 `dsh-presets` Hook 的 `UserPromptSubmit` 事件：发送 `/dsh-mode <preset>`，Hook 会更新 `~/.drifox/memory/dsh-presets-state.json`
2. 下一次 BuildSystemPrompt 时，Hook 会按新 preset 注入对应的声明文本
3. 你应采用新 preset 的工作流约束（如 cordis 必须加载 `editing-cordis-compositions` skill，code 必须禁止中途切到计划模式）

## 注意事项

- cordis 的 cordis_* 工具仅在 DeepSeek Harness GUI 中可用；DriFox 这边执行 cordis 任务时需明确告知用户工具不可用，建议在 DSH 中操作
- preset 切换仅影响当前会话；重启后回到默认 `standard`
- 用户输入 `/dsh-mode` 后无 preset 名 → 列出三选项并询问

## 模板变量

- `$ARGUMENTS`：preset 名
- `$PLUGIN_NAME`：当前插件名（dsh-presets）
