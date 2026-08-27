# Gateway Feishu - DriFox 插件

飞书 (Feishu/Lark) WebSocket 模式适配器（社区插件，万物即插件 Phase E）：实时消息收发，基于 lark-oapi SDK。

从 DriFox 主程序迁出，平台适配器独立成社区插件。

## 功能

- 注册平台适配器到 DriFox GatewayRegistry
- 通过 `check_requirements()` 自检依赖是否可用
- 提供 `_build_config` / `_write_config` / `_build_config_values` / `validate_config` 完整配置面板接口
- `register(registry)` 自动激活平台（ui_order 在 30-60 之间由各平台决定）
- Markdown 富文本卡片：消息以 interactive 卡片发送（`# 标题` 提为卡片头），失败自动回退纯文本
- **命令交互卡片（v1.2.0）**：`/help` `/model` `/session` `/agent` 的回复渲染为专属交互卡片，点按钮直达操作：
  - `/help` → 命令说明卡 + 「新会话 / 模型 / 会话 / Agent」快捷按钮
  - `/model` → 服务商分区 + 模型按钮，**点击模型立即切换**
  - `/session` → 会话列表 + 「切换」按钮，点击即加载
  - `/agent` → Agent 列表 + 「使用」按钮
  - 按钮点击经 `card.action.trigger` 回传，与手敲命令完全同路；无法识别的命令输出自动回退 Markdown 卡片

## 安装

### 方式一：从插件市场安装

```bash
/plugin --install gateway-feishu
```

### 方式二：复制到插件目录

```bash
cp -r plugins/gateway-feishu ~/.drifox/plugins/
# 或 Windows
xcopy /E /I plugins\gateway-feishu %USERPROFILE%\.drifox\plugins\gateway-feishu
```

DriFox 启动时自动发现并加载。

## 配置

在 DriFox 设置面板 → Gateway 中开启并填写：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `false` | 是否启用此平台 |
| `app_id` | text | `` | 飞书应用 App ID |
| `app_secret` | password | `` | 飞书应用 App Secret |
| `encrypt_key` | password | `` | Encrypt Key（可选） |
| `verification_token` | text | `` | Verification Token（可选） |

### 卡片按钮交互前提（v1.2.0）

在 [飞书开放平台](https://open.feishu.cn/app) 应用后台：

1. **事件与回调** → 事件配置 → 订阅方式选择「**使用长连接接收事件**」（无需公网地址）
2. 添加事件：**`card.action.trigger`（卡片回传交互）**——不订阅则点按钮无响应（其余功能不受影响）
3. **权限管理** 已默认具备 `im:message` 收发权限即可

> 限制：服务商名称含空格时，其模型不生成按钮（宿主命令解析歧义），仅文本展示。

## 依赖

本插件 SDK 已自带 `deps/` 目录，**无需 `pip install`**；宿主启动时由插件顶层注入路径加载。

## 架构

- 适配器实现完整自 `<DriFox>/plugins/system/gateways/feishu.py` 迁入
- SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK，仅 `check_requirements()` 与 `connect()` 内按需 import
- 顶层 deps 注入路径：`feishu/gateways/feishu.py` 的 `..` 即 `feishu/deps/`
- 命令卡片识别对齐宿主 `app/core/engines/gateway/engine.py` 的命令文案格式；宿主改版时解析自动回退通用 Markdown 卡片
- **vendor SDK 补丁**：`deps/lark_oapi/ws/client.py` 修复上游 bug（[oapi-sdk-python#126](https://github.com/larksuite/oapi-sdk-python/issues/126)）——CARD 帧被静默丢弃导致 `card.action.trigger` 永不触发，补丁让 CARD 帧走事件分发路径（已标注 PATCH 注释，升级 SDK 时需保留）
