# gateway-qq

QQ 机器人适配器（QQ 开放平台），DriFox Gateway 插件。

## 功能

- WebSocket 长连接接入 QQ 机器人开放平台（`wss://api.sgroup.qq.com/websocket`）
- 支持群聊 @ 消息（`GROUP_AT_MESSAGE_CREATE`）与单聊消息（`C2C_MESSAGE_CREATE`）
- 自动获取/刷新 access_token，op 协议心跳 + 断线指数退避重连
- 被动回复优先复用事件 `msg_id`（无主动消息额度限制）

## 配置

| 字段 | 说明 |
|------|------|
| AppID | 开放平台机器人 AppID |
| AppSecret | 开放平台机器人 AppSecret |
| WebSocket | 接入地址（默认官方正式环境） |

设置卡内提供「创建机器人」外链按钮，直达 [QQ 机器人开放平台](https://q.qq.com/)。

## 依赖

无额外依赖——复用宿主 aiohttp/httpx。

## 使用注意

- 群聊场景需机器人在群内且为公域模式；回复依赖被动 msg_id（有效期约 5 分钟）
- 单聊需用户先添加机器人好友并发起会话
