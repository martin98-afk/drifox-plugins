# Command Code

Command Code 服务商插件，将 Command Code 聚合网关接入 DriFox。数据（icon / API URL / 默认参数 / 模型列表 / family 能力）全部由本插件声明，DriFox 运行时不再硬编码。

## 是什么

Command Code 是一个模型聚合网关：把 Claude / GPT / Gemini / DeepSeek / Kimi / GLM / MiniMax 等主流与开源模型统一在一个 OpenAI 兼容 API 下，按量付费、无加价，deal 自动生效。本插件通过 Provider API 把任意模型暴露给 DriFox。

## 端点

- 协议：OpenAI Chat Completions 兼容（`family` 走系统 openai-family）
- Base URL：`https://api.commandcode.ai/provider/v1`
- 对话：`POST /provider/v1/chat/completions`
- 鉴权：`Authorization: Bearer <API_KEY>`

## 组件

- `providers/command_code.py` — 注册 `Command Code` 服务商定义。
- `icon.svg` / `icon_dark.svg` — 服务商图标（命令提示符风格）。

## 配置

1. 在 [Studio → Provider](https://commandcode.ai/studio/provider) 生成 API key（与 CLI 共用，需 Provider 套餐或更高）。
2. DriFox 设置 → 模型服务商 → 添加 `Command Code`，填入 API key。
3. 选择模型（默认 `deepseek/deepseek-v4-flash`）。

## 模型列表

`models` 仅内置代表性精选。**完整模型 ID 以官方为准**，可用以下任一方式查询：

- 官方 CLI：`cmd --list-models`
- HTTP：`GET https://api.commandcode.ai/provider/v1/models`（Bearer 鉴权）
- 官网：[Available Models](https://commandcode.ai/docs/reference/cli/models)

模型 ID 大小写不敏感，支持完整 id（`moonshotai/Kimi-K2.5`）或 `/` 后的短名（`kimi-k2.5`）。DriFox 也支持手动输入任意合法 model id。

## 能力声明

`capabilities` 取聚合网关各旗舰模型的公共交集（vision / thinking 主流模型均支持）。个别模型的实际上下窗口与能力以官方为准。

## 说明

- 本插件仅声明服务商接入，不缓存任何凭据。
- 余额 / 用量查询（`balance_fetcher` / `coding_plan_fetcher`）暂未接入——Command Code 暂无公开的用量查询 API，后续版本可扩展。
