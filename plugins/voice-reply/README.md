# Voice Reply - 消息卡片语音朗读

消息卡片页脚「朗读」按钮：点击播报本条 AI 回复，按钮变 pause 图标；播放中再次点击即停止；播报自然结束后按钮自动复位为扬声器。双引擎设计，**零第三方依赖**。

> 按钮图标切换说明：宿主 `MessageCard` 构建页脚按钮时不向插件暴露按钮实例（`message_card.py` 用注册快照构造），
> 插件按 tooltip 锚点在卡片子树里定位自己的按钮后 `setIcon` 换图。播报结束检测：
> Windows 轮询 SAPI5 `Status.RunningState`（300ms），macOS 接 `QProcess.finished`。

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

设置 → 语音播报配置（自绘设置卡，即改即生效）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 语音引擎 | 本地系统语音 | `local` / `api`；选本地时在线相关行整体置灰 |
| 服务商 | 硅基流动 | 界面辅助行（不落盘）：选中即预填 API 地址，并联动行尾「获取 Key」链接 |
| API 地址 | 硅基流动端点 | 真实 URL 输入框，可手改；改成已知平台域名时服务商自动跟随，认不出则显示「自定义」并收起 Key 链接 |
| 模型 | `FunAudioLLM/CosyVoice2-0.5B` | 可编辑下拉：CosyVoice2-0.5B / Fish-Speech 1.5 / MOSS-TTSD-v0.5 / 手填 |
| 音色 | `FunAudioLLM/CosyVoice2-0.5B:alex` | 可编辑下拉，随模型换批；CosyVoice2 与 Fish-Speech 1.5 共用 8 个预置音色 |
| API Key | 空 | 环境变量 `TTS_API_KEY` 可覆盖；行尾「获取 Key」直达对应平台密钥页 |

卡底「测试连接」用当前填写值真发一次合成请求（合成两个字，不播放）：成功显示「可用 · 耗时 · 音频大小」，失败显示人话原因（401/403 = Key 无效，404 = 端点或模型不存在，429 = 限流）。

预置服务商与其 API Key 管理页（2026-10 逐个验证可访问）：

| 服务商 | 端点 | Key 页 |
|--------|------|--------|
| 硅基流动 | `api.siliconflow.cn` | https://cloud.siliconflow.cn/account/ak |
| OpenAI | `api.openai.com` | https://platform.openai.com/api-keys |
| 智谱 BigModel | `open.bigmodel.cn` | https://bigmodel.cn/usercenter/proj-mgmt/apikeys |
| MiniMax | `api.minimaxi.com` | https://platform.minimaxi.com/user-center/basic-information/interface-key |
| 月之暗面 Kimi | `api.moonshot.cn` | https://platform.moonshot.cn/console/api-keys |

「模型」「音色」为可编辑下拉（qfluentwidgets `EditableComboBox`）：
既可从预置项里选，也能直接键入任意值（回车后该值进入下拉列表）。
切换模型时音色下拉整体换批，且 `音色` 存储值的模型前缀同步跟随，避免用旧模型的音色名请求新模型报错。
「API 地址」是普通输入框（显示真实 URL 而非平台名），平台选择交给「服务商」下拉。

> 为什么自绘设置卡：主程序 E1 自动卡（plugin.json config_schema）只把字段渲染成
> 不可编辑 ComboBox 或纯 LineEdit，无法「下拉选 + 手填」二合一。插件用更高 priority
> 注册自绘卡覆盖自动卡；注册失败时自动降级回 config_schema 自动卡，朗读功能不受影响。

在线合成固定请求 wav 格式：Windows 走 winmm `mciSendStringW`、macOS 走 `afplay` 播放，音频文件落在系统临时目录、播完即删。日志会打印 wav 摘要（采样率/声道/位深/时长），便于排查「提示播放中但听不到」。

> 为什么不用 `winsound.PlaySound`：它播放失败时**不抛异常、静默无声**，且对 WAV 兼容面窄，
> 表现为「提示播放中但听不到」且日志干净、无从诊断。改用 winmm mci：命令返回码非 0 即失败，
> 可 `mciGetErrorStringW` 转人话，且支持显式 stop/close。

### 停止播放：为什么用「异步 play + 轮询 mode」

