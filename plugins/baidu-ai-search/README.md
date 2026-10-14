# 百度 AI 搜索

用百度搜索全网实时信息。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__baidu-ai-search__`。

## 认证

本连接器的官方 MCP 端点以 URL 查询参数接收密钥。密钥已写成 `${env.BAIDU_AI_SEARCH_API_KEY}`
占位符，无需改动配置文件，设好环境变量即可。

1. 打开下方「获取地址」申请密钥
2. 设置环境变量后重启 DriFox

```powershell
$env:BAIDU_AI_SEARCH_API_KEY = "你的密钥"
```

未设置该变量时，DriFox 会在连接前直接提示缺少哪个环境变量，不会带着空值去连远端。

## 上游

- 服务方端点: `https://appbuilder.baidu.com/v2/ai_search/mcp/sse`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
