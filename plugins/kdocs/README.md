# 金山文档|WPS云文档

金山文档官方 Skill。对话即操作——知识一键存入、碎片内容整理、接龙转表格、文档转 Markdown、表格美化、收发表生成，全在一句话内完成。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__kdocs__`。

## 认证

OAuth 授权。金山文档官方 MCP。WorkBuddy 内为服务端代理认证，此处改为 OAuth 直连，需 WPS 账号授权。

## 上游

- 服务方端点: `https://mcp-center.wps.cn/skill_hub/mcp`
- 传输: streamable HTTP
- 来源: WorkBuddy 连接器市场（connector-plugins 整包）

## 示例

- 把这段接龙内容整理成表格
- 把这个网页存到我的金山文档里
- 帮我把这些零散笔记整理归档到一个文档
- 生成一份活动报名信息收集表

## 技能

随插件内置 AI 技能（AI 按任务自动匹配，无需手动调用）：

- `kdocs`

注：技能正文沿用服务方原文（含其官方脚本），个别操作指引以 WorkBuddy/CodeBuddy 环境为例，DriFox 下以实际可用工具为准。
