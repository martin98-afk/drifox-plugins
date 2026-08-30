---
description: 查看当前 DSH preset 状态与三种 preset 总览
type: prompt
parameters: []
prompt_sections: {}
---

# /dsh-status — 查看当前 preset

你正在处理 `/dsh-status` 命令。读取会话级 preset 状态并展示。

## 操作

1. 读取 `~/.drifox/memory/dsh-presets-state.json`（如果存在）
2. 找到当前会话键（ctx.session_id 或 'default'）
3. 输出当前 preset + 上次切换时间 + 上一 preset
4. 附三选项总览（见下表）

## 输出模板

```
## 当前状态
- preset: <standard | code | cordis>
- 切换时间: <iso>
- 上一 preset: <preset | 未知>
- 状态文件: ~/.drifox/memory/dsh-presets-state.json

## 三选项
| preset | 定位 | 切换命令 |
|--------|------|---------|
| standard | 通用编码 | /dsh-mode standard |
| code | 纯写代码 | /dsh-mode code |
| cordis | Cordis 框架开发 | /dsh-mode cordis |
```

## 注意事项

- 状态文件不存在 → 默认 standard
- 当前 session 无记录但全局有 → 提示「首次进入，使用默认 standard」
- 切换命令由本插件 hook 自动处理（见 dsh-presets-hook UserPromptSubmit 事件）

## 模板变量

- `$PLUGIN_NAME`：当前插件名（dsh-presets）
