# Tripo 3D

Generate textured, rig-ready 3D models from text or images; export GLB/FBX/OBJ/STL/USDZ/3MF.

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__tripo-3d__`。

## 认证

OAuth 授权。Tripo 3D 生成走 OAuth 授权，生成类工具按用量计费。

## 上游

- 服务方端点: `https://openapi-mcp.tripo3d.ai/mcp`
- 传输: streamable HTTP
- 来源: WorkBuddy 连接器市场（connector-plugins 整包）

## 示例

- Generate a low-poly treasure chest and export it as FBX for Unity
- Turn this concept image into a textured 3D model and export it as GLB
- Generate a 3D-printable knight figurine and export it as STL
- Generate a T-pose robot character, rig it and add a walk animation

## 技能

随插件内置 AI 技能（AI 按任务自动匹配，无需手动调用）：

- `tripo-3d`
- `tripo-game-asset`

注：技能正文沿用服务方原文（含其官方脚本），个别操作指引以 WorkBuddy/CodeBuddy 环境为例，DriFox 下以实际可用工具为准。
