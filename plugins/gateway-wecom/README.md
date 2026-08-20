# Gateway WeCom - DriFox 插件

企业微信 (WeCom) AI Bot 适配器（社区插件，万物即插件 Phase E）：通过 WebSocket 长连接与 AI Bot Gateway 通信；不依赖第三方 SDK，复用宿主 aiohttp/httpx。

从 DriFox 主程序迁出，平台适配器独立成社区插件。

## 功能

- 注册平台适配器到 DriFox GatewayRegistry
- 通过 `check_requirements()` 自检依赖是否可用
- 提供 `_build_config` / `_write_config` / `_build_config_values` / `validate_config` 完整配置面板接口
- `register(registry)` 自动激活平台（ui_order 在 30-60 之间由各平台决定）

## 安装

### 方式一：从插件市场安装

```bash
/plugin --install gateway-wecom
```

### 方式二：复制到插件目录

```bash
cp -r plugins/gateway-wecom ~/.drifox/plugins/
# 或 Windows
xcopy /E /I plugins\gateway-wecom %USERPROFILE%\.drifox\plugins\gateway-wecom
```

DriFox 启动时自动发现并加载。

## 配置

在 DriFox 设置面板 → Gateway 中开启并填写：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `false` | 是否启用此平台 |
| `bot_id` | text | `` | 机器人 ID |
| `secret` | password | `` | 机器人密钥 |
| `websocket_url` | text | `wss://openws.work.weixin.qq.com` | WebSocket 地址（可选） |

## 依赖

本插件**不依赖第三方 SDK**，复用宿主已有的 `aiohttp` + `httpx`。

## 架构

- 适配器实现完整自 `<DriFox>/plugins/system/gateways/wecom.py` 迁入
- SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK，仅 `check_requirements()` 与 `connect()` 内按需 import
- 顶层 deps 注入路径：`wecom/gateways/wecom.py` 的 `..` 即 `wecom/deps/`