2026-10-18 修复「点击停止，语音继续播完」：原实现用 `play <alias> wait` 阻塞播放，
主线程发 `stop <alias>` 打断。实测发现 mci alias **绑定到发起 open 的那个线程**，
跨线程发 stop 一律返回 263「指定的设备未打开」，音频照常播完。

改为异步 `play` + 播放线程轮询 `status <alias> mode`，主线程 stop() 只置
`threading.Event`，真正的 stop/close 由播放线程自己发（同线程才有效）。
打断延迟 = 轮询节拍 150ms。

### 预置音色（8 个）

硅基流动 CosyVoice2-0.5B 与 Fish-Speech 1.5 **音色名完全一致**，voice 值统一为
`<模型名>:<音色名>`：

| 短名 | 描述 | 短名 | 描述 |
|------|------|------|------|
| `alex` | 沉稳男声 | `anna` | 沉稳女声 |
| `benjamin` | 低沉男声 | `bella` | 激情女声 |
| `charles` | 磁性男声 | `claire` | 温柔女声 |
| `david` | 欢快男声 | `diana` | 欢快女声 |

`fnlp/MOSS-TTSD-v0.5` 是对话合成模型（input 需 `[S1]`/`[S2]` 标记、voice 走参考音频
uri），单段播报用不上，故不提供音色包，仅允许手填。

### 无声排查

```bash
uv run python tools/diag_voice_reply.py
```

脚本会读实际配置 → 打一次 API → 打印 HTTP 状态 / 返回字节数 / wav 摘要 →
分别用 winsound、winmm mci、系统默认播放器播放同一文件并打印结果，据此可判定
是「音频数据有问题」还是「播放后端有问题」。

## 工作原理

插件以 UI 组件形态注册消息卡片页脚动作（`register_footer_action`，与内置复制/分支按钮同排）：

1. 点击按钮 → 从消息卡片提取**正文** → 清洗 → 截断至 2000 字 → 按钮切 pause；
2. 本地引擎：主线程直接播报（SAPI5 异步 300ms 轮询 RunningState 判结束，`say` 用 QProcess.finished），播放中再点 = `Skip` 打断；
3. 在线引擎：QThread worker 合成（urllib，50 秒超时）→ wav 落临时文件 → 播放；播放中再点 = 终止播放并复位；
4. 播完 / 打断 / 失败三条路径均复位按钮为扬声器图标。

音频播放由 `ui/audio_player.py` 承担（Windows winmm mci / macOS afplay，纯 ctypes）。

## 朗读范围：只读正文

`ui/tts_text.py` 决定「哪些内容会变成声音」，纯函数实现、可离线单测（`tests/test_voice_reply_tts_text.py` 19 例）。

**取正文**：按消息内容块类型过滤，只保留 `type == "text"` 块。思考过程（`reasoning`）、工具调用与结果（`tool_result`）、自定义渲染块（`custom`）、图片块一律不进朗读。拿不到块列表时退回 `get_plain_text()`，此时文本已混入工具结果，再用正则补刀（内联 `<think>…</think>` 整段删、`[tool:xxx]` 开头的行整行删）。

**清洗**：朗读器会把符号读成人话、把机器串读成乱码，因此统一剔除：

| 类别 | 处理 |
|------|------|
| 代码块 | 整体替换为「代码略」提示音 |
| markdown 标记 | 行内代码去反引号；图片留 alt、链接留文字；粗体/斜体/删除线/标题/列表/引用/分隔线/表格竖线去标记 |
| 链接 | 裸 URL、data URI 删除（保留句末标点） |
| 机器串 | 超长 base64/哈希/路径、HTML 标签删除 |
| emoji 与装饰符号 | 删除（多数 TTS 会读成「笑脸」「右箭头」） |
| 控制字符 | 删除；连续标点折叠为单个停顿 |

**上限**：2000 字，超出截断并补「……」。原 500 字常把长回复切断在句中。

## 依赖

无需安装任何依赖。本地引擎用系统自带能力，在线引擎用标准库 `urllib` + 系统 winmm/`afplay`。

> Windows 本地语音要求系统已安装中文语音包（一般 Windows 10/11 自带），验证：
>
> ```powershell
> powershell -NoProfile -Command "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Speech'); $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
> ```
