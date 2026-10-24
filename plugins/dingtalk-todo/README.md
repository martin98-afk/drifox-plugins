# 钉钉待办

查看、创建和完成钉钉待办。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__dingtalk-todo__`。

## 认证

本连接器的端点不是一个固定地址，而是服务方为每个账号签发的专属链接。

1. 到 https://mcp.dingtalk.com 获取你的专属 MCP 链接
2. 设置 → MCP 连接器 → 找到本连接器，把链接粘贴进输入框
3. 点「保存」，随后打开开关即自动连接

## 上游

- 服务方端点: `https://mcp-gw.dingtalk.com`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
