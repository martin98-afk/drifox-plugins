# Voice Reply - 消息卡片语音朗读

消息卡片页脚「朗读」按钮：点击播报本条 AI 回复，再次点击停止（在线引擎）或打断重播（本地引擎）。双引擎设计，**零第三方依赖**。

## 引擎

| 引擎 | 平台 | 成本 | 说明 |
|------|------|------|------|
| 本地系统语音（默认） | Windows | 免费 | SAPI5 COM 接口（`win32com`，随 DriFox 运行环境自带），自动选中文语音 |
| 本地系统语音（默认） | macOS | 免费 | 系统 `say` 命令 |
| 在线 API | 全平台 | 按量（极低） | OpenAI 兼容 `POST /audio/speech`，默认预填硅基流动 CosyVoice2-0.5B，也可指向任意兼容服务 |

### 关于免费在线 TTS

调研结论（2026-10）：**没有官方长期完全免费的 TTS API**（语音识别有硅基流动免费模型，TTS 没有对应免费档）。两条接近免费的路径：

1. **硅基流动 CosyVoice2**：¥7.15/百万 UTF-8 字节，500 字回复约 0.00001 元，注册送额度，默认预填；
2. **自部署 Edge TTS**：[openai-edge-tts](https://github.com/travisvn/openai-edge-tts) 等项目把微软 Edge 朗读接口（真免费无 Key）包装成 OpenAI 兼容服务，部署后把「API 地址」改为自部署端点即可，Key 随便填。

## 配置

设置 → 语音播报配置（声明式 config_schema，即改即生效）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 语音引擎 | 本地系统语音 | `local` / `api` |
| API 地址 | 硅基流动端点 | OpenAI 兼容 `/audio/speech` |
| 模型 | `FunAudioLLM/CosyVoice2-0.5B` | 服务端模型名 |
| 音色 | `FunAudioLLM/CosyVoice2-0.5B:alex` | 硅基流动格式 `模型名:音色名` |
| API Key | 空 | 环境变量 `TTS_API_KEY` 可覆盖 |

在线合成固定请求 wav 格式：Windows 走 `winsound`、macOS 走 `afplay` 播放，音频文件落在系统临时目录、播完即删。

## 工作原理

插件以 UI 组件形态注册消息卡片页脚动作（`register_footer_action`，与内置复制/分支按钮同排）：

1. 点击按钮 → 取本条消息纯文本 → 轻度清洗 markdown 标记 → 截断至 500 字；
2. 本地引擎：主线程直接播报（SAPI5 异步队列打断重播 / `say` 进程重建）；
3. 在线引擎：QThread worker 合成（urllib，50 秒超时）→ wav 落临时文件 → 播放；合成/播放期间再次点击即停止。

## 依赖

无需安装任何依赖。本地引擎用系统自带能力，在线引擎用标准库 `urllib` + 系统 `winsound`/`afplay`。

> Windows 本地语音要求系统已安装中文语音包（一般 Windows 10/11 自带），验证：
>
> ```powershell
> powershell -NoProfile -Command "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Speech'); $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
> ```
