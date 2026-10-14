# 魔搭 MCP

接入魔搭 MCP 广场上的托管服务。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__hana-modelscope__`。

## 认证

本连接器不使用固定端点，而是服务方为每个账号签发的专属链接。

到下方「获取地址」复制你的专属 MCP 链接，替换 `.mcp.json` 里的 `url`，
然后在设置 → MCP 连接器里重新启用本插件。

## 获取地址

https://www.modelscope.cn/mcp

## 上游

- 服务方端点: `https://www.modelscope.cn`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
