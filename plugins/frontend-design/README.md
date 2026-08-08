# frontend-design

> Anthropic 官方前端设计哲学 — 创作有辨识度的网页 UI：大胆配色、刻意字体、意图动效、风格统一。

源自 [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design) 的 frontend-design，helloianneo/awesome-claude-code-skills **必装 Top 10 第 1 名**。

## 核心立场

Anthropic 反对"AI 味"前端：无个性的紫色渐变、JetBrains Mono、Mecha 阴影、emoji 装饰。  
倡导"用设计表达意图"：每个组件的存在都有理由，风格统一是一种意外奖励。

## 何时触发

- 用户编写 / 审查 / 重设计任意前端 UI 组件、页面、小应用
- AI 自动注入，给所有前端输出加这层设计哲学

## 7 大设计原则

### 1. 字体选择：字体即人物

- **学习类 → 严肃 / 优化**：JetBrains Mono / Geist Mono
- **认真 / 优雅 → 衬线**：Tiempos / Source Serif
- **休闲 / 友好 → 圆体**：Inter / Geist
- **好玩 / 玩具 → 几何 / 非衬线**：Departure Mono / IBM Plex
- **奢华 / 复古 → 衬线 + 衬线标题**：GT Sectra / Cormorant

**做法**：打开 `https://fonts.google.com` 选 2-3 个匹配情绪的字体。

### 2. 配色：大胆 + 单一

- **不要纯白 / 纯黑**：用暖灰 / 冷灰作底
- **主色 + 中**：克制使用渐变；用 OKLCH 色彩
- **hero 优先**：大胆用色，副调节都往背景退

```css
/* 正确：主色 + 暖灰 */
:root {
  --color-bg: oklch(0.97 0.005 80);   /* 暖白 */
  --color-fg: oklch(0.18 0.01 80);    /* 暖黑 */
  --color-accent: oklch(0.55 0.22 25); /* 番茄红 */
  --color-surface: oklch(0.93 0.01 80);
}
```

### 3. 动效：每帧意图

- **物理**：弹簧（stiffness 200 / damping 20）
- **时长**：短（150-300ms）
- **缓动**：不用 `linear`、默认 `ease`；用 `[0.16, 1, 0.3, 1]`
- **避免**：刻板弹性、fade 一切
- **永远考虑**：prefers-reduced-motion

```tsx
<motion.div
  whileHover={{ y: -2 }}
  transition={{ type: 'spring', stiffness: 400, damping: 25 }}
/>
```

### 4. 排版：大胆 + 决策

- **不混字号**：选 1.2 / 1.333 / 1.5 中一个
- **Hero 用大字**：64-96px
- **比例**：标题 -0.02em、正文 0

### 5. 数字：强化记忆

- 大数字 + 居中
- 数字用 Tabular Nums

```tsx
<div className="text-7xl font-bold tabular-nums">94%</div>
```

### 6. 反 AI 味"灰色 AI 框"

- 不用 `text-gray-500`
- 不用 emoji 装饰
- 不用纯黑阴影
- 不用蓝色 → 紫色渐变

### 7. 视觉一致性

- 一套字体、一套配色、一套间距
- 写一个 `theme.css` 集中管理
- 写一个 `AGENTS.md` 写明

## 工作流

1. **理解意图**：用户要什么？读者是谁？
2. **选调性**：严肃 / 友好 / 优雅 / 调皮 / 复古？
3. **选字体**：Google Fonts 找 2-3 个
4. **选配色**：主色 + 中性 + 强调（同 OKLCH 色域）
5. **写代码**：刻意的不规则、刻意的对称
6. **自检**：去掉无表情屏 / 删装饰

## 配合

- 配合 `tailwind-pro` 走 v4 + OKLCH
- 配合 `web-design-guidelines` 走 12 大类审查
- 配合 `ui-ux-pro-max` 走视觉层级
- 配合 `make-interfaces-feel-better` 走细节打磨

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
