# ai-video-gen

> AI 视频生成 — 40+ 视频模型统一封装（Veo / Wan / Grok / Sora / Runway / Pika / Kling / Luma / 可灵 / 即梦...）

源自 [inferen-sh/skills](https://github.com/inferen-sh/skills) 的 ai-video-generation，helloianneo/awesome-claude-code-skills **好用**。

本插件为 AI 提供 40+ 视频模型的统一调用接口，覆盖文本到视频（T2V）、图片到视频（I2V）、视频到视频（V2V）、首尾帧控制、视频扩展等。

## 支持模型（40+）

### 顶级模型

| 模型 | 提供商 | 分辨率 | 时长 | 特点 |
|------|--------|--------|------|------|
| **Veo 3** | Google DeepMind | 1080p | 8s | 物理级真实 |
| **Veo 2** | Google DeepMind | 4K | 8s | 长时长 + 影视 |
| **Wan 2.5** | Alibaba | 1080p | 10s | 国产顶级 |
| **Sora 2** | OpenAI | 1080p | 20s | 一致性强 |
| **Sora** | OpenAI | 1080p | 20s | 写真级 |
| **Grok Video** | xAI | 720p | 10s | 创意风格 |
| **Kling 2.0** | Kuaishou | 1080p | 10s | 国产标杆 |
| **可灵 1.6** | Kuaishou | 1080p | 10s | 物理模拟 |
| **即梦 3.0** | ByteDance | 1080p | 12s | 字节系 |
| **Hailuo 02** | MiniMax | 1080p | 6s | 性价比高 |

### 创意工具

| 模型 | 特点 |
|------|------|
| **Runway Gen-4** | 影视级，5s/10s |
| **Pika 2.0** | 风格化、动漫感 |
| **Luma Dream Machine** | 相机运动 |
| **Vidu** | 国产，高质量 |
| **PixVerse** | 风格多样 |
| **Higgsfield** | 角色一致 |
| **Lightricks LTX** | 开源、轻量 |

### 开源

| 模型 | 特点 |
|------|------|
| **Wan 2.1** | Apache 2.0 |
| **Mochi 1** | Apache 2.0 |
| **LTX-Video** | 开源 |
| **CogVideoX** | 智源 |

## 安装

```bash
/plugin marketplace add martin98-afk/drifox-plugins
/plugin install ai-video-gen@drifox-official
```

需要各厂商 API Key：

```bash
export GOOGLE_API_KEY=...            # Veo
export OPENAI_API_KEY=...            # Sora
export DASHSCOPE_API_KEY=...        # Wan
export KLING_ACCESS_KEY=...         # 可灵
# ... 按需设置
```

## 命令

| 命令 | 用途 |
|------|------|
| `/video-generate <prompt>` | 文本生成视频 |
| `/video-from-image <url>` | 图片生成视频 |
| `/video-extend <video>` | 视频扩展 |
| `/video-models` | 列出所有可用模型 |

### `/video-generate --help`

```bash
/video-generate \
  --prompt="A cat walking on a beach at sunset, cinematic" \
  --model=veo-3 \
  --duration=8s \
  --resolution=1080p \
  --aspect=16:9 \
  --output=cat-beach.mp4
```

## 实战模板

### 营销视频

```bash
/video-generate \
  --prompt="A modern SaaS dashboard floating in space, clean UI, \
soft gradient background, professional typography, 4K" \
  --model=veo-3 \
  --duration=8s \
  --aspect=16:9
```

### 角色动画

```bash
/video-generate \
  --prompt="A character walking through a forest, anime style, \
smooth motion, high quality" \
  --model=kling-2.0 \
  --duration=10s \
  --aspect=9:16
```

### 产品展示

```bash
/video-from-image \
  --image=/uploads/shoe.png \
  --prompt="Rotate 360 degrees, soft lighting, studio white background" \
  --model=runway-gen-4 \
  --duration=5s
```

## 模型选择指南

| 需求 | 推荐模型 |
|------|---------|
| 影视级真实 | Veo 3 / Sora 2 |
| 国产 + 高质量 | Wan 2.5 / 可灵 1.6 |
| 动漫风格 | Pika 2.0 / Kling |
| 长时长 | Sora 2 / Veo 2 |
| 性价比 | Hailuo 02 / 即梦 3.0 |
| 角色一致 | Higgsfield / Kling |
| 创意风格 | Grok Video / PixVerse |
| 开源 | Wan 2.1 / Mochi 1 |

## 5 个 Prompt 公式

### 1. 镜头公式

```
[主体] [动作] [环境] [镜头] [风格]
"a cat walks on sand at sunset, tracking shot, cinematic"
```

### 2. 动作清单

```
主体 + 动作 + 速度 + 方向
"a dog runs forward through snow, fast, towards camera"
```

### 3. 风格化

```
[主体] + [风格] + [色温] + [光线]
"a portrait, oil painting style, warm tones, soft lighting"
```

### 4. 物理级

```
[主体] + [物理动作] + [材质] + [光线]
"water drops into a clear pool, refraction, sunlight, slow motion"
```

### 5. 运镜

```
[主体] + [动作] + [镜位]
"a mountain peak, dolly in from 100m to 10m, fog"
```

## 8 个反模式

- ❌ 抽象 prompt（"做一个好看的视频"）
- ❌ 多主体混淆（"猫和狗和鸡在一起"）
- ❌ 复杂动作（"跳舞然后翻跟斗然后倒立"）
- ❌ 文字要求（"屏幕上显示 'Hello'"）
- ❌ 4K + 长时长（小模型不支持）
- ❌ 动画风格混合（半写实半动漫）
- ❌ 强光与暗光（光照过强）
- ❌ 模糊描述（"类似漫威"）

## 配合

- 配合 `ai-image-gen` 先生成关键帧
- 配合 `web-design-skills` 设计封面
- 配合 `copywriting` 写分镜
- 配合 `seo-audit` 优化视频页面

## 许可

MIT（inferen-sh/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
