# Gateway Telegram - DriFox 插件

Telegram 机器人平台适配器（社区插件，万物即插件 Phase E）：私聊/群组/论坛主题/媒体/命令，基于 python-telegram-bot 长轮询。

从 DriFox 主程序迁出，平台适配器独立成社区插件。

## 功能

- 注册平台适配器到 DriFox GatewayRegistry
- 通过 `check_requirements()` 自检依赖是否可用
- 提供 `_build_config` / `_write_config` / `_build_config_values` / `validate_config` 完整配置面板接口
- `register(registry)` 自动激活平台（ui_order 在 30-60 之间由各平台决定）

## 安装

### 方式一：从插件市场安装

```bash
/plugin --install gateway-telegram
```

### 方式二：复制到插件目录

```bash
cp -r plugins/gateway-telegram ~/.drifox/plugins/
# 或 Windows
xcopy /E /I plugins\gateway-telegram %USERPROFILE%\.drifox\plugins\gateway-telegram
```

DriFox 启动时自动发现并加载。

## 配置

在 DriFox 设置面板 → Gateway 中开启并填写：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `false` | 是否启用此平台 |
| `token` | text | `` | Bot Token（向 @BotFather 申请） |
| `require_mention` | bool | `true` | 群组中是否需要 @机器人 才触发 |

## 依赖

本插件 SDK 已自带 `deps/` 目录，**无需 `pip install`**；宿主启动时由插件顶层注入路径加载。

## 架构

- 适配器实现完整自 `<DriFox>/plugins/system/gateways/telegram.py` 迁入
- SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK，仅 `check_requirements()` 与 `connect()` 内按需 import
- 顶层 deps 注入路径：`telegram/gateways/telegram.py` 的 `..` 即 `telegram/deps/`
