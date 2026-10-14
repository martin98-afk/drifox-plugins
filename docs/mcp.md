# mcp 组件

mcp 让插件声明 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 服务器，DriFox 启动时把它们接入运行时，AI 即可调用这些外部工具。

## 文件位置

```
<plugin-name>/
└── .mcp.json          # 插件根（不是 .drifox-plugin/ 下）
```

## 最小示例

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "github_pat_xxx"
      },
      "enabled": true
    }
  }
}
```

## 完整结构

```json
{
  "mcpServers": {
    "<server-name>": {
      "command": "uvx",
      "args": ["some-mcp-server", "-y"],
      "env": {
        "API_KEY": "your-key"
      },
      "type": "stdio",
      "url": "",
      "headers": {},
      "enabled": false
    }
  }
}
```

### 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `mcpServers` | ✅ | 顶层字典，键为服务器名 |
| `<server>.command` | stdio 必填 | 启动命令（如 `uvx`、`npx`） |
| `<server>.args` | ❌ | 命令参数列表 |
| `<server>.env` | ❌ | 注入的环境变量 |
| `<server>.type` | ✅ | `stdio`（本地进程） \| `http`（远程 HTTP） \| `sse`（远程 SSE） |
| `<server>.url` | http/sse 必填 | 端点 URL，支持 `${env.VAR}` 占位符 |
| `<server>.headers` | ❌ | HTTP 头，值支持 `${env.VAR}` 占位符 |
| `<server>.enabled` | ❌ | `false` 时不自动启动，用户可手动启用 |

### 三种 type

- **`stdio`**：DriFox 启动一个子进程，通过 stdin/stdout 通信
- **`http`**：通过 streamable HTTP 连接到远程 MCP 服务器
- **`sse`**：通过 Server-Sent Events 连接到远程 MCP 服务器

### `credential` 凭据声明（推荐）

声明式方式：插件在 `.mcp.json` 里写清「要什么 Key、去哪申请、注入到哪里」，
DriFox 在设置 → MCP 连接器里为它渲染一个输入框和「获取 Key」按钮。
用户粘贴保存即生效，不必碰环境变量。

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "enabled": false,
      "credential": {
        "label": "Token",
        "placeholder": "GitHub Personal Access Token",
        "getUrl": "https://github.com/settings/personal-access-tokens",
        "inject": { "type": "header", "name": "Authorization", "scheme": "Bearer" }
      }
    },
    "amap": {
      "type": "http",
      "url": "https://mcp.amap.com/mcp",
      "enabled": false,
      "credential": {
        "label": "Key",
        "placeholder": "高德地图 Web 服务 Key",
        "getUrl": "https://console.amap.com/dev/key/app",
        "inject": { "type": "query", "name": "key" }
      }
    }
  }
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `label` | ❌ | 输入框前的标签，缺省 `Key` |
| `placeholder` | ❌ | 输入框占位提示 |
| `getUrl` | ❌ | 「获取 Key」按钮打开的申请页；缺省不显示该按钮 |
| `inject.type` | ✅ | `header` / `query` / `url` |
| `inject.name` | header/query 必填 | header 名或查询参数名 |
| `inject.scheme` | ❌ | header 前缀，如 `Bearer`；缺省原样写入 |

三种注入方式：`header` 写成请求头；`query` 追加为 URL 查询参数；
`url` 表示 Key 本身就是完整端点（服务方签发的专属链接），整条替换 `url`。

Key 存在 `<app_data>/plugin_data/<插件>/config.json`，键名 `_mcp_cred_<server>`，
与 OAuth token 同一处（明文，不会进 git）。**声明了 credential 但未填 Key 时，
连接前会直接提示，不会带着空值去打远端。**

### `${env.VAR}` 占位符（适合 CI / 脚本场景）

不想用设置界面时，`url` 与 `headers` 也可写 `${env.变量名}`，连接时替换为进程
环境变量的值。变量未设置时保留字面量，并在连接前直接报错。

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer ${env.GITHUB_TOKEN}" },
      "enabled": false
    }
  }
}
```

优先级：用户在界面填的 Key（`credential`）高于 `${env.VAR}`。
**密钥不要写进 `.mcp.json` 提交到 git。**

## 服务器名

`<server-name>` 是 DriFox 内部标识符。AI 引用工具时使用 `mcp__<server-name>__<tool>` 形式。

## 启用策略

`enabled: false` 时不自动启动，但仍出现在 `/plugin` 命令的列表中，用户可手动启用。

> **不要把密钥提交到 git**。推荐方式：
> - 仓库里只放 `enabled: false` + 占位符
> - 真实密钥放在 `~/.drifox/mcp-credentials.json`（不入 git）
> - 或用环境变量引用

## 完整参考示例

```json
{
  "mcpServers": {
    "minimax": {
      "command": "uvx",
      "args": ["minimax-coding-plan-mcp", "-y"],
      "env": {
        "MINIMAX_API_KEY": "${env.MINIMAX_API_KEY}",
        "MINIMAX_API_HOST": "https://api.minimaxi.com"
      },
      "enabled": false,
      "type": "stdio"
    },
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "${env.GITHUB_TOKEN}"
      },
      "enabled": false
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"],
      "type": "stdio",
      "enabled": false
    }
  }
}
```

## 校验

- `.mcp.json` 必须是合法 JSON
- 顶层必须有 `mcpServers` 字典
- 每个 server 必须有 `command`（stdio）或 `url`（http）之一
- `type` 字段推荐显式指定

## 安全注意

- `env` 字段可能在日志中泄露，**避免硬编码密钥**
- `args` 中若包含 URL / 路径，需警惕命令注入
- system 类型插件的 MCP 配置需要签名验证
