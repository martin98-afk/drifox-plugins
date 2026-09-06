# Voice Input - 输入框语音听写

输入框工具栏麦克风按钮：点击开始录音，再次点击结束并把识别文字插入输入框光标处（不自动发送，可继续编辑）。使用 Windows 自带离线语音识别（SAPI5 中文引擎），**零第三方依赖**。

## 使用

1. 点输入框工具栏的麦克风按钮 → 屏幕右下角弹出录音浮窗（红点脉冲 + 计时）
2. 对麦克风说话（单次最长 60 秒，超时自动结束）
3. 再次点按钮（或点浮窗主体）→ 结束录音并识别
4. 识别文字插入输入框光标处，InfoBar 提示结果
5. 取消：点浮窗「取消」键，丢弃本次录音

## 依赖

**无需安装任何依赖。** 录音走 winmm（`mciSendStringW`，ctypes 标准库调用），识别走 SAPI5（`win32com`，随 DriFox 运行环境自带）。

### 引擎要求

Windows 系统需带中文语音识别引擎（zh-CN）。验证：

```powershell
$r = New-Object -ComObject "SAPI.SpInprocRecognizer"
$cat = New-Object -ComObject "SAPI.SpObjectToken"
$cat.SetId("HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Recognizers", $false)
$cat.EnumerateTokens() | ForEach-Object { "$($_.GetAttribute('Language')) :: $($_.GetDescription())" }
```

列表中有 `804` 开头条目（如 Microsoft Speech Recognizer 8.0 for Windows (Chinese Simplified - PRC)）即可用。中文系统一般自带；缺失时插件会在点击时明确报错。

## 已知上限

- SAPI5 引擎为 Windows 传统识别引擎，中文听写同音字错误多于现代 ASR（如 faster-whisper）；本插件先验证链路，后续可扩展本地 whisper 引擎
- 仅支持普通话（zh-CN），英文等语言引擎检测与切换在计划中
- 录音为按需瞬时采集，仅在录音期间读取麦克风，结束即释放

## 工作原理

```
点按钮 → winmm 录 16kHz 单声道 WAV（%TEMP%）→ SAPI5 SpInprocRecognizer
+ zh-CN token + dictation 语法识别（QThread，CoInitialize）→ 文本回主线程
→ input_area 光标处 insertText → 删除临时 WAV
```

按钮位置锚定 `after:quick-screenshot`（未安装该插件时降级到工具栏末尾）。
