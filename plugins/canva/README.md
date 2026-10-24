# Canva可画

无缝调用Canva可画的设计能力。一句话生成海报、演示文稿、小红书封面等设计，通过文字描述调整尺寸、填充品牌模板及检索已有内容

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__canva__`。

## 认证

OAuth 授权。Canva 官方 MCP 走 OAuth 2.1 授权，首次启用时按提示在浏览器完成登录授权。

## 上游

- 服务方端点: `https://mcp.canva.com/mcp`
- 传输: streamable HTTP
- 来源: WorkBuddy 连接器市场（connector-plugins 整包）

## 示例

- 帮我总结 Q2 产品策略文档
- 为我们的 AI 发布会生成一个风格大胆的 pitch deck
- 将我的小红书帖子调整为微信朋友圈尺寸并导出为 PNG
- 用产品发布内容填充我们的品牌模板，8 页，专业风格
