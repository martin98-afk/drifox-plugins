# anthropic

Anthropic (Claude) 服务商插件，将 Claude 系列模型接入 DriFox。数据（icon / API URL / 默认参数 / 模型列表 / family 能力）全部由本插件声明，DriFox 运行时不再硬编码。

## 组件

- `providers/anthropic.py` — 注册 `Anthropic (Claude)` 服务商定义。

## 使用

安装后，模型选择器即可选用 Claude 系列模型，无需修改 DriFox 运行时。
