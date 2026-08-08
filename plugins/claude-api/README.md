# claude-api

> Claude API 最佳实践 — SDK 用法、prompt caching、streaming、tool use、batch API、prompt 工程、token 优化。

源自 [anthropics/skills/claude-api](https://github.com/anthropics/skills/tree/main/skills/claude-api)。

## 何时使用

- 写 Claude API 集成代码
- 优化 prompt 降低成本
- 实现 tool use / 流式响应
- 批量处理任务

## 核心能力

### 1. SDK 用法

```python
import anthropic

client = anthropic.Anthropic()

message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello, Claude"}
    ]
)

print(message.content[0].text)
```

### 2. Prompt Caching（节省 90% 成本）

```python
message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": "你是资深 Python 工程师...",  # 大 prompt
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=[{"role": "user", "content": "..."}]
)
```

### 3. Streaming

```python
with client.messages.stream(
    model="claude-opus-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "写一首诗"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### 4. Tool Use

```python
tools = [
    {
        "name": "get_weather",
        "description": "获取某地天气",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"}
            },
            "required": ["location"]
        }
    }
]

message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "北京天气?"}]
)
```

### 5. Batch API（50% 折扣）

```python
batch = client.messages.batches.create(
    requests=[
        {
            "custom_id": "task-1",
            "params": {
                "model": "claude-opus-4-5",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "..."}]
            }
        }
    ]
)

# 异步轮询
while True:
    batch = client.messages.batches.retrieve(batch.id)
    if batch.processing_status == "ended":
        break
    time.sleep(60)
```

### 6. Vision

```python
message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64_image
                }
            },
            {"type": "text", "text": "描述这张图"}
        ]
    }]
)
```

## 8 个最佳实践

### 1. Prompt Caching

```python
# 大 prompt + 频繁调用 → cache
# 节省 90% 成本 + 提升 80% 速度
```

### 2. System Prompt

```python
messages = [{
    "role": "user",
    "content": "...",
    "system": "你是..."
}]
```

### 3. 控制 max_tokens

```python
# 短任务 → 1024
# 长任务 → 4096
# 长文 → 8192+
```

### 4. 错误处理

```python
from anthropic import APIError, RateLimitError, APIConnectionError

try:
    message = client.messages.create(...)
except RateLimitError as e:
    time.sleep(60)
    message = client.messages.create(...)
except APIError as e:
    logger.error(f"API error: {e}")
```

### 5. 重试

```python
import backoff

@backoff.on_exception(backoff.expo, APIError, max_tries=3)
def call_api():
    return client.messages.create(...)
```

### 6. Token 计数

```python
# 估计 token 数
count = client.messages.count_tokens(
    model="claude-opus-4-5",
    messages=[{"role": "user", "content": "..."}]
)
```

### 7. 异步

```python
async with anthropic.AsyncAnthropic() as client:
    message = await client.messages.create(...)
```

### 8. 监控

```python
# 记录每次调用
import logging
logging.info(f"input_tokens={message.usage.input_tokens}")
logging.info(f"output_tokens={message.usage.output_tokens}")
```

## 5 个反模式

- ❌ **每条消息都重发 system prompt** — 用 cache
- ❌ **max_tokens 默认 4096** — 按需调整
- ❌ **无限重试** — 加 max_tries
- ❌ **不监控 token** — 预算失控
- ❌ **不用 batch** — 50% 成本浪费

## 5 大模型选择

| 模型 | 用途 |
|------|------|
| Opus 4.5 | 复杂推理、深度任务 |
| Sonnet 4.5 | 平衡（推荐默认） |
| Haiku 4.5 | 高频、低成本 |
| Opus 4 | 旧版深度 |
| Sonnet 4 | 旧版平衡 |

## 配合

- 配合 `browser` 插件（drifox 内置）
- 配合 `mcp-builder` 造 MCP server
- 配合 `python-pro` 写集成

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
