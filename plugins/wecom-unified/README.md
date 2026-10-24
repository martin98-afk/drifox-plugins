# wecom-unified — 企业微信全能套件（Windows，需自备 token）

企业微信通讯录/智能文档/智能表格/在线 PPT/日程/会议/待办/微盘/邮件/消息的 AI 操作技能，随包自带 `wecom-cli`（workbuddy-local 构建，直连企业微信官方 API）。

来源：WorkBuddy wecom-unified 技能包 v1.1.7 + WorkBuddy 内置 vendor CLI。版权归腾讯所有，仅供个人使用。

## 当前限制（重要）

- **仅 Windows**：CLI 为 win32-x64 构建，其他平台暂无对应构建来源
- **无登录能力**：CLI 没有 `auth` 子命令，所有请求依赖环境变量 `WECOM_CLI_ACCESS_TOKEN`
- **token 来源**：原设计由 WorkBuddy 桌面端企微连接器扫码注入；DriFox 下无该链路，需自行准备有效 token（例如来自企业微信自建应用体系）。未配置 token 时技能会明确报错而不尝试登录

## 使用

1. 设置环境变量 `WECOM_CLI_ACCESS_TOKEN`（会话内或系统级）
2. CLI 位置：`plugins/wecom-unified/bin/win32-x64/wecom-cli.exe`，`--version` 验证
3. 之后 AI 按技能路由（13 个业务域 → 130+ 命令 references）执行

## 技能

- `skills/wecom-unified/SKILL.md` — 全能路由入口
