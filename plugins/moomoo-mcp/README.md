# Moomoo

Moomoo is a stock trading and market data connector. It supports multi-market (HK, US, CN, SG, JP, CA, etc.) quote queries and order execution, providing K-lines, capital flow, option chains, financial statements, research reports, institutional holdings, economic calendar, and comprehensive financial data services.

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__moomoo-mcp__`。

## 认证

无需预置密钥，启用后直连。moomoo 证券行情与交易。交易下单涉及真实资金，请谨慎确认。

## 上游

- 服务方端点: `https://mcp.moomoo.com/mcp`
- 传输: streamable HTTP
- 来源: WorkBuddy 连接器市场（connector-plugins 整包）

## 示例

- 查一下腾讯(00700)最新的股价和成交量
- 帮我下单买入100股苹果(AAPL)
- 查看我的港股持仓盈亏情况
- 分析一下比亚迪最近的资金流入流出情况

## 技能

随插件内置 AI 技能（AI 按任务自动匹配，无需手动调用）：

- `moomoo-mcp-skill`

注：技能正文沿用服务方原文（含其官方脚本），个别操作指引以 WorkBuddy/CodeBuddy 环境为例，DriFox 下以实际可用工具为准。
