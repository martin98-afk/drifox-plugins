# mcp-builder

> MCP（Model Context Protocol）服务器构建助手 — 从零创建、调试、文档化任意 MCP 服务器。

源自 [anthropics/skills/mcp-builder](https://github.com/anthropics/skills/tree/main/skills/mcp-builder)。本插件教 AI 按 MCP 官方规范为本地工具/数据源造一个 server。

## 何时触发

- 用户："教我造一个 MCP server"、"包装工具为 MCP"
- AI 给非 Anthropic 工具写适配层
- 第三方 API（Notion / Linear / Slack / 自研）想接入 DriFox

## 核心概念

### MCP 定义

Model Context Protocol = 模型与工具之间的标准协议。

| 角色 | 端 |
|------|------|
| MCP Client | DriFox / Claude Code / Cursor |
| MCP Server | 你的工具包装（stdin-out 或 HTTP） |
| Tool | MCP server 暴露的函数 |

### 3 类传输

| 传输 | 场景 | 端口 |
|------|------|------|
| **stdio** | 本地命令行工具 | - |
| **HTTP+SSE** | 远程服务 | 端口 |
| **streamable HTTP** | 现代远程 | 端口 |

## 工作流

### Step 1 — 评估

问自己 3 个问题：

1. **是否真的需要 MCP？**
   - 简单提示词能解决 → 不要造 server
   - 需要双向流式 + 高并发 → 适合
   - 只读访问资源 → 适合

2. **用什么语言？**
   - Python：生态最丰富（mcp-python-sdk）
   - TypeScript：Node.js 生态
   - Go：高性能

3. **本地 vs 远程？**
   - 本地：stdio
   - 远程：HTTP

### Step 2 — 写 manifest

```json
{
  "name": "my-server",
  "version": "1.0.0",
  "description": "..."
}
```

### Step 3 — 实现 4 类原语

#### 1. Tools（工具）

```python
@mcp.tool()
def search(query: str, limit: int = 10) -> list[dict]:
    """搜索文档"""
    return [{"title": "...", "url": "..."}]
```

#### 2. Resources（资源）

```python
@mcp.resource("file://{path}")
def read_file(path: str) -> str:
    """读取文件内容"""
    return open(path).read()
```

#### 3. Prompts（提示词模板）

```python
@mcp.prompt()
def summarize(text: str) -> str:
    """总结文本"""
    return f"请总结以下文本：{text}"
```

#### 4. Sampling（采样）

```python
@mcp.sampling()
def generate_summary(prompt: str) -> str:
    """调用 LLM 生成摘要"""
    return call_llm(prompt)
```

### Step 4 — 包描述

每个 tool 必须有清晰描述。否则 AI 不知道什么时候调用。

```python
@mcp.tool(
    name="search_docs",
    description="搜索文档库。返回 5-10 条最相关的文档。"
)
def search(query: str) -> list[dict]:
    ...
```

### Step 5 — 错误处理

```python
@mcp.tool()
def risky_tool(x: int) -> int:
    try:
        return 10 / x
    except ZeroDivisionError as e:
        raise McpError(f"除数不能为零: {e}")
```

### Step 6 — 文档化

写 README：

```markdown
# my-mcp-server

## 工具

### search_docs
- 描述：搜索文档
- 参数：
  - query (str): 搜索关键词
  - limit (int, optional): 返回数量
- 返回：[{title, url, snippet}]

## 安装

\`\`\`bash
npm install -g my-mcp-server
\`\`\`

## 配置

\`\`\`json
{
  "mcpServers": {
    "my-server": {
      "command": "my-mcp-server",
      "args": []
    }
  }
}
\`\`\`
```

### Step 7 — 测试

用 MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

## 实战模板

### Python 模板

```python
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

app = Server("my-server")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="hello",
            description="Say hello to someone",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "hello":
        return [TextContent(type="text", text=f"Hello, {arguments['name']}!")]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### TypeScript 模板

```typescript
import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'

const server = new Server({
  name: 'my-server',
  version: '1.0.0',
}, {
  capabilities: {
    tools: {}
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
    return { content: [{ type: 'text', text: `Hello, ${request.params.arguments.name}!` }] }
  }
  throw new Error(`Unknown tool: ${request.params.name}`)
})

const transport = new StdioServerTransport()
await server.connect(transport)
```

## 8 个反模式

- ❌ **没有描述** — AI 不知道何时调用
- ❌ **描述太宽** — "通用工具"（应改具体）
- ❌ **HTTP 用于本地** — 应当用 stdio
- ❌ **没错误处理** — 失败崩盘
- ❌ **同步阻塞** — 应当 async
- ❌ **没限制输入** — 巨大 string 撑爆
- ❌ **没限制 token** — 大量返回撑爆
- ❌ **没版本管理** — 升级破坏兼容

## 4 个最佳实践

### 1. 命名规范

- server 名：`kebab-case`
- tool 名：`snake_case`
- 描述简洁：1-2 句话

### 2. 错误友好

```python
# ❌
raise Exception("error")

# ✅
raise McpError(
    code="INVALID_INPUT",
    message=f"Expected positive number, got {x}"
)
```

### 3. 性能

- 缓存常见查询
- 限制返回数量
- 异步 IO

### 4. 安全

- 验证所有输入
- 不记录 secret
- 限制文件访问范围

## 配合

- 配合 `context7` 拉 MCP SDK 文档
- 配合 `python-pro` 写 Python MCP
- 配合 `frontend-pro` 调试 UI

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
