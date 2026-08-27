# gateway-wechat

微信机器人适配器（iLink 官方接口），DriFox Gateway 插件。

## 功能

- **扫码登录**：官方 iLink 接口（`ilinkai.weixin.qq.com`），无需公众号/企业微信配置
- 单聊消息收发（HTTP 长轮询 `getupdates`，游标持久化断点续传）
- 被动回复复用 `context_token`（24h 窗口），支持文本/引用消息/语音转文字
- token 失效（errcode -14）自动停止并提示重新扫码

## 快速开始

1. 在对话中让 AI 调用工具：
   - `wechat_login(action="get_qr")` → 返回二维码 PNG 路径
   - 微信扫码 → `wechat_login(action="poll", qrcode_id="...")` → 自动写入 bot_token
2. 设置中启用「微信网关」开关
3. 微信里给机器人发消息即可对话

## 使用注意

- 仅单聊（iLink 官方接口无群聊能力）
- 仅被动回复：对方 24h 内发过消息才能回复
- bot_token 长期失效后需重新扫码（约 24h 不活动或服务端踢下线）
- 协议为官方 iLink Bot 接口（同 openclaw-weixin / openhanako 方案），非个人号协议，无封号风险

## 配置

| 字段 | 说明 |
|------|------|
| 启用微信网关 | 开关 |
| Bot Token | 扫码自动写入（也可手动粘贴） |

## 依赖

无额外宿主依赖——复用宿主 httpx；二维码渲染使用插件自包含的 `deps/segno`（零依赖纯 Python，MIT）。

## 致谢

- [openhanako](https://github.com/liliMozi/openhanako) `lib/bridge/wechat-login.ts` / `wechat-adapter.ts`（Apache-2.0）
- [Tencent/openclaw-weixin](https://github.com/Tencent/openclaw-weixin)（MIT）
- [segno](https://github.com/heuer/segno)（MIT）
