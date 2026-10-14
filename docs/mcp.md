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

### `${env.VAR}` 凭据占位符

`url` 与 `headers` 的值可以写 `${env.变量名}`，连接时替换为进程环境变量的值。
变量未设置时保留字面量，并在连接前直接报错，不会带着假值去连远端。

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer ${env.GITHUB_TOKEN}" },
      "enabled": false
    },
    "amap": {
      "type": "http",
      "url": "https://mcp.amap.com/mcp?key=${env.AMAP_KEY}",
      "enabled": false
    }
  }
}
```

前者注入请求头，后者拼在 URL 查询参数上——两类远程 MCP 的常见鉴权方式。
**密钥不要写进 `.mcp.json` 提交到 git**，用环境变量注入。

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
