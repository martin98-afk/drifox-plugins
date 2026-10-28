# Voice Input - 输入框语音听写

输入框工具栏麦克风按钮：点击开始录音，再次点击结束并把识别文字插入输入框光标处（不自动发送，可继续编辑）。

**纯云端双引擎**：硅基流动（免费模型，默认优先）+ MiniMax（按量计费）互为备用。自动模式下首选引擎失败（限流/超时/key 无效）自动转备用，单引擎选项失败即报错。识别带标点，秒级返回。

**平台支持**：Windows（winmm）/ macOS（AVFoundation）。Linux 未实现，已用 `platforms` 声明支持范围，不兼容平台的市场卡片会置灰。

## 使用

1. 点输入框工具栏的麦克风按钮 → 屏幕右下角弹出录音浮窗（红点脉冲 + 计时）
2. 对麦克风说话（单次最长 60 秒，超时自动结束）
3. 再次点按钮（或点浮窗主体）→ 结束录音并识别
4. 识别文字插入输入框光标处，InfoBar 提示结果
5. 取消：点浮窗「取消」键，丢弃本次录音

### macOS 首次使用（麦克风授权）

首次点麦克风按钮时，系统会弹出麦克风授权弹窗，点「允许」即可。

- 未授权就点按钮：弹窗出现的同时本次录音已经开始，**这一轮录到的可能是静音**，允许后重新点一次即可。
- 误点了「不允许」：到 系统设置 → 隐私与安全性 → 麦克风 勾选 Drifox，然后重开 DriFox。
- 宿主 DriFox 必须在 Info.plist 声明 `NSMicrophoneUsageDescription`（`build.py` 的 `_mac_info_plist` 已内置）。缺这个键时 macOS 不弹窗、直接拒绝，录音全程数字静音。

## 配置（设置 → 语音听写配置）

| 字段 | 类型 | 说明 |
|------|------|------|
| 识别引擎 | select | `auto`（默认，硅基流动优先，失败转 MiniMax）/ `siliconflow`（仅硅基流动）/ `minimax`（仅 MiniMax） |
| 硅基流动 API Key | password | [硅基流动](https://cloud.siliconflow.cn/account/ak) 获取；免费模型不消耗余额 |
| 硅基流动模型 | select | 免费模型下拉：Qwen3-ASR（默认）/ SenseVoice-Small / 星尘 ASR 系列，均为免费档 |
| MiniMax API Key | password | [MiniMax 开放平台](https://platform.minimaxi.com/user-center/basic-information) 获取；¥2.50/小时 |

> 两把 Key 均支持环境变量覆盖（`SILICONFLOW_API_KEY` / `MINIMAX_API_KEY`，优先级高于设置页）。推荐至少配硅基流动 Key（免费）；两把都配才能互为备用。

### 测试连接

卡底的「测试连接」会真发一次识别请求验证凭据（上传 1 秒音调 WAV，非人声，识别文本为空属正常）：

- 按当前引擎发：`auto` 先试硅基流动，失败再试 MiniMax，任一成功即通过
- 结果就地显示在按钮同行（绿=可用并带耗时，红=失败原因），不弹窗
- 401/403 直接提示「API Key 无效或无权限」，404 提示端点/模型不存在，429 提示限流
- 用的是卡里**当前填写值**，改完不用先失焦或保存

## 引擎对比

| 引擎 | 价格 | 中文效果 | 说明 |
|------|------|---------|------|
| 硅基流动 Qwen3-ASR（默认） | 免费 | 好，带标点 | 免费模型；SenseVoiceSmall 免费通道限流严重，不建议 |
| MiniMax asr-1.0 | ¥2.50/小时 | 好，带标点 | 稳定，适合做备用 |

## 工作原理

```
点按钮 → 平台录音后端录 16kHz/16bit/mono WAV（临时目录）
          ├─ Windows：winmm (mciSendStringW)
          └─ macOS：AVFoundation (AVAudioRecorder，ctypes 直调，绕过 pyobjc 未打包问题)
        → 按配置生成识别链（自动模式：硅基流动 → MiniMax）
        → POST multipart（file + model，Bearer 认证）→ JSON {"text": ...}
        → 头部引擎失败自动转链内下一个；全部失败报错收场
        → 文本回主线程 → input_area 光标处 insertText → 删除临时 WAV
```

录音后端按 `sys.platform` 分派（`_make_recorder`）：winmm 模块顶层绑定
`ctypes.windll`（Windows 专属符号），非 Windows 平台必须绕开其 import。

识别请求在 QThread 内执行（30 秒超时），不卡 UI；上传用标准库 urllib 手写
multipart（宿主未收集 requests，插件零第三方依赖）。按钮位置锚定
`after:quick-screenshot`（未安装该插件时降级到工具栏末尾）。

WAV 头解析与电平统计在 `wav_utils.py`（两端共用）。注意 AVAudioRecorder 会在
`fmt` 前插入 `JUNK`/`FLLR` 填充块（实测 data 偏移到 4096 字节），解析必须读够
8KB 头，否则时长统计失败。
