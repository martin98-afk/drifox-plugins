# Voice Reply - AI 回复语音播报

将 AI 回复文字转为语音播放，使用 Windows 自带离线 TTS（SAPI5），无需网络、**零第三方依赖**。

## 依赖

**无需安装任何依赖。** 插件直接调用 Windows SAPI5 COM 接口（`win32com`，随 DriFox 运行环境自带），
不依赖 `pyttsx3` 等第三方库。

> 要求：Windows 系统已安装中文语音包（如 Microsoft Huihui），一般 Windows 10/11 自带。

### 验证语音

```powershell
powershell -NoProfile -Command "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Speech'); $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
```

如果列表中有中文语音（如 `Microsoft Huihui Desktop`），即可正常播报。

## 配置

本插件默认监听 `PostAssistantMessage` 事件，在每次 AI 回复后自动朗读。

如需调整语音或语速，编辑 `hooks/voice-reply_hook.py` 中的：

| 配置项 | 代码位置 | 说明 |
|--------|----------|------|
| 中文语音选择 | `_get_engine()` 中 `"Chinese" in desc` | 自动选择中文语音，可改为其他关键词 |
| 语速 | `engine.Rate = 1` | SAPI 范围 -10 ~ 10，0 为正常 |
| 音量 | `engine.Volume = 100` | 范围 0 ~ 100 |
| 最大字符 | `MAX_TEXT_LEN = 500` | 截断阈值，避免语音队列过长 |

## 工作原理

DriFox 在 `PostAssistantMessage` 事件触发时，以 **python 类型 Hook** 加载本插件
（`hooks/hooks.json` 配置的 `function` 指向 `voice-reply_hook.py`），
在 DriFox 进程内通过 `win32com` 调用 Windows SAPI5 异步播报（`SVSFlagsAsync`），
**不阻塞聊天流程**。

## 事件

| 事件 | 触发时机 | 行为 |
|------|----------|------|
| `PostAssistantMessage` | AI 回复完成后 | 朗读回复内容 |
