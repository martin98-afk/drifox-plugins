# Voice Input - 输入框语音听写

输入框工具栏麦克风按钮：点击开始录音，再次点击结束并把识别文字插入输入框光标处（不自动发送，可继续编辑）。

**识别引擎三后端，设置里可选**：MiniMax 云端识别（准确率最高、带标点、秒回，需在 设置 → 语音听写配置 填 API Key）→ 本地 Whisper（faster-whisper，可一键安装）→ Windows 自带离线识别（SAPI5 中文引擎）。自动模式下配了 Key 走云端优先，云端失败自动回退本地链，插件始终可用。

## 使用

1. 点输入框工具栏的麦克风按钮 → 屏幕右下角弹出录音浮窗（红点脉冲 + 计时）
2. 对麦克风说话（单次最长 60 秒，超时自动结束）
3. 再次点按钮（或点浮窗主体）→ 结束录音并识别
4. 识别文字插入输入框光标处，InfoBar 提示结果
5. 取消：点浮窗「取消」键，丢弃本次录音

## 引擎选择与准确率

| 后端 | 中文准确率 | 依赖 | 说明 |
|------|-----------|------|------|
| **MiniMax 云端（推荐）** | 最高，带标点 | 设置里填 API Key | `asr-1.0` 模型，秒级返回；失败自动回退本地链 |
| Whisper | ~90%+，带标点 | faster-whisper + 一次模型下载 | 离线、免费、隐私好；默认 small 档（约 460MB） |
| SAPI5（自动回退） | ~60–75%，无标点 | 零 | Windows 传统离线引擎，仅作兜底 |

## 配置（设置 → 语音听写配置）

| 字段 | 类型 | 说明 |
|------|------|------|
| 识别引擎 | select | `auto`（默认，配了 Key 走云端优先）/ `minimax`（强制云端）/ `sapi5`（强制本地） |
| MiniMax API Key | password | [MiniMax 开放平台](https://platform.minimax.cn/docs/api-reference/speech-to-text) 获取；留空走本地引擎 |

> API Key 存储于插件独立配置（`plugin_data/voice-input/config.json`），也可用环境变量 `MINIMAX_API_KEY` 覆盖（环境变量优先级更高）。选择 MiniMax 时无需本地中文识别引擎。

> 为什么准确率差？旧版全程走 SAPI5 dictation（Windows Vista/7 时代的离线听写引擎），
> 中文同音字错误多、无标点，这是引擎天花板，录音/调用方式无法弥补。

## 安装 faster-whisper（推荐，提升明显）

### 方式一：一键脚本（装进插件自带 deps/，自包含）

用 **DriFox 宿主的同一个 Python 解释器**执行：

```bash
<DriFox-python> plugins/voice-input/tools/install_whisper.py
```

脚本会把 faster-whisper 及编译依赖（ctranslate2 / av / tokenizers 等）装到
`plugins/voice-input/deps/`，并按宿主解释器自动挑选匹配的编译轮子（cp314/abi3 均可），
装完自动验证 import。卸载：删除 `deps/` 目录即可（插件自动回退 SAPI5）。

### 方式二：直接装进宿主环境

```bash
<DriFox-python> -m pip install faster-whisper
```

## 首次使用：自动下载模型

Whisper 首次识别会自动从 HuggingFace 下载中文模型（默认 **small** ≈460MB，仅一次，
缓存于 `~/.cache/drifox-voice-input/`），浮窗会显示「下载模型…」进度文案，完成后自动识别。

配置（环境变量）：

| 变量 | 作用 | 取值 |
|------|------|------|
| `DRIFOX_VOICE_MODEL` | 模型档位 | `tiny`(≈75MB) / `base`(≈145MB) / `small`(460MB, 默认) / `medium`(≈1.5GB) |
| `DRIFOX_VOICE_WHISPER_DIR` | 模型缓存目录 | 任意绝对路径 |

- 想最省流量先试效果：`DRIFOX_VOICE_MODEL=tiny`
- 追求更高准确率且机器性能够：`DRIFOX_VOICE_MODEL=medium`
- 国内网络下载模型失败时：设 `HF_ENDPOINT=https://hf-mirror.com`（HuggingFace 镜像）

## SAPI5 引擎要求（仅回退路径需要）

Windows 系统需带中文语音识别引擎（zh-CN）。验证：

```powershell
$r = New-Object -ComObject "SAPI.SpInprocRecognizer"
$cat = New-Object -ComObject "SAPI.SpObjectToken"
$cat.SetId("HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Recognizers", $false)
$cat.EnumerateTokens() | ForEach-Object { "$($_.GetAttribute('Language')) :: $($_.GetDescription())" }
```

列表中有 `804` 开头条目（如 Microsoft Speech Recognizer 8.0 for Windows (Chinese Simplified - PRC)）即可用。中文系统一般自带；缺失时插件会在点击时明确报错。

## 已知上限

- 仅支持普通话（zh-CN）；英文等语言识别在计划中
- Whisper 为 CPU int8 离线推理：small 档录音后约 1–3 秒出结果，medium 更慢
- 录音为按需瞬时采集，仅在录音期间读取麦克风，结束即释放

## 工作原理

```
点按钮 → winmm 录 16kHz/16bit/mono WAV（%TEMP%）
        → 引擎选择（设置里配置，默认 auto）：
           ① 配了 MiniMax Key → POST speech_to_text（multipart, asr-1.0）
              失败（网络/HTTP/key 无效）→ 回退 ②
           ② faster-whisper 可用 → Whisper CPU(int8) + VAD + 固定 zh
              不可用 → SAPI5 SpInprocRecognizer + dictation
        → 文本回主线程 → input_area 光标处 insertText → 删除临时 WAV
```

引擎探测只做轻量 `find_spec`（不卡 UI）；真正的网络请求 / import / 模型下载 / 识别都在
QThread 内完成，任一环节失败自动回退下一引擎。云端上传用标准库 urllib 手写 multipart
（宿主未收集 requests，插件零第三方依赖）。按钮位置锚定
`after:quick-screenshot`（未安装该插件时降级到工具栏末尾）。
