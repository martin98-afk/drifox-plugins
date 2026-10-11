# grok-oauth

xAI Grok 服务商插件（OAuth 登录制）：用 SuperGrok / X Premium+ 订阅账号浏览器授权登录，直连 Grok 系列模型，无需 API Key。

## 前置条件

- **SuperGrok**（grok.com 订阅）或 **X Premium+**（绑定 X 账号）订阅（免费层无 OAuth 编程权益）
- 网络可达 `auth.x.ai` 与 `cli-chat-proxy.grok.com`
- 本地 `127.0.0.1:56121` 端口空闲（登录回调用，Grok CLI / OpenCode 登录也用它）

## 登录步骤

1. DriFox「设置 → 模型服务商」新增配置，服务商选 **Grok OAuth**
2. 点「登录」：自动打开 auth.x.ai 授权页
3. 登录 SuperGrok / X Premium+ 账号并点授权
4. xAI 自动回调本机 `127.0.0.1:56121`，DriFox 自动完成登录（无需复制任何内容）
5. 长效 `refresh_token` 自动回填到 API Key 输入框 → **保存配置**

## 工作方式

- API Key 字段存**长效 refresh_token**；聊天时自动换取**短效 access_token**（临期自动刷新，本地缓存）
- 请求走 xAI 订阅通道 `cli-chat-proxy.grok.com/v1` 的 **Responses API**（`/responses`），与 Codex 插件同形态；`api.x.ai/v1` 为 API Key 专用，OAuth 凭证不可用
- 模型池经 `/v1/models-v2` 按订阅实时拉取（点「获取模型列表」），内置列表仅兜底

## 已知限制

- 订阅通道协议为社区实践（复用 Grok CLI 公开 client_id），**未经 xAI 官方承诺**：权益判定以账号为准，若请求返回 403，多为订阅档位权益限制（SuperGrok Heavy 才开放编程模型的时期曾出现）
- refresh_token 轮换后以本地缓存的新值为准；若缓存目录被清理且旧 token 已轮换失效，需重新登录
- 非官方客户端协议实现，存在违反服务条款与封号风险，**请自行评估**
