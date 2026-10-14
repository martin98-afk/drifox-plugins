# 钉钉待办

查看、创建和完成钉钉待办。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__dingtalk-todo__`。

## 认证

本连接器不使用固定端点，而是服务方为每个账号签发的专属链接。链接已写成
`${env.DINGTALK_TODO_MCP_URL}` 占位符，设好环境变量即可，无需改动配置文件。

1. 打开下方「获取地址」复制你的专属 MCP 链接
2. 设为环境变量，重启 DriFox 后在设置 → MCP 连接器启用本插件

```powershell
$env:DINGTALK_TODO_MCP_URL = "你的专属 MCP 链接"
```

## 上游

- 服务方端点: `https://mcp-gw.dingtalk.com`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
