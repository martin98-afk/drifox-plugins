# ai-image-gen

> AI 图片生成 — 主流文生图（T2I）与图编辑模型统一封装（Gemini / DALL-E / Imagen / Midjourney / Stable Diffusion / FLUX），支持 4K 输出。

源自 [inferen-sh/skills](https://github.com/inferen-sh/skills) 的 nano-banana-2 和 ai-image-generation 整合，helloianneo/awesome-claude-code-skills **好用**。

## 支持模型

### 顶级文生图

| 模型 | 提供商 | 分辨率 | 特点 |
|------|--------|--------|------|
| **Imagen 4** | Google | 4K | 真实感顶级 |
| **Nano Banana 2** | Google | 4K | 速度 + 质量 |
| **DALL-E 3** | OpenAI | 1024 | 创意 + 文字 |
| **Midjourney v7** | Midjourney | 2K | 风格化标杆 |
| **FLUX.1 Pro** | Black Forest Labs | 2K | 开源、可商用 |
| **FLUX.1 Dev** | Black Forest Labs | 2K | 开源、研发 |
| **Stable Diffusion 3.5** | Stability AI | 2K | 生态丰富 |
| **Recraft v3** | Recraft | 2K | 设计师向 |
| **Ideogram 2.0** | Ideogram | 2K | 文字渲染 |
| **Playground v2.5** | Playground | 2K | 风格多样 |

### 图编辑（多模态）

| 模型 | 特点 |
|------|------|
| **Gemini 2.5 Flash Image** | 多图编辑、4K |
| **GPT-4o Image** | 自然语言编辑 |
| **SeedDream** | 字节系 |
| **Qwen-VL-Edit** | 阿里 |
| **InstructPix2Pix** | 开源 |

## 安装

```bash
/plugin marketplace add martin98-afk/drifox-plugins
/plugin install ai-image-gen@drifox-official
```

需要 API Key：

```bash
export GOOGLE_API_KEY=...       # Imagen / Gemini
export OPENAI_API_KEY=...       # DALL-E / GPT-4o
export REPLICATE_API_KEY=...    # 多模型
export STABILITY_API_KEY=...    # Stable Diffusion
```

## 命令

| 命令 | 用途 |
|------|------|
| `/image-generate <prompt>` | 文本生成图片 |
| `/image-edit <image>` | 图片编辑 |
| `/image-upscale <image>` | 图片放大 |
| `/image-variations <image>` | 图片变体 |
| `/image-models` | 列出所有模型 |

### `/image-generate --help`

```bash
/image-generate \
  --prompt="a futuristic city at sunset, cyberpunk style, 4K" \
  --model=imagen-4 \
  --aspect=16:9 \
  --count=4 \
  --output=./cities/
```

## 实战模板

### 营销 Banner

```bash
/image-generate \
  --prompt="A modern SaaS hero banner, abstract gradient, clean typography space, professional, 4K" \
  --model=imagen-4 \
  --aspect=16:9
```

### 头像

```bash
/image-generate \
  --prompt="A young developer portrait, soft lighting, neutral background, professional headshot" \
  --model=midjourney-v7 \
  --aspect=1:1
```

### Logo 概念

```bash
/image-generate \
  --prompt="A minimalist logo for a tech startup, geometric, monoline, vector style" \
  --model=recraft-v3 \
  --aspect=1:1
```

### 修复/编辑

```bash
/image-edit \
  --image=./photo.png \
  --prompt="Replace the sky with a sunset, keep the foreground" \
  --model=gemini-2.5-flash-image
```

## 5 个 Prompt 公式

### 1. 主体公式

```
[主体] + [细节] + [环境] + [光线] + [风格]
"a cat, fluffy, on a beach, sunset, cinematic"
```

### 2. 文字+风格

```
[文字内容] + [字体] + [位置] + [风格]
"a logo with 'Hello', bold sans-serif, centered, minimalist"
```

### 3. 摄影

```
[主体] + [镜头] + [光圈] + [快门] + [风格]
"a portrait, 85mm, f/1.4, 1/200, golden hour"
```

### 4. 二次元

```
[主体] + [风格] + [构图] + [色温]
"a warrior, anime style, full body, warm tones"
```

### 5. 概念艺术

```
[主体] + [情绪] + [颜色] + [光线]
"a dragon, epic, dark purple, dramatic lighting"
```

## 8 个反模式

- ❌ 抽象 prompt（"好看的图"）
- ❌ 多主体混淆（"猫和狗和鸡"）
- ❌ 模糊风格（"类似迪士尼"）
- ❌ 复杂构图（"5 个人 + 风景 + 建筑"）
- ❌ 文字要求（"屏幕上显示 'Hello'"）
- ❌ 比例极端（"32:9"）
- ❌ 风格混合（"半写实半动漫"）
- ❌ 强光或暗光（光照过强）

## 配合

- 配合 `ai-video-gen` 提供图片引导
- 配合 `web-design-skills` 设计封面
- 配合 `ui-ux-pro-max` 走色彩心理学
- 配合 `make-interfaces-feel-better` 走细节

## 许可

MIT（inferen-sh/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
