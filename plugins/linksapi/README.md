# LinksAPI 中转

[LinksAPI](https://linksapi.cn) 服务商插件 — 国内直连的 OpenAI 兼容中转网关，聚合 GPT 全系模型，微信/支付宝充值，按量计费。

## 功能

- 注册 LinksAPI 服务商到 DriFox 服务商列表（providers 组件）
- 图标取自官网品牌 logo
- 预置「GPT低价特供」分组实测可用模型列表，可在设置中手动增删

## 配置

1. 设置 → 服务商 → LinksAPI
2. API URL 默认 `https://linksapi.cn/v1`，无需修改
3. 填入在 [LinksAPI 控制台](https://linksapi.cn/keys) 创建的 API Key
4. 选择模型即可对话

## 实测备注（2026-11-18）

- GPT-6.2 系列暂未上架（发布次日，渠道未同步）
- 「GPT低价特供」为低价号池分组：请求会被注入约 4200 token 的渠道侧上下文（计费含缓存折扣），能力可能低于官方满血
- 需要不降智渠道请在 LinksAPI 控制台切换分组后手动更新模型列表

## 许可

GPL-3.0-or-later
