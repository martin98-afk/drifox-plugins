# minimax-h3 官方插件设计

- 日期：2026-08-11
- 状态：已批准
- 仓库：drifox-plugins2（DriFox 官方插件市场）

## 1. 目标

新建官方插件 `plugins/minimax-h3`，把 MiniMax-H3（开源全模态音视频生成系统）集成进 DriFox 插件生态。用户可通过 `/minimax-h3` 命令生成带原生立体声音频的视频（文生视频 / 首帧 / 尾帧 / 首尾帧 / 多模态参考生视频），并配有 H3 提示词编写技能，保证生成质量。

## 2. 范围

- **新增** `plugins/minimax-h3/` 目录（commands + skills 两类组件）
- **不动** 其他现有插件、CI 配置、LICENSE、CODE_OF_CONDUCT

### 能力清单

| 能力 | 载体 | 说明 |
|------|------|------|
| H3 提示词编写技能 | `skills/h3-prompt-writing/` | 上游 MiniMax-AI/MiniMax-H3 原文搬运（SKILL.md + references/base-en.txt + references/ref-en.txt），不改内容 |
| 视频生成命令 | `commands/minimax-h3.md` | `/minimax-h3` 引导 Agent 走「技能写提示词 → 脚本提交 → 轮询 → 下载」全流程 |
| API 封装脚本 | `scripts/h3_video.py` | create / query / download 三个子命令 |

### 明确不做（YAGNI）

- 不做本地部署（SGLang / diffusers / ComfyUI）支持
- 不做 2K 工作流的 H3-Context-IR / H3-Regenerate-2K 单独 API 封装（`/v2/video_generation` 传 `resolution=2K` 即可直接出 2K，无需多阶段）
- 不做 UI 组件 / hooks / agents / themes / mcp / lsp
- 不搬运 MiniMax Hub 画布专用的 8 个风格化视频技能（不可移植到通用 agent）

## 3. 目录结构

```
plugins/minimax-h3/
├── .drifox-plugin/
│   └── plugin.json          # name=minimax-h3, components: commands+skills
├── icon.png                 # MiniMax logo（浅色）
├── icon_dark.png            # MiniMax logo（深色）
├── LICENSE                  # MiniMax H3 Community License 声明 + MIT 结构
├── README.md                # 插件说明：能力、用法、API Key、合规
├── commands/
│   └── minimax-h3.md        # /minimax-h3 命令
├── scripts/
│   └── h3_video.py          # create / query / download
└── skills/
    └── h3-prompt-writing/
        ├── SKILL.md         # 上游原文
        └── references/
            ├── base-en.txt  # T2VA/I2VA/FL2VA/L2VA 指南
            └── ref-en.txt   # Ref2VA 指南
```

## 4. API 对接

### 端点（国内 / 海外可切）

| 用途 | 端点 |
|------|------|
| 创建任务 | `POST https://api.minimaxi.com/v2/video_generation`（海外 `api.minimax.io`） |
| 查询任务 | `GET https://api.minimaxi.com/v2/query/video_generation/{task_id}` |

### 创建任务请求体

```json
{
  "model": "MiniMax-H3",
  "content": [
    { "type": "text", "text": "<提示词>" },
    { "type": "image_url", "image_url": { "url": "<首帧图>" }, "role": "first_frame" },
    { "type": "image_url", "image_url": { "url": "<尾帧图>" }, "role": "last_frame" }
  ],
  "resolution": "768P",
  "duration": 8,
  "ratio": "16:9"
}
```

### 输入模式（content 组合）

| 模式 | content | ratio 规则 |
|------|---------|-----------|
| t2va 文生视频 | 仅 text | 必填，不可 adaptive |
| i2va 首帧 | text + 1 图（role=first_frame 或不填） | 恒 adaptive |
| 尾帧 | text + 1 图（role=last_frame） | 恒 adaptive |
| 首尾帧 | text + 2 图（first_frame + last_frame） | 恒 adaptive |
| ref2va 多模态参考 | text + 参考图(≤9)/参考视频(≤3)/参考音频(≤3) | 可选，默认 adaptive |

### 约束（脚本需校验）

- 请求体总大小 ≤ 64MB（大文件用公网 URL，勿用 Base64）
- 图片：JPG/PNG/WEBP/HEIC/HEIF，≤30MB，宽 [256,5760]，长宽比 [0.4,2.5]
- 视频：MP4/MOV，≤50MB，≤3 个，单段 [2,15]s 总 ≤15s
- 音频：WAV/MP3，≤15MB，≤3 个，单段 [2,15]s 总 ≤15s
- duration：整数 4~15
- 图生视频与多模态参考**互斥**（不能同时出现 first_frame/last_frame 与 reference_*）

### 查询任务响应

- status: `queued` / `running` / `succeeded` / `failed` / `cancelled`
- succeeded 时 `task.content.url` 为视频直链，`task.ratio` 为实际比例

## 5. 脚本设计（scripts/h3_video.py）

仿 voice-clone 的 `voice_clone.py` 风格，标准库 + requests。

### 子命令

```
python h3_video.py create \
  --prompt "<提示词>" \
  [--first-frame <图URL或本地路径>] \
  [--last-frame <图URL或本地路径>] \
  [--ref-image <URL>]... [--ref-video <URL>]... [--ref-audio <URL>]... \
  [--resolution 768P|2K] [--duration 4-15] [--ratio 16:9] \
  [--api-base https://api.minimaxi.com] [--api-key xxx] \
  [--wait] [--timeout 600] [--output out.mp4]

python h3_video.py query <task_id> [--api-base ...] [--api-key ...]

python h3_video.py download <task_id> --output out.mp4 [--api-base ...] [--api-key ...]
```

