---
name: brand-guidelines
description: Anthropic 官方品牌规范 — 应用颜色 / 字体 / 视觉 / 调性 / 动效到任意 artifact（文档 / 网站 / 演示）。触发关键词：brand guidelines、antropische brand、anthropic 品牌、应用品牌、官方品牌、品牌规范、san serif、cream、near-black、字距、版权、anthropic 字体、anthropic 颜色。
---

# Brand Guidelines 技能 — Anthropic 官方品牌规范

源自 [anthropics/skills/brand-guidelines](https://github.com/anthropics/skills/tree/main/skills/brand-guidelines)。本技能为 AI 提供应用 Anthropic 官方品牌设计语言到任意 artifact 的能力。

## 何时触发

- 用户要求"应用 Anthropic 品牌风格"
- 用户要求"anthropic-look"、"Claude-look"
- 用户提到"anthropic 品牌"、"官方品牌"

## 5 大品牌元素

### 1. 字体

#### 主字体：Anthropic Sans

- 主字体：Anthropic Sans（自研）
- 备用：Inter / Geist
- 略备：Tiempos Headline（标题衬线）

```css
:root {
  --font-sans: 'Anthropic Sans', 'Inter', 'Geist', sans-serif;
  --font-serif: 'Tiempos Headline', 'Source Serif', serif;
}
```

#### 字距（Tracking）

| 元素 | 字距 |
|------|------|
| 正文 | -0.005em |
| 标题 | -0.01em |
| 大写 | +0.05em |

#### 字间距

```css
/* 中英文混排，调整间距 */
.cn-en-mix { word-spacing: 0.05em; }
```

### 2. 颜色

#### 主色

| 名称 | OKLCH | 用途 |
|------|-------|------|
| **Cream** | `oklch(0.97 0.005 80)` | 主背景 |
| **Near-black** | `oklch(0.18 0.01 80)` | 主文本 |
| **Tomato** | `oklch(0.55 0.22 25)` | 强调 / CTA |
| **Mid-gray** | `oklch(0.55 0.01 80)` | 次文本 |
| **Light-gray** | `oklch(0.92 0.005 80)` | 边框 / 分割 |

```css
:root {
  --color-cream: oklch(0.97 0.005 80);
  --color-near-black: oklch(0.18 0.01 80);
  --color-tomato: oklch(0.55 0.22 25);
  --color-mid-gray: oklch(0.55 0.01 80);
  --color-light-gray: oklch(0.92 0.005 80);
}
```

#### 应用规则

- 背景：cream（暖白，不纯白）
- 文本：near-black（暖黑，不纯黑）
- 强调：tomato（克制使用）
- 边框：light-gray

### 3. 视觉元素

#### 形状

- 圆角：8-12px（卡片）
- 边框：1px light-gray
- 阴影：克制（不要 Mecha 阴影）

#### 间距

- 8 倍数：4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96
- 段落间距：1.5em
- 区块间距：96px

### 4. 调性

#### 语气

- 严谨但不冷淡
- 友好但不轻浮
- 智能但不卖弄
- 助力但不阿谀

#### 用词

- "我" / "我们" 优于 "AI"
- 主动语态
- 简短句
- 避免术语堆砌

### 5. 动效

#### 缓动

```css
:root {
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
}
```

#### 时长

- 短：150-200ms
- 中：300-400ms
- 长：500ms+（少用）

#### 触发

- prefers-reduced-motion: 减弱

## 5 大应用场景

### 1. 演示文稿

```css
:root {
  --slide-bg: oklch(0.97 0.005 80);
  --slide-text: oklch(0.18 0.01 80);
  --slide-accent: oklch(0.55 0.22 25);
}
```

字体：标题用 Anthropic Sans 700，正文 400。

### 2. 文档

```css
:root {
  --doc-bg: oklch(0.97 0.005 80);
  --doc-text: oklch(0.18 0.01 80);
  --doc-link: oklch(0.55 0.22 25);
}
```

行高 1.6，字距 -0.005em。

### 3. 网站

```css
:root {
  --bg: oklch(0.97 0.005 80);
  --fg: oklch(0.18 0.01 80);
  --accent: oklch(0.55 0.22 25);
  --border: oklch(0.92 0.005 80);
}
```

### 4. README

```markdown
# Project Title

主标题用 Anthropic Sans 700。
副标题用 400。
```

### 5. Logo 使用

- 保持清晰边距（周围留 ≥ Logo 高度 50%）
- 不扭曲
- 不用动画 logo
- 暗色模式用反白

## 4 个反模式

- ❌ **用纯白 / 纯黑** — 用 cream / near-black
- ❌ **用其他品牌色** — 保持克制
- ❌ **多色滥用** — 1 主色 + 2 中性
- ❌ **emoji 装饰** — 删除

## 5 个最佳实践

1. **留白奢侈**：让眼睛呼吸
2. **字体克己**：1-2 个字体
3. **色彩克制**：1 主色 + 2 中性
4. **动效克制**：少数动效
5. **断点一致**：跨页一致

## 配合

- 配合 `frontend-design` 走 Anthropic 设计哲学
- 配合 `tailwind-pro` 走 OKLCH token
- 配合 `web-design-guidelines` 走 12 大类审查

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
