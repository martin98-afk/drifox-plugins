# TikTok for Business

TikTok for Business MCP Server 是基于模型上下文协议（MCP）搭建的标准化桥梁，助力开发者与广告主将 AI 智能代理直接对接 TikTok 广告平台。它将广告核心能力⸺广告活动管理、效果报表、受众配置以及创意运营，封装为一套稳定、可投入生产环境使用的工具。AI智能代理仅通过简洁结构化指令，即可完成 TikTok 广告的管理、优化与数据依托这套工具报表查询工作。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__tiktok__`。

## 认证

无需预置密钥，启用后直连。TikTok for Business 广告 MCP，需 TikTok 广告账户授权。

## 上游

- 服务方端点: `https://business-api.tiktok.com/open_mcp/tt-ads-mcp-flat`
- 传输: streamable HTTP
- 来源: WorkBuddy 连接器市场（connector-plugins 整包）

## 示例

- 将所有广告活动结束日期更新为两周后
- 结合我名下广告活动年初至今的数据表现，为即将到来的季节性推广活动推荐广告活动类型与创意素材
- 识别消耗异常，并针对投放不达预期的广告活动给出优化建议