### 关键行为

- `get_api_key()`：复用 voice-clone 读取链（`MINIMAX_API_KEY` 环境变量 → `~/.minimax/api_key` → `--api-key`），绝不硬编码
- 本地图片/视频/音频文件自动 Base64 编码为 Data URL（≤64MB 总限），URL 直传不处理
- `create`：自动推导输入模式（无图=t2va，1 图=首帧/尾帧按 role，2 图=首尾帧，有 reference_*=ref2va）
- 输入互斥校验：first/last-frame 与 reference_* 同传报错
- `query`：打印状态 + 视频 URL + 分辨率/时长/比例
- `download`：查询到 succeeded 后拉取视频到本地文件
- `--wait`：create 后阻塞轮询（间隔 5s，默认超时 600s），succeeded 即下载（配合 --output），failed 打印错误
- 错误处理：HTTP 非 2xx 与任务 failed 都给出可读信息，非 0 退出

## 6. 命令设计（commands/minimax-h3.md）

`/minimax-h3` 命令（type: prompt），内容要点：

1. **确认输入模式**：根据用户给的素材（纯文本 / 图片 / 视频 / 音频）判断 t2va / i2va / fl2va / ref2va
2. **写提示词**：加载 `h3-prompt-writing` 技能，按 base-en.txt 或 ref-en.txt 的结构重写用户需求为 H3 提示词
3. **提交任务**：运行 `python plugins/minimax-h3/scripts/h3_video.py create ... --wait --output out.mp4`
4. **告知结果**：输出文件路径、时长、分辨率、实际比例

## 7. 技能搬运（skills/h3-prompt-writing/）

- 完整搬运上游 `SKILL.md` + `references/base-en.txt` + `references/ref-en.txt`，**内容原样**，不改写
- 不搬运 `agents/openai.yaml`（仅 ChatGPT/Codex UI 元数据，DriFox 不需要）
- 保留 frontmatter（name/description/compatibility）

## 8. 图标

用户提供 MiniMax 官方 logo 图（`https://avatars.githubusercontent.com/u/194880281`，粉红渐变 + 白色 MINIMAX 字样 + 波形）。以此为基础生成 `icon.png` / `icon_dark.png`：
- light：粉红渐变底 + 白 logo（原图直接缩放）
- dark：深色底 + 粉红 logo（或同款反色处理）

> 已确认 DriFox 图标加载：`QIcon(str(icon_path))`，PNG 原生支持；manifest `icon` 字段接受任意路径字符串，不限于 SVG。上游图是位图 PNG，直接使用 PNG 而非转 SVG。

## 9. plugin.json

```json
{
  "name": "minimax-h3",
  "description": "MiniMax H3 全模态视频生成 — 文本/图片/视频/音频转带立体声音频的视频（768P/2K，4-15s），含 H3 提示词编写技能。",
  "icon": { "light": "icon.png", "dark": "icon_dark.png" },
  "version": "1.0.0",
  "type": "user",
  "license": "MIT",
  "author": { "name": "DriFox Contributors" },
  "homepage": "https://github.com/martin98-afk/drifox-plugins",
  "keywords": ["minimax", "h3", "video", "video-generation", "t2v", "i2v", "t2va", "i2va", "fl2va", "ref2va", "ai-video", "视频生成", "文生视频", "图生视频", "多模态"],
  "components": { "commands": true, "skills": true },
  "drifox": { "min_version": "0.5.0" }
}
```

### 许可证说明

- `plugin.json` 的 `license` 字段沿用仓库惯例（voice-clone 用 MIT）
- `LICENSE` 文件：MIT 结构 + 注明 H3 技能内容与提示词指南源自 [MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3)，遵循 MiniMax H3 Community License；模型权重与 API 使用受 MiniMax 平台条款约束
- README 中显著标注来源与合规提示

## 10. 文档同步（强制规则）

- `plugins/README.md`：索引表新增 minimax-h3 行（语音与多媒体分类下）
- 仓库根 `README.md`：官方插件表中新增 minimax-h3 行
- `CHANGELOG.md`：追加条目

## 11. 验证

1. `python tools/validate_plugins.py` 通过（manifest schema / 组件资源存在 / marketplace 一致性）
2. `python tools/generate_marketplace.py` 生成 marketplace.json（CI 也会自动做）
3. `python -m py_compile plugins/minimax-h3/scripts/h3_video.py` 语法通过
4. 脚本 dry-run：`python h3_video.py --help` 各子命令可用
5. 无真实 API Key 时脚本给出清晰报错（不崩溃）

## 12. 风险与对策

| 风险 | 对策 |
|------|------|
| 无 API Key 环境时 Agent 调用失败 | 脚本清晰提示配置方法（同 voice-clone），命令 md 写明前置条件 |
| 视频生成耗时长（分钟级） | create 默认不 --wait，提示用户可后台轮询 query |
| 请求体超 64MB | 提示用公网 URL 而非本地大文件 |
| 图生视频与参考模式互斥误用 | 脚本强校验，报错说明 |
| MiniMax 海外/国内端点差异 | `--api-base` 可配，默认国内 minimaxi.com |
