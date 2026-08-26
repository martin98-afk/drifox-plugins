# openrouter-provider

OpenRouter 服务商接入插件：声明图标/API URL/模型列表/models.dev 映射/余额查询，走 OpenAI 兼容协议。

## 内容

- `providers/openrouter_provider.py` — 注册 OpenRouter 服务商定义
  - API：`https://openrouter.ai/api/v1`（OpenAI 兼容，Bearer 认证）
  - 模型列表：Claude / GPT / Gemini / DeepSeek / Grok / Qwen / Kimi 等热门型号
  - 余额查询：`GET /api/v1/credits`，余额 = total_credits − total_usage（美元）
- `providers/icons/openrouter.svg` — 深色主题图标
- `providers/icons_light/openrouter.svg` — 浅色主题图标

## 说明

OpenRouter 为聚合网关，协议层直接复用系统内置 `openai-family` 适配器，无需自定义 model_adapter。

获取 API Key：https://openrouter.ai/keys

> 由 evolution_scaffold 生成。
