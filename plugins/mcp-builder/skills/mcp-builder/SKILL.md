---
name: mcp-builder
description: 教用户从零创建 MCP（Model Context Protocol）服务器，连接任意工具/数据源到 DriFox / Claude Code / Cursor。触发关键词：MCP、Model Context Protocol、mcp server、mcp tools、mcp resources、造 MCP、写 MCP、MCP 服务器、模型上下文协议、tool 集成。
---

# MCP Builder 技能 — 从零造 MCP 服务器

源自 [anthropics/skills/mcp-builder](https://github.com/anthropics/skills/tree/main/skills/mcp-builder)。

## 何时触发

- "造一个 MCP server"、"包装工具为 MCP"
- "想接入 Notion / Linear / Slack 到 DriFox"
- "我的工具想暴露给 AI"

## 5 步工作流

### Step 1 — 评估

问 3 个问题：

1. **是否真的需要 MCP？**
   - 简单提示词能解决 → 不要造
   - 需要双向流式 + 高并发 → 适合
   - 只读访问资源 → 适合

2. **用什么语言？**
   - Python：生态最丰富（首选）
   - TypeScript：Node.js 生态
   - Go：高性能

3. **本地 vs 远程？**
   - 本地：stdio
   - 远程：HTTP+SSE

### Step 2 — 写 4 类原语

#### 1. Tools（工具）

```python
from mcp.server import Server
from mcp.types import Tool, TextContent

app = Server("my-server")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_docs",
            description="搜索文档库。返回 5-10 条最相关的文档。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "limit": {"type": "integer", "description": "返回数量", "default": 10}
                },
                "required": ["query"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "search_docs":
        results = do_search(arguments["query"], arguments.get("limit", 10))
        return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False))]
    raise ValueError(f"Unknown tool: {name}")
```

#### 2. Resources（资源）

```python
@app.list_resources()
async def list_resources():
    return [
        Resource(
            uri="file://docs/{path}",
            name="文档文件",
            description="读取文档文件"
        )
    ]

@app.read_resource()
async def read_resource(uri: str):
    if uri.startswith("file://docs/"):
        path = uri[len("file://docs/"):]
        return open(path).read()
    raise ValueError(f"Unknown resource: {uri}")
```

#### 3. Prompts（提示词模板）

```python
@app.list_prompts()
async def list_prompts():
    return [
        Prompt(
            name="summarize",
            description="总结文本",
            arguments=[
                {"name": "text", "description": "要总结的文本", "required": True}
            ]
        )
    ]

@app.get_prompt()
async def get_prompt(name: str, arguments: dict):
    if name == "summarize":
        return f"请总结以下文本：\n\n{arguments['text']}"
    raise ValueError(f"Unknown prompt: {name}")
```

#### 4. Sampling（采样）

```python
@app.sampling()
async def generate(prompt: str) -> str:
    """调用 LLM 生成内容"""
    return await call_llm(prompt)
```

### Step 3 — 包描述

每个 tool 必须有清晰描述。否则 AI 不知道什么时候调用。

```python
# ✅ 清晰
Tool(
    name="search_docs",
    description="搜索文档库。返回 5-10 条最相关的文档。",
    ...
)

# ❌ 模糊
Tool(
    name="search",
    description="搜索",
    ...
)
```

### Step 4 — 错误处理

```python
from mcp import McpError

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "divide":
        x = arguments.get("x")
        if x == 0:
            raise McpError(
                code="INVALID_INPUT",
                message="除数不能为零"
            )
        return [TextContent(type="text", text=str(10 / x))]
```

### Step 5 — 文档化 + 测试

```bash
# 1. 写 README
# 2. 用 MCP Inspector 测
npx @modelcontextprotocol/inspector
```

## 3 种传输

| 传输 | 场景 | 选择 |
|------|------|------|
| **stdio** | 本地 CLI 工具 | ✅ 首选 |
| **HTTP+SSE** | 远程服务 | 80/443 端口 |
| **streamable HTTP** | 现代远程 | 80/443 |

## 8 个反模式

- ❌ **没有描述** — AI 不知道何时调用
- ❌ **描述太宽** — "通用工具"（应改具体）
- ❌ **HTTP 用于本地** — 应当用 stdio
- ❌ **没错误处理** — 失败崩盘
- ❌ **同步阻塞** — 应当 async
- ❌ **没限制输入** — 巨大 string 撑爆
- ❌ **没限制 token** — 大量返回撑爆
- ❌ **没版本管理** — 升级破坏兼容

## 8 个最佳实践

1. **命名规范**：server `kebab-case`、tool `snake_case`
2. **错误友好**：用 `McpError` 带 code + message
3. **限制输入**：校验所有参数
4. **限制返回**：截断长字符串
5. **安全**：不记录 secret、限制文件访问
6. **缓存**：常见查询加 cache
7. **异步**：所有 IO 异步
8. **文档**：每个 tool 都有 README

## TypeScript 模板

```typescript
import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'

const server = new Server({
  name: 'my-server',
  version: '1.0.0',
}, {
  capabilities: {
    tools: {},
    resources: {},
    prompts: {}
  }
})

server.setRequestHandler('tools/list', async () => ({
  tools: [{
    name: 'hello',
    description: 'Say hello',
    inputSchema: {
      type: 'object',
      properties: { name: { type: 'string' } },
      required: ['name']
    }
  }]
}))

server.setRequestHandler('tools/call', async (request) => {
  if (request.params.name === 'hello') {
    return {
      content: [{ type: 'text', text: `Hello, ${request.params.arguments.name}!` }]
    }
  }
  throw new Error(`Unknown tool: ${request.params.name}`)
})

const transport = new StdioServerTransport()
await server.connect(transport)
```

## JSON-RPC 协议

MCP 基于 JSON-RPC 2.0：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_docs",
    "arguments": { "query": "MCP" }
  }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      { "type": "text", "text": "..." }
    ]
  }
}
```

## 3 个常见 MCP server 范例

### 1. GitHub MCP

```python
@app.list_tools()
async def list_tools():
    return [
        Tool(name="search_repos", description="搜索 GitHub 仓库", ...),
        Tool(name="list_issues", description="列出 issues", ...),
        Tool(name="create_issue", description="创建 issue", ...),
    ]
```

### 2. Linear MCP

```python
Tool(name="list_teams", description="列出团队", ...),
Tool(name="create_task", description="创建任务", ...),
Tool(name="update_task", description="更新任务", ...),
```

### 3. Notion MCP

```python
Tool(name="search_pages", description="搜索页面", ...),
Tool(name="create_page", description="创建页面", ...),
Tool(name="update_page", description="更新页面", ...),
```

## 配合

- 配合 `context7` 拉 MCP SDK 文档
- 配合 `python-pro` 写 Python MCP
- 配合 `ecc` 复用工作流

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
