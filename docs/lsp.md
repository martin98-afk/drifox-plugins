# lsp 组件

lsp 让插件声明 [Language Server Protocol (LSP)](https://microsoft.github.io/language-server-protocol/) 服务器，DriFox 启动时把它们接入代码智能层（补全、跳转、诊断、重构等）。

## 文件位置

```
<plugin-name>/
└── .lsp.json          # 插件根（不是 .drifox-plugin/ 下）
```

## 最小示例

```json
{
    "pyright": {
        "command": "pyright-langserver",
        "args": ["--stdio"],
        "extensionToLanguage": {
            ".py": "python",
            ".pyi": "python"
        },
        "transport": "stdio"
    }
}
```

## 完整结构

```json
{
    "<server-name>": {
        "command": "pyright-langserver",
        "args": ["--stdio"],
        "extensionToLanguage": {
            ".py": "python",
            ".pyi": "python"
        },
        "initializationOptions": {},
        "settings": {
            "python.analysis.typeCheckingMode": "basic"
        },
        "startupTimeout": 10000,
        "maxRestarts": 3,
        "transport": "stdio",
        "installHint": "uv pip install pyright"
    }
}
```

## 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `command` | ✅ | LSP 可执行命令 |
| `args` | ❌ | 命令参数 |
| `extensionToLanguage` | ✅ | 文件扩展名 → 语言 ID 映射 |
| `transport` | ❌ | 通信协议，默认 `stdio`（目前唯一支持） |
| `initializationOptions` | ❌ | LSP `initialize` 请求的 options |
| `settings` | ❌ | LSP `workspace/didChangeConfiguration` 的 settings |
| `startupTimeout` | ❌ | 启动超时（ms），默认 10000 |
| `maxRestarts` | ❌ | 崩溃后最大重启次数，默认 3 |
| `installHint` | ❌ | 给用户的安装提示（如 `"uv pip install pyright"`） |

## 服务器名

`<server-name>` 是 DriFox 内部标识符。多个插件可声明相同 server 名（后者覆盖前者）。

## 多语言支持

DriFox 会按打开文件的扩展名匹配对应的 LSP server：

```json
{
    "pyright": {
        "command": "pyright-langserver",
        "args": ["--stdio"],
        "extensionToLanguage": { ".py": "python", ".pyi": "python" }
    },
    "rust-analyzer": {
        "command": "rust-analyzer",
        "args": [],
        "extensionToLanguage": { ".rs": "rust" }
    }
}
```

## 常用 LSP 配置示例

### Python (pyright)

```json
{
    "pyright": {
        "command": "pyright-langserver",
        "args": ["--stdio"],
        "extensionToLanguage": { ".py": "python", ".pyi": "python" },
        "settings": {
            "python.analysis.typeCheckingMode": "basic",
            "python.analysis.autoSearchPaths": true,
            "python.analysis.useLibraryCodeForTypes": true
        },
        "startupTimeout": 10000,
        "maxRestarts": 3,
        "transport": "stdio",
        "installHint": "uv pip install pyright"
    }
}
```

### TypeScript (typescript-language-server)

```json
{
    "typescript": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "extensionToLanguage": {
            ".ts": "typescript",
            ".tsx": "typescriptreact",
            ".js": "javascript",
            ".jsx": "javascriptreact"
        },
        "settings": {
            "typescript": {
                "preferences": { "includePackageJsonAutoImports": "auto" }
            }
        },
        "installHint": "npm install -g typescript-language-server typescript"
    }
}
```

## 校验

- `.lsp.json` 必须是合法 JSON
- 必须是包含至少一个 server 的字典
- 每个 server 必须有 `command` 字段
- `extensionToLanguage` 推荐填写（缺失时无法自动匹配）

## 与 mcp 的区别

| 维度 | mcp | lsp |
|------|-----|-----|
| 协议 | MCP | LSP |
| 启动方 | DriFox | DriFox |
| 客户端 | LLM 调用 | 编辑器/IDE |
| 用途 | 扩展 LLM 工具集 | 扩展代码智能 |
| 协议端口 | stdio / http | stdio |
| 文件 | `.mcp.json` | `.lsp.json` |

## 故障排查

- **LSP 启动失败**：检查 `command` 是否在 PATH 里
- **没有补全**：检查 `extensionToLanguage` 是否正确
- **经常崩溃**：增大 `maxRestarts` 或检查 LSP server 自身日志
- **性能慢**：调整 `settings` 中的 `typeCheckingMode` 为 `off` / `basic`
