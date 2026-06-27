# Voice Reply - AI 回复语音播报

将 AI 回复文字转为语音播放，使用 Windows 离线 TTS（SAPI5），无需网络。

## 依赖安装

本插件依赖 `pyttsx3` 库进行语音合成，需在当前系统 Python 环境中安装：

```bash
pip install pyttsx3
```

> ⚠️ **注意**：本插件以 `command` 类型运行（调用系统 `python`），而非 DriFox 内置 Python。
> 请确保 `python` 命令可用且已安装上述依赖。

### 验证安装

```bash
python -c "import pyttsx3; print('✅ pyttsx3 可用')"
```

如果看到 ✅ 提示，说明安装成功。

## 配置

本插件默认监听 `PostAssistantMessage` 事件，在每次 AI 回复后自动朗读。

如需调整语音或语速，编辑 `hooks/voice_reply.py` 中的：

| 配置项 | 代码位置 | 说明 |
|--------|----------|------|
| 语音索引 | `voices[0]` → 切换索引选择不同语音 | 0=中文, 1/2=英文 |
| 语速 | `engine.setProperty("rate", 180)` | 数值越大越快 |
| 最大字符 | `if len(text) > 1000` → 截断阈值 | 避免朗读过长文本 |

## 工作原理

DriFox 在 `PostAssistantMessage` 事件触发时，通过 command 类型 Hook 执行：

```
python "{plugin_root}/hooks/voice_reply.py" --event=PostAssistantMessage
```

其中 `{plugin_root}` 是 DriFox 内置变量，自动替换为插件根目录路径。上下文通过 stdin (JSON) 传递给脚本，脚本使用 `pyttsx3` 朗读 AI 回复文本。

## 事件

| 事件 | 触发时机 | 行为 |
|------|----------|------|
| `PostAssistantMessage` | AI 回复完成后 | 朗读回复内容 |
