# 软件服务AI 中转站

[软件服务AI API中转站](https://s.rjfw.com)（s.rjfw.com，站点副标题 ZLY-Sub2API）服务商插件 — OpenAI 兼容聚合网关，覆盖 GPT / Claude / Gemini / Grok / DeepSeek / Kimi / 智谱。

## 功能

- 注册「软件服务AI」服务商到 DriFox 服务商列表（providers 组件）
- 「获取模型列表」按你手上的 Key 拉真实可用池（`GET /v1/models`）
- 内置 53 个文本模型作为未填 Key 时的全貌兜底
- 余额查询：用 API Key 直接调 `GET /v1/usage`，显示钱包余额（USD），不需要登录网页
- 图标取自站点官方 logo
- gpt-5+ 自动走 `/v1/responses`（系统协议家族判定），其余走 `/v1/chat/completions`

## 配置

1. 在 [控制台](https://s.rjfw.com/keys) 创建 API Key（注册目前仅限 `@qq.com` 邮箱）
2. 设置 → 服务商 → 软件服务AI
3. API URL 默认 `https://s.rjfw.com/v1`，无需修改
4. 填入 API Key，卡内显示钱包余额；点「获取模型列表」拉到本组可用模型
5. 选择模型即可对话

## 分组机制（最容易踩的坑）

本站按「分组」售卖，**一个 Key 只能访问所属分组的模型**。拿别组的模型名请求会回：

```
404 Model "claude-sonnet-5" is not supported by any configured account in this group
```

| 分组示例 | 平台 | 倍率 |
|---|---|---|
| GPT-福利 | openai | 0.028 |
| GPT-PRO | openai | 0.2 |
| 国模-DEEPSEEK / K3 / GLM | deepseek / kimi / zhipu | 0.5 / 0.5 / 0.9 |
| Claude福利 / Claude | anthropic | 0.7 / 1.0 |
| GEMINI-全模型-官转 | gemini | 4.0 |

完整分组与价格见站点[模型广场](https://s.rjfw.com/model-plaza)。插件内置清单是全平台混列，买了哪个组的 Key 就点「获取模型列表」覆盖成本组真实池，或手工删掉用不到的项。

图像与 TTS 模型（gpt-image-2 系列、gemini-*-image、nano-banana、flash-tts）不列入：模型下拉用于对话，选中会报错。

## 实测记录（2026-11-27，GPT-福利组 Key）

| 项 | 结果 |
|---|---|
| `POST /v1/chat/completions` | 200，8 个 gpt 模型全部可用 |
| `POST /v1/responses` | 200 |
| `POST /v1/messages` | 403 `This group does not allow /v1/messages dispatch`（分组级开关） |
| `GET /v1/models` | 200，返回本组 8 个模型（余额为 0 时 403 `INSUFFICIENT_BALANCE`） |
| `GET /v1/usage` | 200，`{balance, remaining, unit, isValid, planName, usage.today, usage.total}` |
| `reasoning_effort: "high"` | 200，思考参数按此语义声明 |
| `image_url` 视觉输入 | 200 |
| `stream: true` | 标准 `chat.completion.chunk` SSE |
| 跨分组模型（claude/gemini/grok/国模） | 404 `model_not_found` |

**渠道侧提示注入**：多数 gpt 模型的上游是 Codex 账号池，`prompt_tokens` 会被注入 4100~5400 token 的系统提示（回复常以 "What would you like me to work on?" 开场），按缓存折扣计费。实测 `gpt-6.1-sol` 只有 7 token，故设为默认模型。

## 未验证项

- Claude / Gemini / Grok / 国模的真实通道：本次只有 GPT 组 Key，买 Claude 组后需要复测「claude 能否走 `/v1/chat/completions`」。若报「不支持该接口」，说明该组只放 `/v1/messages`，届时需补 protocol router 适配器（参考 `oaipro-provider` 的 `oaipro_router.py`）。
- 各模型的真实上下文窗口：插件里按平台取保守值（gpt 组广场标注 272K、claude 200K、国模 128K），未逐模型压测。

## 许可

GPL-3.0-or-later