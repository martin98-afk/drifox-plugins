# oaipro-provider

OAIPro（api.oaipro.com）中转站服务商插件，含一条自带协议通道。

## 为什么需要这个插件

OAIPro 按**模型**硬性分流协议，同一 Base URL 下三条端点并存（2026-11-16 实测）：

| 模型族 | 唯一可用端点 | 直接用 OpenAI 兼容客户端会怎样 |
|---|---|---|
| `gpt-4o` / `gpt-4.1` / `gpt-5.x`（非 pro）/ `gpt-6.x` / `o3` / `chat-latest` | `/v1/chat/completions` | 正常 |
| `gpt-5-pro` / `gpt-5.x-pro` / `gpt-5.3-codex` / `o3-pro` | `/v1/responses` | 404「Use v1/responses instead」 |
| `claude-*` | `/v1/messages`（Anthropic 原生） | 403「模型 xxx 不支持 /v1/chat/completions 接口」 |

DriFox 宿主自带 `openai_chat` 与 `openai_responses` 两条通道，没有 anthropic 通道，
所以 Claude 模型原本无法在本站使用。本插件补上第三条通道。

## 组件

| 组件 | 文件 | 作用 |
|---|---|---|
| providers | `providers/oaipro.py` | 注册「OAIPro」（GPT 系）与「OAIPro Claude」两条服务商 + 余额查询 |
| model_adapters | `model_adapters/oaipro_router.py` | 按模型名选通道：`claude-*` → `anthropic_messages`，`*-pro`/`*-codex` → `openai_responses` |
| transports | `transports/anthropic_messages.py` | Anthropic Messages 协议：请求组装 + SSE → StreamEvent 归一 |

路由仅对 `API_URL` 含 `oaipro.com` 的配置生效，不劫持其他服务商的同名模型。

## 使用

1. 设置 → 服务商 → 新建
2. **GPT 系**：服务商选 `OAIPro`，填 API Key（在 https://api.oaipro.com/token 生成）
3. **Claude 系**：服务商选 `OAIPro Claude`，同一个 Key 即可
4. 模型列表可自行「获取模型列表」或按需增删

## 查余额

本站**没有 API key 级余额接口**（`/v1/dashboard/billing/*`、`/api/user/self`、
`/api/usage/token` 全部 404），唯一能读余额的 `/backend-api/users/me` 需要网页登录态，
而登录接口强制 Turnstile 人机验证，脚本无法自动登录。因此余额靠手动粘贴 Cookie：

1. 浏览器打开 https://api.oaipro.com 并登录
2. F12 → Network → 点任一 `backend-api` 请求 → 复制请求头里的 `Cookie` 整行
3. 服务商编辑卡 → 展开「套餐用量查询（可选）」→ 粘贴到 `Cookie:` 字段 → 保存

余额栏显示 `$xx.xx`。Cookie 过期后余额自动隐藏并提示重新复制，不影响聊天。

额度换算：`user.quota ÷ quota_per_unit`，其中 `quota_per_unit` 从公开接口
`/backend-api/status` 实时读取（本站当前 500000），站点调单位时自动跟随。

## 已知限制

- Claude 通道暂不透传 thinking block 的 `signature`。实测本站第二轮请求丢掉 thinking
  仍返回 200（不强制校验），但若上游将来收紧，多轮思考模式可能报 400。
- 只收录实测可路由的模型；站点新增模型需手动加到模型列表。
- 余额查询依赖网页 Cookie，属站点私有接口，改版可能失效。

## 验证记录（2026-11-16，真实 API 请求）

| 用例 | 结果 |
|---|---|
| 纯文本（claude-haiku-4-5） | 200，29 个 StreamEvent，finish=stop |
| 工具调用 | 200，`tool_call_begin` + `input_json_delta` 正确拼接为 `{"city": "北京"}`，finish=tool_calls |
| 工具结果回传（tool role → tool_result） | 200，正文正确 |
| 开启思考 | 200，`reasoning_delta` 正常产出 |
| 错误路径（gpt 走 anthropic 通道） | 403 明确报错，不静默失败 |
| 余额：无 Cookie | 返回 None（不请求） |
| 余额：坏 Cookie | `{"hide": true, "tooltip": "Cookie 已失效..."}` |
| 取消路径 socket 探测 | SSLSocket 可定位，worker 可半关闭唤醒 |
