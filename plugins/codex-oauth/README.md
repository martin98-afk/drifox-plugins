# codex-oauth

OpenAI Codex 服务商插件（OAuth 登录制）：用 ChatGPT 账号浏览器授权登录，以订阅额度直连 Codex Responses API，无需 API Key。

## 前置条件

- ChatGPT **Plus / Pro / Business / Enterprise / Edu** 订阅（Codex 额度随订阅档位而定；Free/Go 仅在桌面端可用 luna 系模型，本插件通道不可用）
- 网络可达 `auth.openai.com` 与 `chatgpt.com`

## 登录步骤

1. DriFox「设置 → 模型服务商」新增配置，服务商选 **OpenAI Codex**
2. 点「登录」：自动打开浏览器授权页，`user_code` 已复制到剪贴板
3. 在授权页粘贴 `user_code` → Continue → 完成授权
4. DriFox 自动回填长效 `refresh_token` 到 API Key 输入框 → **保存配置**

## 工作方式

- API Key 字段存**长效 refresh_token**；聊天时自动换取**短效 access_token**（临期 5 分钟自动刷新，本地缓存）
- 请求走 `https://chatgpt.com/backend-api/codex` 的 **Responses API** 形态（自动开启「使用ResponsesAPI」）
- 请求头伪装 Codex CLI（`originator` / `User-Agent` / `ChatGPT-Account-Id`）
- 模型池为内置静态列表（`gpt-6.1-sol` / `gpt-6-sol` / `gpt-6.1-luna` / `gpt-6-luna`），实际可用性随订阅档位而异

## 已知限制

- refresh_token 轮换后以本地缓存的新值为准；若缓存目录被清理且旧 token 已轮换失效，需重新登录
- 非官方客户端协议实现（复用 Codex CLI 公开 client_id），存在违反服务条款与封号风险，**请自行评估**
