# anthropic-oauth

Anthropic Claude 服务商插件（OAuth 登录制）：用 claude.ai 账号浏览器授权登录，以 Pro/Max 订阅额度使用 Claude 系列模型，无需 API Key。

## 前置条件

- Claude **Pro / Max / Team / Enterprise** 订阅（免费层无 Claude Code 权益）
- 网络可达 `claude.ai` 与 `api.anthropic.com`

## 登录步骤

1. DriFox「设置 → 模型服务商」新增配置，服务商选 **Anthropic OAuth**
2. 点「登录」：自动打开 claude.ai 授权页
3. 登录并授权后，回调页会展示一串 code（形如 `xxxxx#yyyyy`）
4. **复制整段 code（Ctrl+C）**，DriFox 轮询剪贴板自动检测并换取 token
5. 自动回填长效 `refresh_token` 到 API Key 输入框 → **保存配置**

## 工作方式

- API Key 字段存**长效 refresh_token**；聊天时自动换取**短效 access_token**（临期自动刷新，本地缓存）
- 请求走 `api.anthropic.com/v1` 的 OpenAI 兼容层，OAuth 凭证自动携带 `anthropic-beta: oauth-2025-04-20` 头
- 请求头伪装 Claude Code CLI（`User-Agent` / `x-app`）
- 模型池经 `/v1/models` 按订阅实时拉取（点「获取模型列表」），内置列表仅兜底

## 已知限制

- OAuth 凭证走 OpenAI 兼容层为社区实践，**未经 Anthropic 官方承诺**：若请求返回 401，说明兼容层不接受 OAuth token，需等待原生 /v1/messages 协议通道支持
- refresh_token 轮换后以本地缓存的新值为准；若缓存目录被清理且旧 token 已轮换失效，需重新登录
- 非官方客户端协议实现（复用 Claude Code 公开 client_id），存在违反服务条款与封号风险，**请自行评估**
