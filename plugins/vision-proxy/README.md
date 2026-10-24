# vision-proxy — 图片代理

当前模型不支持视觉时，把图片转发给配置好的多模态模型，取回文字描述交给当前  
模型继续推理。

## 它解决什么

DriFox 在发送前判断当前模型的 `supports_vision`：不支持时，图片附件只作为文件  
路径文本拼进正文，模型「看」不到图（`app/main_widget.py` 的 `[ImageAttach]` 分支）。  
本工具补上这条断层——AI 主动调用，把图片交给会看图的模型，拿回文字描述。

## 用法

安装后在插件设置里填：

| 字段      | 说明                                                                                              |
| ------- | ----------------------------------------------------------------------------------------------- |
| 视觉服务商   | 承接图片理解的服务商名（config_id / 显示名 / provider_name 均可）。留空 = 用当前服务商                                     |
| 视觉模型    | 必须支持图像输入的模型名（如 `gpt-4o`、`claude-sonnet-4-20250514`、`gemini-2.0-flash`、`qwen-vl-max`）。留空 = 用当前模型 |
| 超时（秒）   | 默认 120；思考模型建议 ≥180                                                                              |
| 单次最多图片数 | 默认 4                                                                                            |

之后 AI 在需要看图时自行调用 `vision_describe`：

```
vision_describe(paths=["D:/work/shot.png"], question="读出截图里的报错文字")
```

支持本地路径与 `http(s)` 图片 URL，一次可传多张（单张 ≤8MB）。

## 实现要点

- 请求走宿主 `create_engine_session` + `model_config_override`，不自建 HTTP client。    
  协议适配（chat/responses、thinking 参数）、单向伪装头、max_tokens 钳制、智能    
  重试全在引擎里，自建直发会丢这些。
- 引擎以 `hook_policy="none"` + `permission_strategy="auto_deny"` + `tools=[]` 钳成    
  纯问答：不触发全局 hook，不给任何工具。
- `turn()` 跑在 daemon 线程，外层另有硬看门狗（timeout + 30s 后下发 cancel）。
- 图片走 OpenAI multimodal `image_url` 块（本地文件 base64 成 data URI）。

## 能力声明

`engine.session` 与 `model.config` 的 provider 只注册在 **ui surface**  
（`app/plugins/capabilities/providers/ui_core.py`），而工具插件的  
`tool_ctx["services"]` 只投影 tool surface。所以代码里用  
`pool_for(plugin=..., surface="ui")` 跨面取，宿主按插件名解析到活跃窗口。

代价：无活跃窗口时取不到能力，工具返回明确错误而不是静默失败。
