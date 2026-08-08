---
name: voice-clone
description: MiniMax 语音克隆技能 — 当用户需要克隆声音/音色、用特定人声朗读文本、生成 TTS 语音、复刻音色时使用。支持上传音频样本克隆 voice_id 并用克隆音色合成语音。常用词：语音克隆、克隆声音、音色、voice clone、TTS、配音。
---

# MiniMax 语音克隆

## 适用场景

- 用户说「克隆我的声音」「用 XX 的声音读这段文字」「生成配音」「做 TTS」
- 需要复刻某个音色并反复使用
- 有音频样本（自己录音/别人授权的声音），想变成可复用的语音

## 工作流

```
[音频样本 10s+ wav/mp3/m4a] ──► upload ──► file_id
                                          │
[voice_id 自定义] ◄── clone ──► 克隆音色（永久有效）
                                          │
[任意文本] ──► tts ──► 克隆音色朗读的 mp3
```

## 核心脚本

```bash
# 1. 克隆音色（一次即可，voice_id 永久）
python plugins/voice-clone/scripts/voice_clone.py clone \
  --audio sample.wav --voice-id myvoice2026 \
  --text "你好，这是我的克隆声音试听" \
  --text-validation "音频样本里实际说的话"

# 2. 之后直接合成（无需再克隆）
python plugins/voice-clone/scripts/voice_clone.py tts \
  --voice-id myvoice2026 --text "要合成的文本" --output out.mp3
```

## 参数速查

| 参数 | 说明 |
|------|------|
| `--audio` | 样本路径（mp3/m4a/wav，10s~5min，≤20MB） |
| `--voice-id` | 音色 ID（8-256 字符，字母开头，不可与已有重复） |
| `--text` | 克隆时试听文本 / tts 时合成文本（≤1000 字符） |
| `--text-validation` | 样本预期文本（可选，ASR 校验防传错） |
| `--accuracy` | ASR 阈值 0-1（默认 0.7） |
| `--noise-reduction` | 开启降噪 |
| `--speed` | 语速 0.5-2.0（默认 1.0） |

## 语气词标签（speech-2.8-hd）

文本中可插入 `(breath)` 换气、`(laughs)` 笑、`(sighs)` 叹气、`(coughs)` 咳嗽、`(pauses)` 停顿等，让语音更自然。

## 最佳实践

- **样本质量**：10-30 秒清晰无噪人声效果最佳；背景噪音大时加 `--noise-reduction`
- **复用**：克隆一次 → voice_id 永久有效 → 之后只跑 tts，零重复开销
- **授权**：仅克隆用户有权使用的声音；不用于冒充、欺诈
- **计费**：clone 时带 `--text` 试听按字符计费；tts 合成按字符计费；上传文件本身免费
- **失败排查**：`file expired` → 重新上传；`1043 ASR 相似度低` → 检查 `--text-validation` 是否与样本内容一致

## 配置 API Key

```bash
set MINIMAX_API_KEY=your_key_here        # Windows
echo your_key > %USERPROFILE%\.minimax\api_key
```
