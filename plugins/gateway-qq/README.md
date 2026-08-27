# gateway-qq

QQ 机器人适配器（QQ 开放平台），DriFox Gateway 插件。

## 功能

- WebSocket 长连接接入 QQ 机器人开放平台（`wss://api.sgroup.qq.com/websocket`）
- 支持群聊 @ 消息（`GROUP_AT_MESSAGE_CREATE`）与单聊消息（`C2C_MESSAGE_CREATE`）
- 自动获取/刷新 access_token，op 协议心跳 + 断线指数退避重连 + **RESUME 会话恢复**（断线不丢消息）
- 被动回复优先复用事件 `msg_id`（无主动消息额度限制），**msg_seq 跨轮递增**防 QQ 判重吞消息
- **单聊流式打字机**（v1.1.0）：对接官方 `stream_messages` 接口
  - 支持平台流式时：工具进度 + AI 增量实时合并为一条打字机消息（replace 全量快照模式，≥600ms 节流，40007 前缀跳变自动跳帧/降级）
  - 平台不支持时：思考占位 + 工具进度折叠为一条追加式消息（append 模式），不再逐条刷屏
  - 接口 403/404/限流自动永久回退普通发送

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
- `stream_messages` 为官方单聊专属接口：群聊回复仍是逐条普通发送
- 流式体验需宿主 DriFox ≥ 含 `supports_streaming/start_stream/update_stream/finish_stream` 钩子的版本；旧宿主自动降级为 append 折叠流

## 变更记录

- v1.1.0：修复 msg_seq 每轮重置被 QQ 判重吞消息、群聊命令 `/` 前缀被误剥；新增 RESUME 会话恢复；接入官方 stream_messages 流式（replace 打字机 + append 折叠双模式，失败自动回退）
- v1.0.0：初版
