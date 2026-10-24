# monday.com

查看和更新 monday.com 的看板、条目与更新。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__monday__`。

## 认证

首次启用会跳转浏览器完成 OAuth 授权。DriFox 自动完成动态客户端注册与
PKCE，token 保存在插件自身配置中，之后自动刷新。

授权入口：设置 → MCP 连接器 → 本插件 → 点击授权按钮。

## 上游

- 服务方端点: `https://mcp.monday.com/mcp`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
