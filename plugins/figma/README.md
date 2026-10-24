# Figma

读取 Figma 设计稿的结构、样式与变量。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__figma__`。

## 认证

首次启用会跳转浏览器完成 OAuth 授权。DriFox 自动完成动态客户端注册与
PKCE，token 保存在插件自身配置中，之后自动刷新。

授权入口：设置 → MCP 连接器 → 本插件 → 点击授权按钮。

### 注册名说明（重要）

Figma 的远程 MCP 只接受其官方目录内客户端的动态注册，其余一律 `403 Forbidden`。
实测（2026-10-24）可通过的名字仅：`Claude Code`、`Codex`、`opencode`、`Claude Desktop`；
`DriFox`、`VS Code`、`Cursor`、`Gemini CLI` 等均被拒。

本插件 `.mcp.json` 的 `client_name` 设为 `Claude Code` 才能完成注册。代价与风险：

- Figma 侧会把连接识别为 Claude Code（授权页 `utm_source=Figma+MCP+in+Claude+Code`），
  属于冒用第三方客户端身份，不符合 Figma 服务条款，账号风险由使用者自担。
- 该白名单是 Figma 单方维护的硬编码列表，随时可能收紧导致再次失败。
- 若 Figma 官方接洽或明确禁止，应改回 `DriFox` 并等待被纳入官方目录。

替代方案：用 Figma 桌面版 MCP（本地端点，需桌面 app 与 Dev/Full 席位），不依赖此白名单。

## 上游

- 服务方端点: `https://mcp.figma.com/mcp`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
