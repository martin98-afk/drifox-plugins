# Voice Clone — MiniMax 语音克隆

基于 MiniMax 开放平台 `voice_clone` API 的语音克隆插件：上传 10 秒+ 音频样本，克隆音色为永久的 `voice_id`，再用该音色把任意文本合成为语音。

## 功能

| 命令/能力 | 说明 |
|-----------|------|
| `/voice-clone` | 引导式语音克隆流程（采集样本 → 克隆 → 合成） |
| `scripts/voice_clone.py clone` | 上传音频 + 克隆音色 + 可选试听 |
| `scripts/voice_clone.py tts` | 用克隆音色合成语音到本地 mp3 |
| `scripts/voice_clone.py upload` | 只上传音频拿 file_id |

## 使用

```bash
# 1. 配置 API Key（任选其一）
set MINIMAX_API_KEY=your_key_here
echo your_key > %USERPROFILE%\.minimax\api_key

# 2. 克隆音色（一次，永久有效）
python plugins/voice-clone/scripts/voice_clone.py clone \
  --audio sample.wav --voice-id myvoice2026 --text "试听文本"

# 3. 用克隆音色合成
python plugins/voice-clone/scripts/voice_clone.py tts \
  --voice-id myvoice2026 --text "要合成的文本" --output out.mp3
```

## 样本要求

- 格式：mp3 / m4a / wav
- 时长：≥10 秒，≤5 分钟
- 大小：≤20MB
- 质量建议：清晰、无背景噪音；10-30 秒人声最佳

## 注意

- 语音克隆涉及个人声音权益，**仅克隆用户有权使用的声音**，不得用于冒充或欺诈
- API Key 从环境变量 / `~/.minimax/api_key` 读取，不硬编码
- 试听与合成都按字符计费（与 MiniMax T2A 定价一致）；文件上传免费

## 许可证

MIT