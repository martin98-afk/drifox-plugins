# moonshot

Moonshot (Kimi) 服务商插件，将 Kimi 系列模型接入 DriFox。数据（icon / API URL / 默认参数 / 模型列表 / family 能力 / per-model 能力 / 余额查询）全部由本插件声明。

## 组件

- `providers/moonshot.py` — 注册 `Moonshot (Kimi)` 服务商定义（默认 `https://api.moonshot.cn/v1`，国际站 `https://api.moonshot.ai/v1` 可在预设 URL 中切换）。

## 模型

| 模型 | 上下文 | 视觉 | 思考 |
|---|---|---|---|
| `kimi-k3` | 1M | 支持 | 恒开，`reasoning_effort` 三档（low/high/max） |
| `kimi-k2.7-code` | 256K | 不支持 | 恒开（Preserved Thinking） |
| `kimi-k2.7-code-highspeed` | 256K | 不支持 | 恒开，与上者为同一模型仅速度不同 |

已下线的 `kimi-k2.5` / `moonshot-v1` 全系 / `kimi-k2` 系不录入。

`kimi-k2.6` 有意不录入：其 `temperature` 随思考模式变化（思考态 1.0 / 非思考态 0.6），而服务商默认参数是服务商级配置、不随模型切换，主程序也没有 per-model 参数覆盖机制。需要它请自行添加为自定义服务商并手动配温度。

## 使用

安装后在模型选择器选用 Kimi 模型，填写 API Key 即可。服务商编辑卡会显示账户可用余额（`available_balance`，含代金券与现金）。

K3 与 K2.7 Code 的 `temperature` / `top_p` / `n` / penalty 由服务端固定（1.0 / 0.95 / 1 / 0），传入其他值会报 `invalid_request_error`。插件已在默认参数中显式声明，请勿在参数卡修改这两项。
