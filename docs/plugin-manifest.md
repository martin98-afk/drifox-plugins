# 插件 manifest

`plugin.json` 是插件的「身份证」，是 DriFox 识别与加载插件的唯一入口。

## 位置

```
<plugin-name>/
└── .drifox-plugin/
    └── plugin.json
```

路径**必须**是 `<plugin-name>/.drifox-plugin/plugin.json`，**不能**换名。

## 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 插件名，必须与目录名一致，小写 kebab-case |
| `description` | string | 一句话说明插件功能（不超过 200 字） |
| `version` | string | 语义化版本（SemVer 2.0） |
| `components` | object | 启用的组件清单（至少启用一个） |

## 选填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `author` | object \| string | 作者信息，object 形如 `{"name": "x", "email": "x@y.z"}` |
| `homepage` | string (URI) | 插件主页 |
| `repository` | string (URI) | 源码仓库 |
| `license` | string | SPDX 标识符，默认 `GPL-3.0-or-later` |
| `type` | enum | `user`（用户插件，默认） \| `system`（系统级，受信任） |
| `keywords` | string[] | 检索关键词 |
| `drifox` | object | 兼容性声明，见下 |
| `dependencies` | object | 插件间依赖，见下 |

### `components` 子字段（7 个 flag）

```json
"components": {
  "commands": true,    // commands/<name>.md → 斜杠命令
  "agents": true,      // agents/<name>.md → @<name> 智能体
  "skills": true,      // skills/<name>/SKILL.md → AI 技能
  "themes": true,      // themes/<name>/*.yaml → 主题方案
  "hooks": true,       // hooks/hooks.json + <plugin>_hook.py
  "mcp": true,         // .mcp.json → MCP 服务器
  "lsp": true          // .lsp.json → LSP 语言服务器
}
```

启用 `true` 的组件必须有对应目录/文件（详见 [architecture.md](architecture.md) 的目录约定）。

| flag | 必需资源 | 详见 |
|------|---------|------|
| `commands` | `commands/*.md` | [commands.md](commands.md) |
| `agents` | `agents/*.md` | [agents.md](agents.md) |
| `skills` | `skills/<name>/SKILL.md` | [skills.md](skills.md) |
| `themes` | `themes/<name>/*.yaml` | [themes.md](themes.md) |
| `hooks` | `hooks/hooks.json` + `hooks/<plugin>_hook.py` | [hooks.md](hooks.md) |
| `mcp` | `.mcp.json`（插件根） | [mcp.md](mcp.md) |
| `lsp` | `.lsp.json`（插件根） | [lsp.md](lsp.md) |

### `drifox` 兼容性

```json
"drifox": {
  "min_version": "0.5.0",
  "max_version": "1.x",
  "events": [
    "SessionStart",
    "PostToolUse"
  ]
}
```

### `dependencies` 依赖

```json
"dependencies": {
  "evolver": ">=1.0.0",
  "code-review": "^2.1.0"
}
```

## 完整示例

参考 [`evolver` 的 plugin.json](../plugins/evolver/.drifox-plugin/plugin.json)：

```json
{
    "name": "evolver",
    "description": "Evolver 自进化引擎集成插件 — 基于 GEP 协议的 AI Agent 进化能力。",
    "version": "1.0.0",
    "author": { "name": "EvoMap" },
    "homepage": "https://evomap.ai",
    "license": "GPL-3.0-or-later",
    "type": "user",
    "components": {
        "commands": true,
        "hooks": true,
        "skills": true
    }
}
```

另一个参考：system 插件（不在本仓库）的 7 个 flag 全部启用，type 为 `system`，license 为 `MIT`。

## JSON Schema

所有合法 manifest 都必须通过 [`schemas/plugin.schema.json`](../schemas/plugin.schema.json) 校验。

运行 `python tools/validate_plugins.py` 验证。

## 校验规则

- `name` 必须 `^[a-z][a-z0-9-]{1,63}$`
- `version` 必须符合 SemVer `^\d+\.\d+\.\d+(-[a-z0-9.-]+)?$`
- `components.*` 启用时，对应目录/文件必须存在
- `dependencies.*` 中被引用的插件也必须存在
