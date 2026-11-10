# 腾讯文档

创建、搜索、阅读和编辑腾讯文档，支持文档、表格、幻灯片与思维导图。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__tencent-docs__`。

## 认证

腾讯文档 MCP 官方已下线 OAuth，仅支持空间级 MCP token（credential 机制，Key 不落配置文件）：

1. 电脑端打开 docs.qq.com 空间列表，进入目标空间
2. 右上角「≡」→「使用MCP」→「获取MCP token」（需超级会员/超级会员Plus，token 一年有效）
3. 设置 → MCP 连接器 → 本插件 → 填入 Token（「申请页」按钮直达一键复制页）
4. 宿主按 `credential.inject` 把 Token 以 `Authorization: <token>` 头注入（无 Bearer 前缀）

注意：token 是空间级的，一个空间一个 token；多空间需配置多个 server entry。

## 上游

- 服务方端点: `https://docs.qq.com/openapi/mcp`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
