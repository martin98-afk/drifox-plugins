---
description: 文本生成视频（40+ AI 视频模型统一封装）
type: prompt
parameters:
  - name: "<prompt>"
    description: "视频文字描述（必填）"
    param_type: positional
  - name: "--model="
    description: "模型：veo-3 / sora-2 / wan-2.5 / kling-2.0 / 可灵-1.6 / 即梦-3.0 / runway-gen-4 / pika-2.0 / grok-video / haituo-02 / 默认 auto"
    param_type: value
  - name: "--duration="
    description: "时长：5s/6s/8s/10s/12s/20s"
    param_type: value
  - name: "--resolution="
    description: "分辨率：720p / 1080p / 4k"
    param_type: value
  - name: "--aspect="
    description: "宽高比：16:9 / 9:16 / 1:1 / 4:3 / 21:9"
    param_type: value
  - name: "--output="
    description: "输出文件名（默认 .mp4）"
    param_type: value
allowed-tools:
  - read
  - bash
  - grep
hidden: false
---

# /video-generate 命令 — 文本生成视频

你正在处理 `/video-generate` 命令。本命令通过 AI 模型从文本生成视频。

## 📋 执行规则

1. **解析参数**：
   - `<prompt>`：视频描述，必填
   - `--model=`：模型，默认 `auto`（按需选择）
   - `--duration=`：时长，默认 8s
   - `--resolution=`：分辨率，默认 1080p
   - `--aspect=`：宽高比，默认 16:9
   - `--output=`：输出文件名

2. **模型选择**（auto 模式）：

   | Prompt 关键词 | 推荐模型 |
   |--------------|---------|
   | cinematic / film / 真实 / 物理 | veo-3, sora-2 |
   | anime / 动漫 / 二次元 | pika-2.0, kling-2.0 |
   | 中文 / 国产 | wan-2.5, 可灵-1.6, 即梦-3.0 |
   | long / 长 / 20s | sora-2, veo-2 |
   | cheap / 性价比 | haituo-02, 即梦-3.0 |
   | character / 角色 / 一致 | higgsfield, kling-2.0 |
   | creative / 风格化 | grok-video, pixverse |

3. **调用模型**：

   ```bash
   # 示例：veo-3
   curl -X POST "https://generativelanguage.googleapis.com/v1beta/models/veo-3:generateVideo" \
     -H "Authorization: Bearer $GOOGLE_API_KEY" \
     -d '{
       "prompt": "<prompt>",
       "duration_seconds": "8",
       "aspect_ratio": "16:9",
       "resolution": "1080p"
     }'
   ```

4. **输出**：

   ```
   ✅ 视频生成完成
   模型：veo-3
   时长：8s
   分辨率：1080p
   宽高比：16:9
   输出：./videos/cat-beach.mp4
   ```

## 子行为

<!-- section:model -->
### `--model=<name>` 显式指定模型

| 模型 | 强项 | 弱项 |
|------|------|------|
| veo-3 | 物理级真实 | 价格高 |
| sora-2 | 长时长、一致性 | 等待长 |
| wan-2.5 | 中文、性价比 | 创意一般 |
| kling-2.0 | 角色动画 | 物理一般 |
| runway-gen-4 | 影视级 | 价格高 |
| pika-2.0 | 动漫风格 | 真实感弱 |
| grok-video | 创意风格 | 长时长不可 |
| haituo-02 | 性价比 | 复杂动作一般 |
<!-- end -->

<!-- section:duration -->
### `--duration=<n>s` 时长

| 模型 | 支持时长 |
|------|---------|
| veo-3 | 5s / 8s |
| sora-2 | 5s / 10s / 15s / 20s |
| wan-2.5 | 5s / 10s |
| kling-2.0 | 5s / 10s |
| haituo-02 | 6s / 12s |
<!-- end -->

<!-- section:resolution -->
### `--resolution=<p>` 分辨率

| 模型 | 720p | 1080p | 4K |
|------|------|-------|-----|
| veo-3 | ✓ | ✓ | ✗ |
| sora-2 | ✓ | ✓ | ✗ |
| wan-2.5 | ✓ | ✓ | ✗ |
| runway-gen-4 | ✓ | ✓ | ✓ |
| 即梦-3.0 | ✓ | ✓ | ✗ |
<!-- end -->

<!-- section:aspect -->
### `--aspect=<ratio>` 宽高比

| 比例 | 适用 |
|------|------|
| 16:9 | YouTube / 桌面 |
| 9:16 | TikTok / 抖音 |
| 1:1 | Instagram |
| 4:3 | 传统电视 |
| 21:9 | 电影 |
<!-- end -->

## 模板变量

- `$ARGUMENTS`：用户输入的完整参数
- `$PLUGIN_NAME`：当前插件名（ai-video-gen）
- `$PROJECT_ROOT`：当前工作项目根目录

## 提示

- 配合 `/video-from-image` 提供图片引导
- 配合 `ai-image-gen` 先生成关键帧
- 八字 prompt 公式：[主体] [动作] [环境] [镜头] [风格]
- 避免抽象 prompt 与多主体混淆
