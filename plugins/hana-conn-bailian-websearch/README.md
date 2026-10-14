# 阿里云百炼 联网搜索

通过阿里云百炼进行实时联网搜索。安装后填入百炼 API Key。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__hana-bailian-websearch__`。

## 认证

本连接器需要服务方颁发的访问令牌。令牌通过环境变量注入，仓库内只保留占位符。

1. 打开下方「获取地址」申请令牌
2. 设为环境变量后重启 DriFox，或在设置 → MCP 连接器 → 本插件里直接填写

```powershell
$env:BAILIAN_WEBSEARCH_APIKEY = "你的令牌"
```

## 获取地址

https://bailian.console.aliyun.com/?tab=model#/api-key

## 上游

- 服务方端点: `https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
