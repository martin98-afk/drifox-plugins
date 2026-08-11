# minimax-h3 插件

MiniMax H3 全模态音视频生成官方插件。通过 MiniMax 开放平台 API 生成带原生立体声音频的视频。

## 能力

- **视频生成**：`/minimax-h3` 命令，支持
  - **t2va 文生视频** — 仅文本描述生成视频
  - **i2va / fl2va 图生视频** — 首帧 / 尾帧 / 首尾帧生视频
  - **ref2va 多模态参考生视频** — 参考图片（≤9）/ 参考视频（≤3）/ 参考音频（≤3）组合
  - 分辨率 768P / 2K，时长 4-15 秒，输出 24FPS + 32kHz 立体声
- **提示词技能**：`h3-prompt-writing` — H3 提示词编写指南（base-en.txt 用于文本/关键帧模式，ref-en.txt 用于全参考模式），保证生成质量

## 快速开始

### 1. 配置 API Key

```bash
# 方式一：环境变量
set MINIMAX_API_KEY=your_key_here

# 方式二：配置文件
echo your_key > %USERPROFILE%\.minimax\api_key
```

API Key 在 [MiniMax 开放平台](https://platform.minimaxi.com) 获取。

### 2. 生成视频

```bash
# 文生视频（需指定宽高比）
python scripts/h3_video.py create \
  --prompt "一只橘猫在沙滩上追逐浪花，黄昏光线，电影感" \
  --resolution 768P --duration 8 --ratio 16:9 \
  --wait --output out.mp4

# 首帧图生视频
python scripts/h3_video.py create \
  --prompt "画面中的女孩转头微笑，镜头缓缓拉远" \
  --first-frame first.png --duration 8 --wait --output out.mp4

# 多模态参考（图+视频+音频）
python scripts/h3_video.py create \
  --prompt "参考视频中的人物在沙漠场景中行走" \
  --ref-image ref.jpg --ref-video ref.mp4 --ref-audio ref.mp3 \
  --resolution 2K --duration 8 --wait --output out.mp4
```

### 3. 查询 / 下载任务

```bash
python scripts/h3_video.py query <task_id>
python scripts/h3_video.py download <task_id> --output out.mp4
```

## 脚本用法

```
python scripts/h3_video.py create --prompt "<提示词>" [--first-frame f.png] [--last-frame l.png]
    [--ref-image a.jpg]... [--ref-video b.mp4]... [--ref-audio c.mp3]...
    [--resolution 768P|2K] [--duration 4-15] [--ratio 21:9|16:9|4:3|1:1|3:4|9:16]
    [--api-base https://api.minimaxi.com] [--wait] [--timeout 600] [--output out.mp4]
python scripts/h3_video.py query <task_id>
python scripts/h3_video.py download <task_id> --output out.mp4
```

## 限制

- 请求体总大小 ≤ 64MB（本地文件自动 Base64，大文件请用公网 URL）
- 图片：JPG/PNG/WEBP/HEIC/HEIF，≤30MB
- 参考视频：MP4/MOV，≤50MB，单段 2-15 秒，总时长 ≤15 秒
- 参考音频：WAV/MP3，≤15MB，单段 2-15 秒，总时长 ≤15 秒
- 图生视频（首/尾帧）与多模态参考互斥，不能混用
- 时长整数 4-15 秒

## 来源与合规

- `skills/h3-prompt-writing/` 内容搬运自 [MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3)（MiniMax H3 Community License），原样保留不改写
- 生成内容受 MiniMax 平台审核约束（禁止违法、色情、侵权内容）
- 详细声明见 [LICENSE](LICENSE)
