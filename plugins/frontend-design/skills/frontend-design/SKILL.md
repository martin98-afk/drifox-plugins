---
name: frontend-design
description: 创作有辨识度的网页 UI — 编写任意前端组件、网页、应用时自动注入 Anthropic 官方设计哲学：大胆配色、刻意字体、意图动效、风格统一。用于：组件 / 页面 / 小型前端应用、视觉审查、风格统一。触发关键词：前端设计、frontend design、UI 设计、视觉设计、网页设计、配色、字体、动效、anthropic skills、style guide、design philosophy、distinctive UI。
---

# frontend-design 技能 — Anthropic 官方设计哲学

源自 [anthropics/skills/frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)。本技能为 AI 提供"产出具有辨识度的网页 UI"的能力，与生成"AI 味"前端做明确切割。

## 何时触发

- 编写 / 审查 / 重设计任意前端代码
- 用户提到"风格"、"调性"、"配色"、"字体"、"动效"
- AI 自动注入，给所有前端输出加这层哲学

## 三大核心立场

### 立场 1：字体即人物

| 调性 | 字体 |
|------|------|
| 学习 / 严肃 / 优化 | JetBrains Mono, Geist Mono |
| 认真 / 优雅 / 严肃 | Tiempos, Source Serif, GT Sectra |
| 休闲 / 友好 / 易读 | Inter, Geist, IBM Plex |
| 好玩 / 玩具 / 创意 | Departure Mono, Space Grotesk |
| 奢华 / 复古 / 编辑 | Cormorant, Playfair Display |

**做法**：打开 `https://fonts.google.com` 选 2-3 个匹配情绪的字体。

### 立场 2：配色大胆 + 克制

- ❌ 不用纯白 / 纯黑（用 oklch(0.97 0.005 80) 这种暖灰）
- ❌ 不用蓝紫渐变（AI 味）
- ❌ 不用太多色（1 主色 + 1 中性 + 1 强调）
- ✅ 用 OKLCH 色彩空间（感知更均匀）

```css
:root {
  --color-bg: oklch(0.97 0.005 80);    /* 暖白 */
  --color-fg: oklch(0.18 0.01 80);     /* 暖黑 */
  --color-accent: oklch(0.55 0.22 25); /* 番茄红 */
  --color-surface: oklch(0.93 0.01 80);
  --color-muted: oklch(0.55 0.01 80);  /* 暖灰 */
}
```

### 立场 3：动效每帧意图

- ✅ 物理弹簧（stiffness 200-400 / damping 20-30）
- ✅ 时长短（150-300ms）
- ✅ 缓动曲线：`[0.16, 1, 0.3, 1]` 或 `cubic-bezier(0.65, 0, 0.35, 1)`
- ❌ 不用 `linear` 或 `ease`（廉价）
- ❌ 不用 fade 一切（无聊）
- ♿ 永远考虑 `prefers-reduced-motion`

```tsx
<motion.button
  whileHover={{ y: -2 }}
  whileTap={{ scale: 0.95 }}
  transition={{ type: 'spring', stiffness: 400, damping: 25 }}
>
  Click me
</motion.button>
```

## 9 大反 AI 味清单

### 1. 不要紫色渐变白卡

```css
/* ❌ AI 味 */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
border-radius: 16px;
box-shadow: 0 8px 32px rgba(102, 126, 234, 0.4);
color: white;
```

### 2. 不要纯灰层级

```
❌ text-gray-500 / text-gray-600 / text-gray-700
✅ text-zinc-700 / text-stone-600 / text-neutral-600
```

### 3. 不要 emoji 装饰

```
❌ 🚀 ✨ 💡 🔥 ⚡ 🎉 🌟 💫 🎯
✅ 删除或用 SVG icon
```

### 4. 不要手写字体默认

```
❌ font-family: 'Bradley Hand', cursive;
✅ 选个符合调性的字体
```

### 5. 不要"Lorem Ipsum"

```
❌ "Lorem ipsum dolor sit amet..."
✅ 与语境匹配的占位文字
```

### 6. 不要"圆角过大"

```
❌ border-radius: 32px（卡片式）
✅ border-radius: 8-12px（克制）
```

### 7. 不要 Mecha 阴影

```
❌ box-shadow: 0 0 80px rgba(124, 58, 237, 0.5);
✅ 微妙阴影或边框
```

### 8. 不要 emoji 数字

```
❌ 1️⃣ 2️⃣ 3️⃣
✅ Ol 列表 + 计数
```

### 9. 不要在所有 hero 上放大字

```
❌ 96px 标题 + 90% 留白
✅ 字号根据上下文 / 品牌调性
```

## 5 大设计意图

### 1. 对比（Contrast）

大小对比、颜色对比、字重对比、间距对比。

### 2. 重复（Repetition）

字体、配色、间距、圆角在整站保持一致。

### 3. 对齐（Alignment）

4 列 / 8 列网格对齐、子元素对齐网格。

### 4. 亲密性（Proximity）

相关元素靠近、不相关元素远离。

### 5. 留白（White Space）

奢侈地使用留白，让眼睛呼吸。

## 5 个工作流

### 1. 理解意图

- 用户要什么？
- 读者是谁？
- 调性是什么？

### 2. 选调性

- 严肃 / 优雅 / 友好 / 调皮 / 复古？
- 写一句"风格宣言"：`本站是一个帮助开发者写日志的工具，应该专业、克制、温暖。`

### 3. 选字体 + 配色

- 字体 2-3 个
- 配色：1 主色 + 1 中性 + 1 强调

### 4. 写代码

- 集中写一个 `theme.css` 统一定义
- 写一个 `AGENTS.md` 写明风格

### 5. 自检

- 删 / 减 ornament
- 校对比度
- 测移动端

## 实战模板

### Marketing Page Hero

```tsx
export default function Hero() {
  return (
    <section className="min-h-screen bg-[oklch(0.97_0.005_80)] text-[oklch(0.18_0.01_80)]">
      <div className="container mx-auto px-4 py-32">
        <h1 className="font-serif text-7xl font-bold tracking-tight md:text-9xl">
          Write code<br />
          <span className="italic text-[oklch(0.55_0.22_25)]">that ships</span>
        </h1>
        <p className="mt-8 max-w-2xl text-xl text-[oklch(0.55_0.01_80)]">
          A modern editor for the next generation of developers.
        </p>
        <button className="mt-12 inline-flex items-center gap-2 bg-[oklch(0.18_0.01_80)] px-8 py-4 text-white transition-transform hover:-translate-y-1">
          Start writing
          <ArrowRight className="h-5 w-5" />
        </button>
      </div>
    </section>
  )
}
```

### Dashboard Card

```tsx
<motion.div
  whileHover={{ y: -2 }}
  className="rounded-lg border border-[oklch(0.92_0.005_80)] bg-white p-6"
  transition={{ type: 'spring', stiffness: 400, damping: 25 }}
>
  <div className="text-sm font-medium uppercase tracking-wider text-[oklch(0.55_0.01_80)]">
    Active Users
  </div>
  <div className="mt-2 text-5xl font-bold tabular-nums">12,847</div>
  <div className="mt-2 text-sm text-[oklch(0.55_0.22_145)]">+12.4% from last week</div>
</motion.div>
```

## 配合

- 配合 `tailwind-pro` 走 v4 + OKLCH token
- 配合 `web-design-guidelines` 走 12 大类审查
- 配合 `ui-ux-pro-max` 走视觉层级
- 配合 `make-interfaces-feel-better` 走细节打磨
- 配合 `motion` / `animation-systems` 走动效
