# wecom-unified — 企业微信全能套件

通讯录、智能文档、智能表格、在线 PPT、日程、会议、待办、微盘、邮件、媒体文件一站式 AI 操作，自带跨平台 `wecom-cli`（5 平台二进制，无需安装）。

来源：WorkBuddy wecom-unified 技能包 v1.1.7（static.workbuddy.cn/wecom-skills）。版权归腾讯所有，仅供个人使用。

## 启用

安装即用（技能由 AI 自动匹配）。首次使用任意命令前：

1. 按平台定位 CLI：`bin/win32-x64/wecom-cli.exe`（Windows）/ `bin/darwin-arm64/wecom-cli`（Apple Silicon）等
2. 执行 `<cli> auth init` 扫码完成企业微信授权（登录态由 CLI 本地管理）
3. `<cli> --version` 应 >= 1.2.1

## 技能

- `skills/wecom-unified/SKILL.md` — 全能路由入口（13 个业务域 → 130+ 命令 references）

## 注意

- 原包按 WorkBuddy 宿主登录态设计（`WECOM_CLI_*` 注入）；本插件已改写为 DriFox 下 `auth init` 扫码授权
- 涉及真实邮件发送、文档写入、会议预约等操作，AI 会按技能内约束执行，敏感操作请留意确认
