# Voice Input - 输入框语音听写

输入框工具栏麦克风按钮：点击开始录音，再次点击结束并把识别文字插入输入框光标处（不自动发送，可继续编辑）。

**纯云端双引擎**：硅基流动（免费模型，默认优先）+ MiniMax（按量计费）互为备用。自动模式下首选引擎失败（限流/超时/key 无效）自动转备用，单引擎选项失败即报错。识别带标点，秒级返回。

## 使用

1. 点输入框工具栏的麦克风按钮 → 屏幕右下角弹出录音浮窗（红点脉冲 + 计时）
2. 对麦克风说话（单次最长 60 秒，超时自动结束）
3. 再次点按钮（或点浮窗主体）→ 结束录音并识别
4. 识别文字插入输入框光标处，InfoBar 提示结果
5. 取消：点浮窗「取消」键，丢弃本次录音

## 配置（设置 → 语音听写配置）

| 字段 | 类型 | 说明 |
|------|------|------|
| 识别引擎 | select | `auto`（默认，硅基流动优先，失败转 MiniMax）/ `siliconflow`（仅硅基流动）/ `minimax`（仅 MiniMax） |
| 硅基流动 API Key | password | [硅基流动](https://cloud.siliconflow.cn/account/ak) 获取；免费模型不消耗余额 |
| 硅基流动模型 | select | 免费模型下拉：Qwen3-ASR（默认）/ SenseVoice-Small / 星尘 ASR 系列，均为免费档 |
| MiniMax API Key | password | [MiniMax 开放平台](https://platform.minimaxi.com/user-center/basic-information) 获取；¥2.50/小时 |

> 两把 Key 均支持环境变量覆盖（`SILICONFLOW_API_KEY` / `MINIMAX_API_KEY`，优先级高于设置页）。推荐至少配硅基流动 Key（免费）；两把都配才能互为备用。

## 引擎对比

| 引擎 | 价格 | 中文效果 | 说明 |
|------|------|---------|------|
| 硅基流动 Qwen3-ASR（默认） | 免费 | 好，带标点 | 免费模型；SenseVoiceSmall 免费通道限流严重，不建议 |
| MiniMax asr-1.0 | ¥2.50/小时 | 好，带标点 | 稳定，适合做备用 |

## 工作原理

```
点按钮 → winmm 录 16kHz/16bit/mono WAV（%TEMP%）
        → 按配置生成识别链（自动模式：硅基流动 → MiniMax）
        → POST multipart（file + model，Bearer 认证）→ JSON {"text": ...}
        → 头部引擎失败自动转链内下一个；全部失败报错收场
        → 文本回主线程 → input_area 光标处 insertText → 删除临时 WAV
```

识别请求在 QThread 内执行（30 秒超时），不卡 UI；上传用标准库 urllib 手写
multipart（宿主未收集 requests，插件零第三方依赖）。按钮位置锚定
`after:quick-screenshot`（未安装该插件时降级到工具栏末尾）。
