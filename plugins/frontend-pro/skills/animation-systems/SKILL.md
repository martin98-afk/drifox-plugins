---
name: animation-systems
description: Stripe / Linear / Apple 级别网页动效系统 — 微交互 / 状态过渡 / 编排 / 动效 token / 动效设计原则。源自 guilhermemarketing/gui-marketing-skills。触发关键词：微交互、动效系统、动效设计、状态过渡、view transitions、动效架构、strip 级动效、linear 级别动效、apple 级别动效。
---

# Animation Systems — Stripe / Linear / Apple 级别动效

源自 [guilhermemarketing/gui-marketing-skills](https://github.com/guilhermemarketing/gui-marketing-skills) 的 animation-systems，helloianneo/awesome-claude-code-skills **强推**。

本技能为 AI 提供"高级感"动效设计方法论，让产品动效达到 Stripe / Linear / Apple 级别。

## 何时触发

- "让动效更高级"、"专业级动效"
- "微交互"、"状态过渡"
- "Stripe / Linear / Apple 那种感觉"
- 设计 SaaS / 工具类产品

## 7 大动效原则

### 1. 动效是状态，不是装饰

```
❌ 装饰性动效：动画本身是目的
✅ 状态性动效：动画是状态变化的副产物
```

每段动画都应该回答：**"什么状态变了？"**

| 状态变化 | 动效 |
|---------|------|
| 加载中 | 骨架 / spinner |
| 成功 | 300ms 淡入 + 轻微缩放 |
| 错误 | 4px 抖动 + 颜色变化 |
| 选中 | 200ms 缩放 + 边框颜色 |
| 激活 | 150ms 弹簧 |
| 警告 | 500ms 颜色脉冲 |

### 2. 动效时长公式

```
时长 = 0.3 * 距离^0.5
```

| 距离 | 时长 |
|------|------|
| 10px | 100ms |
| 50px | 200ms |
| 200px | 400ms |
| 500px | 700ms |

短距离动效要快，长距离动效可以慢。

### 3. 缓动（Easing）

| 关系 | 缓动 |
|------|------|
| 入场 | `ease-out`（开始快，结束慢） |
| 出场 | `ease-in`（开始慢，结束快） |
| 双向 | `ease-in-out`（对称） |
| 弹性 | `spring`（自然） |
| 紧急 | `ease-in-back`（结束回弹） |

高级感源于**缓动的细微差异**：

```css
/* ❌ 默认 ease（廉价） */
transition: all 0.3s ease;

/* ✅ 自定义 ease-out-expo（高级） */
transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);

/* ✅ 弹性（自然） */
transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
```

### 4. 编排（Choreography）

#### 4.1 stagger 列表

```tsx
const container = {
  show: { transition: { staggerChildren: 0.05 } }
}
const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
}
```

#### 4.2 父子关系

```
父级先动 → 子级接力动 → 整体完成
父级 300ms → 子级 200ms（错开 100ms）
```

#### 4.3 视口触发

```tsx
<motion.div
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: '-50px' }}
/>
```

### 5. 微交互（Microinteractions）

| 触发 | 视觉反馈 | 持续 |
|------|---------|------|
| Button hover | 背景色 + 1px 缩放 | 150ms |
| Button click | 0.95 缩放 | 100ms |
| Input focus | 边框色 + 2px 轮廓 | 200ms |
| Toggle on | 滑块平移 + 颜色 | 200ms |
| Checkbox check | 勾画路径动画 | 200ms |
| Card hover | 阴影增强 + 1px 抬高 | 200ms |
| Drag start | 缩放 1.05 + 阴影 | 150ms |
| Drop | 弹性 1.1→1.0 | 300ms |

### 6. 状态过渡（State Transitions）

#### 6.1 加载 → 内容

```tsx
<AnimatePresence mode="wait">
  {loading ? (
    <motion.div
      key="skeleton"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <Skeleton />
    </motion.div>
  ) : (
    <motion.div
      key="content"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <Content />
    </motion.div>
  )}
</AnimatePresence>
```

#### 6.2 错误 → 重试

```tsx
<motion.div
  animate={error ? { x: [0, -4, 4, -4, 4, 0] } : {}}
  transition={{ duration: 0.4 }}
>
  {error ? '请重试' : '提交'}
</motion.div>
```

### 7. 动效 Token

把所有动效集中到 token，跨页面统一：

```ts
// motion.ts
export const motion = {
  duration: {
    instant: 100,
    fast: 150,
    normal: 200,
    slow: 300,
    slower: 500,
  },
  easing: {
    out: [0.16, 1, 0.3, 1],
    in: [0.7, 0, 0.84, 0],
    inOut: [0.65, 0, 0.35, 1],
    spring: { type: 'spring', stiffness: 260, damping: 20 },
  },
  stagger: {
    fast: 0.03,
    normal: 0.05,
    slow: 0.1,
  },
}
```

```tsx
<motion.div
  transition={{ duration: motion.duration.normal, ease: motion.easing.out }}
/>
```

## 5 个高级感案例

### 1. Stripe style 卡片聚焦

```tsx
<motion.div
  whileHover={{ y: -2 }}
  transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
  className="rounded-xl border bg-white p-6 shadow-sm hover:shadow-md"
>
  ...
</motion.div>
```

### 2. Linear style 模态

```tsx
<AnimatePresence>
  {open && (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-xl bg-zinc-900 p-6 shadow-2xl"
    >
      ...模态内容
    </motion.div>
  )}
</AnimatePresence>
```

### 3. Apple style 列表进入

```tsx
const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.1,
    },
  },
}
const item = {
  hidden: { opacity: 0, y: 20, filter: 'blur(4px)' },
  show: { opacity: 1, y: 0, filter: 'blur(0px)' },
}

<motion.div variants={container} initial="hidden" animate="show">
  {items.map(i => (
    <motion.div key={i.id} variants={item}>{i.name}</motion.div>
  ))}
</motion.div>
```

### 4. Apple style 数字滚动

```tsx
import { useMotionValue, useTransform, animate } from 'framer-motion'

function Counter({ from, to }: { from: number; to: number }) {
  const count = useMotionValue(from)
  const rounded = useTransform(count, latest => Math.round(latest))

  useEffect(() => {
    const controls = animate(count, to, { duration: 1.5, ease: 'easeOut' })
    return controls.stop
  }, [to])

  return <motion.span>{rounded}</motion.span>
}
```

### 5. Stripe style 加载

```tsx
function Skeleton() {
  return (
    <motion.div
      animate={{ opacity: [0.5, 1, 0.5] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
      className="h-4 rounded bg-zinc-200"
    />
  )
}
```

## 性能清单

```markdown
- [ ] 动效属性只用 transform / opacity / filter
- [ ] 避免 layout 属性（width/height/top）
- [ ] prefers-reduced-motion 适配
- [ ] 移动端简化动效
- [ ] 列表 1000+ 项禁用复杂动效
- [ ] 60fps 持续（DevTools Performance 检测）
```

## 反模式

- ❌ 动画时长 > 1s（用户失去耐心）
- ❌ 一次性动画多个属性（抖动）
- ❌ 装饰性动画（无状态意义）
- ❌ 缓动函数默认 `ease`（廉价）
- ❌ 列表项同时动画（应该 stagger）
- ❌ 触发 layout 属性的动画
- ❌ 忽略 `prefers-reduced-motion`

## 配合

- 配合 `motion` 走 Framer Motion 实战
- 配合 `frontend-pro` 走组件设计
- 配合 `tailwind-pro` 验证样式
- 配合 `web-design-guidelines` 走 12 大类审查
