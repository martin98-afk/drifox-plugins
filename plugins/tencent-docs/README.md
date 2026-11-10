# 腾讯文档

创建、搜索、阅读和编辑腾讯文档，支持文档、表格、幻灯片与思维导图。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__tencent-docs__`。

## 认证

腾讯文档 MCP 官方已下线 OAuth，仅支持空间级 MCP token：

1. 电脑端打开 docs.qq.com 空间列表，进入目标空间
2. 右上角「≡」→「使用MCP」→「获取MCP token」（需超级会员/超级会员Plus，token 一年有效）
3. 编辑本插件 `.mcp.json`，把 token 粘贴到 `headers.Authorization` 的值里
   （key 必须叫 `Authorization`，直接填 token 值，不带 Bearer 前缀）
4. 保存后宿主热重载自动重连

注意：token 是空间级的，一个空间一个 token；多空间需配置多个 server entry。

## 上游

- 服务方端点: `https://docs.qq.com/openapi/mcp`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
