---
description: 文本生成图片（主流 AI 图片模型统一封装）
type: prompt
parameters:
  - name: "<prompt>"
    description: "图片描述（必填）"
    param_type: positional
  - name: "--model="
    description: "模型：imagen-4 / nano-banana-2 / dall-e-3 / midjourney-v7 / flux-pro / sd-3.5 / recraft-v3 / ideogram-2.0 / 默认 auto"
    param_type: value
  - name: "--aspect="
    description: "宽高比：1:1 / 16:9 / 9:16 / 4:3 / 3:4 / 21:9"
    param_type: value
  - name: "--resolution="
    description: "分辨率：512 / 1024 / 2k / 4k"
    param_type: value
  - name: "--count="
    description: "生成数量（1-4）"
    param_type: value
  - name: "--negative="
    description: "负面提示词（避免的元素）"
    param_type: value
  - name: "--output="
    description: "输出目录"
    param_type: value
allowed-tools:
  - read
  - bash
  - grep
hidden: false
---

# /image-generate 命令 — 文本生成图片

你正在处理 `/image-generate` 命令。本命令通过 AI 模型从文本生成图片。

## 📋 执行规则

1. **解析参数**：
   - `<prompt>`：图片描述，必填
   - `--model=`：模型，默认 `auto`
   - `--aspect=`：宽高比，默认 1:1
   - `--resolution=`：分辨率，根据模型能力
   - `--count=`：数量，默认 1
   - `--negative=`：负面提示词
   - `--output=`：输出目录

2. **模型选择**（auto 模式）：

   | Prompt 关键词 | 推荐模型 |
   |--------------|---------|
   | realistic / 真实 / 摄影 | imagen-4, midjourney-v7 |
   | logo / 字体 / 排版 | recraft-v3, ideogram-2.0 |
   | anime / 二次元 | midjourney-v7, sd-3.5 |
   | fast / 速度 | nano-banana-2 |
   | open / 开源 / 商用 | flux-pro, sd-3.5 |
   | 4K / 高清 | imagen-4, nano-banana-2 |
   | character / 虚拟形象 | midjourney-v7 |

3. **调用模型**：

   ```bash
   # 示例：imagen-4
   curl -X POST "https://generativelanguage.googleapis.com/v1beta/models/imagen-4:generateImage" \
     -H "Authorization: Bearer $GOOGLE_API_KEY" \
     -d '{
       "prompt": "<prompt>",
       "aspect_ratio": "16:9",
       "count": 1
     }'
   ```

4. **输出**：

   ```
   ✅ 图片生成完成
   模型：imagen-4
   分辨率：4K (4096x2160)
   数量：4 张
   输出：./cities/
     - city-001.png
     - city-002.png
     - city-003.png
     - city-004.png
   ```

## 子行为

<!-- section:model -->
### `--model=<name>` 显式指定模型

| 模型 | 强项 | 弱项 |
|------|------|------|
| imagen-4 | 真实感、4K | 价格高 |
| nano-banana-2 | 速度 + 质量 | 创意一般 |
| dall-e-3 | 创意、文字 | 风格化弱 |
| midjourney-v7 | 风格化标杆 | 等待长 |
| flux-pro | 开源 + 商用 | 真实感弱 |
| sd-3.5 | 生态丰富 | 需 GPU |
| recraft-v3 | 设计师向 | 写实弱 |
| ideogram-2.0 | 文字渲染 | 风格化弱 |
<!-- end -->

<!-- section:aspect -->
### `--aspect=<ratio>` 宽高比

| 比例 | 适用 |
|------|------|
| 1:1 | 头像、Instagram |
| 16:9 | YouTube、桌面 |
| 9:16 | TikTok、抖音 |
| 4:3 | 传统照片 |
| 3:4 | 印刷品 |
| 21:9 | 电影 |
<!-- end -->

<!-- section:resolution -->
### `--resolution=<p>` 分辨率

| 模型 | 1K | 2K | 4K |
|------|----|----|-----|
| imagen-4 | ✓ | ✓ | ✓ |
| nano-banana-2 | ✓ | ✓ | ✓ |
| midjourney-v7 | ✓ | ✓ | ✓ |
| dall-e-3 | ✓ | ✗ | ✗ |
| flux-pro | ✓ | ✓ | ✗ |
| sd-3.5 | ✓ | ✓ | ✗ |
<!-- end -->

<!-- section:negative -->
### `--negative=<text>` 负面提示词

避免的元素：

```
--negative="blurry, low quality, distorted, ugly, watermark, text"
```

通常包括：模糊、低质量、扭曲、难看、水印、文字、错误解剖、风格混乱。
<!-- end -->

## 模板变量

- `$ARGUMENTS`：用户输入的完整参数
- `$PLUGIN_NAME`：当前插件名（ai-image-gen）
- `$PROJECT_ROOT`：当前工作项目根目录

## 提示

- 配合 `/image-edit` 走局部修改
- 配合 `ai-video-gen` 走图生视频
- 配合 `ui-ux-pro-max` 走色彩心理学
- 八字 prompt 公式：[主体] [细节] [环境] [光线] [风格]
