# multimodal-providers

多模态能力服务商定义插件：把图像生成 / 视频生成 / 语音合成 / 语音识别四类能力服务商从主程序内置迁出，并补齐插件生态里实际在用的服务商，改为按需安装。

## 服务商清单

| 文件 | 服务商 | `capability_type` | 端点 | 来源 |
|---|---|---|---|---|
| `providers/volcengine_multimodal.py` | 豆包语音合成 | `speech_generation` | `openspeech.bytedance.com/api/v1/tts` | 主程序迁出 |
| `providers/volcengine_multimodal.py` | 火山方舟图像 | `image_generation` | `ark.cn-beijing.volces.com/api/v3` | 主程序迁出 |
| `providers/volcengine_multimodal.py` | 豆包录音识别 | `speech_recognition` | `openspeech.bytedance.com/api/v3/asr` | 主程序迁出 |
| `providers/minimax_video.py` | 海螺视频 | `video_generation` | `api.minimaxi.com/v1` | 主程序迁出 |
| `providers/minimax_video.py` | 海螺视频 H3 | `video_generation` | `api.minimaxi.com/v2/video_generation` | `minimax-h3` |
| `providers/minimax_speech.py` | MiniMax 语音合成 | `speech_generation` | `api.minimaxi.com/v1/audio/speech` | `voice-reply` / `voice-clone` |
| `providers/minimax_speech.py` | MiniMax 语音识别 | `speech_recognition` | `api.minimaxi.com/v1/speech_to_text` | `voice-input` |
| `providers/siliconflow_multimodal.py` | 硅基流动语音合成 | `speech_generation` | `api.siliconflow.cn/v1/audio/speech` | `voice-reply` |
| `providers/siliconflow_multimodal.py` | 硅基流动语音识别 | `speech_recognition` | `api.siliconflow.cn/v1/audio/transcriptions` | `voice-input` / `meeting-notes` |
| `providers/openai_multimodal.py` | OpenAI 图像生成 | `image_generation` | `api.openai.com/v1/images/generations` | `gpt-image-2` |
| `providers/openai_multimodal.py` | OpenAI 语音合成 | `speech_generation` | `api.openai.com/v1/audio/speech` | `voice-reply` |
| `providers/zhipu_speech.py` | 智谱语音合成 | `speech_generation` | `open.bigmodel.cn/api/paas/v4/audio/speech` | `voice-reply` |

模型列表按来源插件的预置与官方文档填写，可在服务商编辑卡里手改成任意模型名。

## 安装后

- 服务商设置页的服务商墙按 `capability_type` 动态分组，出现「图像生成 / 视频生成 / 语音合成 / 语音识别」组头。
- 每条都是独立 `ProviderDef`，12 条 `api_url` 互不相同，`config_id = hash(URL, KEY)` 不会与彼此或各家 chat 配置撞车。
- 能力实例的取用走能力池：`config_for(query, capability_type=...)`，由调用方按意图过滤候选。

## 说明

- 本插件只做**服务商声明**，不含具体的图像/视频/语音请求实现；实际调用由使用方按 `capability_type` 取配置后自行发起。
- 未收录：即梦（CLI + Cookie 登录）、可灵 / Tripo3D（MCP + OAuth）、inference.sh 系列（command 平台）。这些不是 bearer-key 型 HTTP 服务，塞进 `ProviderDef` 表达不了认证方式，走各自插件。
- 依赖宿主 `ProviderDef.capability_type` 字段，故 `min_host_version` 声明为 `0.7.1`。老宿主加载会因构造参数不识别而失败，请勿降级安装。
