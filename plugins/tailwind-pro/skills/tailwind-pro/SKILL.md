---
name: tailwind-pro
description: Tailwind CSS v4 完整支持 — 类名 / 任意值 / 设计系统 / 主题变量 / OKLCH 色彩 / 响应式 / dark mode。触发关键词：tailwind、tailwindcss、tailwind v4、utility class、@apply、@theme、oklch、任意值、arbitrary value、design token、tailwind 主题、tailwind 迁移。
---

# Tailwind CSS v4 技能

本技能为 AI 提供 Tailwind CSS v4 完整知识，覆盖类名、任意值、主题变量、OKLCH 色彩、设计系统、最佳实践。

## v4 核心新特性

### 1. CSS-first 配置（无需 `tailwind.config.js`）

```css
/* v4 */
@import "tailwindcss";

@theme {
  --color-brand-500: oklch(0.7 0.2 240);
  --spacing-18: 4.5rem;
  --font-display: "Inter", sans-serif;
}
```

### 2. 自动内容检测

无需 `content: [...]`，v4 自动扫描源文件。

### 3. OKLCH 色彩空间

```css
@theme {
  /* OKLCH 比 HSL/Hex 感知更均匀 */
  --color-primary: oklch(0.65 0.21 260);
  --color-success: oklch(0.7 0.17 145);
  --color-danger: oklch(0.65 0.25 25);
}
```

### 4. @custom-variant（自定义变体）

```css
@custom-variant dark (&:where(.dark, .dark *));
@custom-variant hover (&:hover);
@custom-variant rtl (selector(:where([dir="rtl"], [dir="rtl"] *)));
```

### 5. @utility（自定义工具类）

```css
@utility scrollbar-hidden {
  &::-webkit-scrollbar {
    display: none;
  }
}
```

## 任意值（Arbitrary Values）

```html
<!-- 任意像素 -->
<div class="top-[117px]"></div>

<!-- 任意颜色 -->
<div class="bg-[#bada55]"></div>
<div class="text-[oklch(0.5_0.2_240)]"></div>

<!-- 任意 CSS 变量 -->
<div class="text-[length:var(--text-base)]"></div>

<!-- 任意 grid -->
<div class="grid grid-cols-[200px_1fr_200px]"></div>

<!-- 任意 calc -->
<div class="p-[clamp(1rem,4vw,2rem)]"></div>
```

## 响应式（v4 语法）

```html
<!-- 移动优先 -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3"></div>

<!-- 任意断点 -->
<div class="grid grid-cols-1 [@media(min-width:1200px)]:grid-cols-4"></div>
```

## Dark Mode

```css
/* 启用 dark 变体 */
@custom-variant dark (&:where(.dark, .dark *));
```

```html
<div class="bg-white dark:bg-zinc-900 text-black dark:text-white"></div>
```

## v3 → v4 迁移要点

| v3 写法 | v4 写法 |
|--------|--------|
| `tailwind.config.js` | 删除（用 `@theme`） |
| `@tailwind base/components/utilities` | `@import "tailwindcss"` |
| `bg-gradient-to-r` | `bg-linear-to-r` |
| `shadow-sm` | `shadow-xs` |
| `content: [...]` | 自动 |
| `darkMode: 'class'` | `@custom-variant dark` |

## 设计系统最佳实践

### 1. Token 命名规范

```css
@theme {
  /* 语义化命名 */
  --color-canvas: oklch(1 0 0);        /* 背景 */
  --color-surface: oklch(0.98 0 0);    /* 卡片/抬升 */
  --color-text: oklch(0.2 0 0);        /* 主文本 */
  --color-text-muted: oklch(0.5 0 0);  /* 次文本 */
  --color-border: oklch(0.92 0 0);     /* 描边 */

  --color-primary: oklch(0.65 0.21 260);
  --color-success: oklch(0.7 0.17 145);
  --color-warning: oklch(0.78 0.16 80);
  --color-danger: oklch(0.65 0.25 25);

  /* 间距阶梯（8 倍数） */
  --spacing-1: 0.25rem;
  --spacing-2: 0.5rem;
  --spacing-4: 1rem;
  --spacing-8: 2rem;
}
```

### 2. 组件组合模式

```html
<!-- 卡片：组合而非继承 -->
<article class="rounded-lg border border-zinc-200 bg-white p-4 shadow-xs">
  <h2 class="text-lg font-semibold text-zinc-900">Title</h2>
  <p class="mt-2 text-sm text-zinc-600">Description</p>
</article>
```

### 3. 避免过度 utility

```html
<!-- ❌ 过长难维护 -->
<button class="bg-blue-500 hover:bg-blue-600 focus:ring-2 focus:ring-blue-300 active:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2 rounded text-white font-medium transition-colors">

<!-- ✅ 提取为 @utility -->
<!-- @utility btn-primary { ... } -->
<button class="btn-primary px-4 py-2">
```

## 反模式

- ❌ **不要**保持 v3 的 `tailwind.config.js`（v4 不再需要）
- ❌ **不要**用 `@apply` 替代组件（v4 鼓励组件抽象）
- ❌ **不要**混用 v3 / v4 类名（如 `bg-gradient-to-r`）
- ❌ **不要**在生产用 CDN（用 `npx tailwindcss -o` 编译）
- ❌ **不要**忽略 JIT 模式（v4 默认开）

## 配色公式（OKLCH 推荐）

```
oklch(亮度 0~1  色度 0~0.4  色相 0~360)
```

| 用途 | 推荐值 |
|------|--------|
| 主色 | `oklch(0.65 0.21 品牌色色相)` |
| 辅色 | `oklch(0.7 0.17 145)`（绿） |
| 警告 | `oklch(0.78 0.16 80)`（黄） |
| 危险 | `oklch(0.65 0.25 25)`（红） |
| 中性 | `oklch(0.5 0 0)`（灰） |

## 提示

- 配合 `react-pro` 编写 React 组件时自动应用
- 配合 `frontend-pro` 验证 a11y（对比度）
- 配合 `web-design-skills` 做整体视觉
- 自动启用 `tailwindcss` LSP（hover / 补全 / 颜色预览）
