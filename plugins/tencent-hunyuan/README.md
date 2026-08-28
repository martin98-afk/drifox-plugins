# Tencent Hunyuan (TokenHub) 服务商插件

把腾讯混元 Hy 系列大模型接入 DriFox 作为可选服务商，走腾讯云 **TokenHub**
OpenAI 兼容协议（`/v1/chat/completions`），Bearer 鉴权，无需自定义 model_adapter
（协议由系统 openai-family 兜底适配器处理）。

## 接入步骤

1. 打开腾讯云控制台创建 API Key：
   https://console.cloud.tencent.com/tokenhub/apikey
   - 注意 Key 的「可访问范围」需勾选对应模型（如 `hy4-preview`）。
2. 在 DriFox 服务商设置里选 **Tencent Hunyuan**，粘贴 API Key 即可。
3. 模型选择器默认 `hy4-preview`，可切 `hy3`。

## 模型

| 模型 | 说明 | 免费窗口 |
|---|---|---|
| `hy4-preview` | 混元新一代开源 MoE，770B / 激活 49B，1M 上下文，代码/办公/推理 | WorkBuddy/CodeBuddy 限免 2 周（约 2026-09-11 止） |
| `hy3` | 混元上一代，性价比高 | 免费延至 2026-09-30 |

> 限免期后经 TokenHub 计费：输入 ¥6 / 百万 token，输出 ¥18 / 百万 token，缓存命中 ¥0.30 / 百万 token。

## 配置文件

- `providers/tencent_hunyuan.py` — `ProviderDef` 注册（icon / API URL / 模型列表 / family 能力）。
- `providers/icons/` · `providers/icons_light/` — 深浅主题图标（`tencenthunyuan.svg`）。

## 已知注意点（TODO 验证）

- **思考模式参数格式**：混元 OpenAI 路径文档示例为 `thinking: {type:"enabled"}`
  （嵌套对象），本插件沿用 OpenAI 通用 `thinking_param="thinking"`。若开启「思考模式」
  后请求报错，先关闭思考模式使用；格式兼容性问题需在框架层核对。
- `supports_vision` 暂设 `False`（Hy4 preview 以文本/代码为主，多模态能力待核实后开启）。
- `max_output_tokens` 暂保守设为 8192，后续按官方上限调整。
- 未配置余额查询 fetcher（TokenHub 暂无公开余额端点），UI 不显示余额。
