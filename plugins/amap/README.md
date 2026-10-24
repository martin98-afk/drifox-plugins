# 高德地图

地点搜索、路线规划、天气与周边查询。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__amap__`。

## 认证

本连接器需要服务方颁发的 Key。在 DriFox 里直接填，不必配环境变量：

1. 设置 → MCP 连接器 → 找到本连接器
2. 点「获取 Key」跳到申请页，拿到后粘贴进输入框
3. 点「保存」，随后打开开关即自动连接

申请地址：https://console.amap.com/dev/key/app

## 上游

- 服务方端点: `https://mcp.amap.com/mcp`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
