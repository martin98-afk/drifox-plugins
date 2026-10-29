---
description: B站值班：打开值班面板 / 手动跑一轮 / 查看状态
type: prompt
parameters:
  - name: "run"
    description: "立即后台跑一轮值班"
    param_type: flag
  - name: "status"
    description: "只看环境自检与今日进度"
    param_type: flag
hidden: false
---

# /bili-scroll 命令 — B站值班

你正在处理 `/bili-scroll` 命令（bili-scroll 插件）。

## 执行规则

1. **默认（无参数）**：告诉用户值班面板已可通过 `/bili-scroll` 卡片打开的说明——
   调用 `bili_status` 工具拿环境自检结果，用简洁列表汇报：
   venv / MCP 连接 / 登录凭证 / 今日已挑配额 / 自动跑窗口。
2. **`run`**：调用 `bili_duty_run` 工具后台跑一轮，告知预计 5-20 分钟、完成会弹通知。
3. **`status`**：只做第 1 步。

## 首次使用引导（自检发现未就绪时）

按顺序引导：
1. venv 缺失 → 建议执行 `bili_setup`（装依赖，dangerous 需用户在权限卡确认）
2. MCP 未连接 → 让用户到 `/plugin` 面板启用 bili-scroll 服务器（或重启 DriFox）
3. 凭证不存在 → 提示在对话里喊「扫码登录B站」（走 MCP 的 bili_login，二维码落盘可打开扫）
4. 都就绪 → 可以 `run`

## 红线

- **不要**替用户开启「自动评论」（那是拿他的账号发言，必须在设置卡里本人开启）
- 跑一轮消耗 token，先确认用户有意图再调 `bili_duty_run`
