# ollama

Ollama 服务商插件，将本地推理模型接入 DriFox。数据（icon / API URL / 默认参数 / 模型列表 / family 能力）全部由本插件声明。

## 组件

- `providers/ollama.py` — 注册 `Ollama` 服务商定义（默认 `http://localhost:11434/v1`）。

## 使用

安装后，模型选择器即可选用 Ollama 本地模型（llama3 / qwen2.5 / mistral 等），无需修改 DriFox 运行时。
