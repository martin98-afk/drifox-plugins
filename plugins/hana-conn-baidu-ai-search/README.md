# 百度 AI 搜索

用百度搜索全网实时信息。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__hana-baidu-ai-search__`。

## 认证

本连接器的官方 MCP 端点在 URL 上以查询参数接收密钥。DriFox 的 MCP 配置
只支持 HTTP 头与环境变量两种注入方式，无法自动拼接该参数，需手动补全。

到下方「获取地址」申请密钥，然后把 `.mcp.json` 里 `url` 改成:

```
https://appbuilder.baidu.com/v2/ai_search/mcp/sse?api_key=你的密钥
```

改完在设置 → MCP 连接器里重新启用本插件。

## 获取地址

https://console.bce.baidu.com/iam/#/iam/apikey/list

## 上游

- 服务方端点: `https://appbuilder.baidu.com/v2/ai_search/mcp/sse`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
