---
name: claude-api
description: Claude API 最佳实践 — SDK 用法、Prompt Caching、Streaming、Tool Use、Batch API、Token 优化、模型选择、错误处理。触发关键词：claude api、anthropic sdk、prompt cache、streaming、tool use、batch api、token 优化、claude opus、claude sonnet、claude haiku、anthropic SDK、prompt 工程、claude-api。
---

# Claude API 技能 — 最佳实践

源自 [anthropics/skills/claude-api](https://github.com/anthropics/skills/tree/main/skills/claude-api)。

## 何时触发

- 写 Claude API 集成代码
- 优化 prompt 降低成本
- 实现 tool use / 流式响应
- 批量处理任务
- 错误处理 / 重试

## 6 大核心能力

### 1. SDK 基础

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

### 2. Prompt Caching（省 90% 成本）

```python
message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": "你是资深 Python 工程师..." * 100,  # 大 prompt
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=[{"role": "user", "content": "..."}]
)
```

**何时该用**：
- 大 system prompt（> 1024 tokens）
- 频繁调用同一 prompt
- 长文档分析

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

if message.stop_reason == "tool_use":
    tool_use = next(b for b in message.content if b.type == "tool_use")
    # 调用工具
    result = get_weather(tool_use.input["location"])
    # 继续对话
    messages.append({
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": str(result)
        }]
    })
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

# 读取结果
for result in client.messages.batches.results(batch.id):
    print(result.custom_id, result.result.message.content)
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

```
大 prompt + 频繁调用 → cache
节省 90% 成本 + 提升 80% 速度
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
短任务 → 1024
长任务 → 4096
长文 → 8192+
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

## 6 个工具函数

```python
# 1. 计数 token
client.messages.count_tokens(...)

# 2. 流式
client.messages.stream(...)

# 3. 异步
client.messages.acreate(...)

# 4. 批量
client.messages.batches.create(...)

# 5. Vision
client.messages.create(..., content=[image, text])

# 6. Files API
client.files.create(...)  # 上传文件
client.files.retrieve(...)  # 读取
```

## 配合

- 配合 `mcp-builder` 造 MCP server
- 配合 `python-pro` 写集成
- 配合 `prompt-engineering` 优化

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
