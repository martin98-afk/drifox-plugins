# openai

OpenAI 服务商插件，将 GPT / ChatGPT 系列模型接入 DriFox。数据（icon / API URL / 默认参数 / 模型列表 / family 能力）全部由本插件声明，并内置 API 用量（月度额度）查询。

## 组件

- `providers/openai.py` — 注册 `OpenAI` 服务商定义，含 `coding_plan_fetcher` 用量查询。

## 使用

安装后，模型选择器即可选用 GPT 系列模型；配置 API Key 后自动拉取用量百分比。
