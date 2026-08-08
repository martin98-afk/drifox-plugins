---
name: motion
description: Framer Motion（Motion）React 动画 — 手势 / 滚动 / 弹性 / 布局动画 / AnimatePresence 模式。源自 jezweb/claude-skills。触发关键词：framer motion、motion、react 动画、gesture、spring、layout 动画、AnimatePresence、useScroll、useMotionValue、useTransform。
---

# Motion 技能 — Framer Motion / React 动画

源自 [jezweb/claude-skills](https://github.com/jezweb/claude-skills) 的 motion skill，helloianneo/awesome-claude-code-skills **强推**。

本技能为 AI 提供 Framer Motion / Motion 库的标准动画模式。

## 何时触发

- "加个 React 动画"、"用 Framer Motion"
- "卡片悬浮"、"按钮点击反馈"
- "页面切换动画"、"路由过渡"
- "滚动动画"、"视差"
- "拖动 / 手势"

## 核心 API

### 1. motion 组件

```tsx
import { motion } from 'framer-motion'

<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  exit={{ opacity: 0, y: -20 }}
  transition={{ duration: 0.3, ease: 'easeOut' }}
>
  内容
</motion.div>
```

### 2. 常用动画属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `initial` | object | 初始状态 |
| `animate` | object | 目标状态 |
| `exit` | object | 卸载状态（需 AnimatePresence） |
| `transition` | object | 过渡配置 |
| `whileHover` | object | 悬浮态 |
| `whileTap` | object | 按下态 |
| `whileDrag` | object | 拖动态 |
| `whileFocus` | object | 聚焦态 |
| `whileInView` | object | 进入视口 |
| `variants` | object | 命名变体 |

### 3. transition 配置

```tsx
// 缓动（推荐）
transition={{
  duration: 0.3,
  ease: [0.16, 1, 0.3, 1]  // ease-out-expo
}}

// 弹簧（弹性）
transition={{
  type: 'spring',
  stiffness: 260,
  damping: 20,
  mass: 1
}}

// 视图
transition={{ duration: 0.5, ease: 'linear' }}
```

| 缓动 | 用途 |
|------|------|
| `easeOut` | 入场（短→长） |
| `easeIn` | 出场（长→短） |
| `easeInOut` | 双向（对称） |
| `[0.16, 1, 0.3, 1]` | ease-out-expo（高级） |
| `[0.65, 0, 0.35, 1]` | ease-in-out-cubic |

### 4. Variants（命名变体）

```tsx
const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,  // 子项错开 100ms
      delayChildren: 0.2
    }
  }
}

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
}

<motion.div variants={container} initial="hidden" animate="show">
  {items.map(i => (
    <motion.div key={i.id} variants={item}>{i.name}</motion.div>
  ))}
</motion.div>
```

## 5 大实战模式

### 1. AnimatePresence（mount/unmount 动画）

```tsx
import { AnimatePresence, motion } from 'framer-motion'

<AnimatePresence mode="wait">
  {isOpen && (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    >
      模态内容
    </motion.div>
  )}
</AnimatePresence>
```

**use cases**：
- 模态对话框
- 通知 toast
- 路由切换
- 列表项增删

### 2. 布局动画（layout）

```tsx
<motion.div layout transition={{ type: 'spring', stiffness: 300, damping: 30 }}>
  重排列表项
</motion.div>

// 复杂动画共享元素
<motion.div
  layoutId="shared-card"
  transition={{ type: 'spring' }}
/>
```

**use cases**：
- 卡片重排
- 列表过滤
- 共享元素动画（hero→详情）
- 抽屉展开

### 3. 手势（Gestures）

```tsx
<motion.div
  drag="x"
  dragConstraints={{ left: -100, right: 0 }}
  dragElastic={0.2}
  onDragEnd={(e, info) => {
    if (info.offset.x < -50) close()
  }}
  whileDrag={{ scale: 1.05 }}
>
  拖动我
</motion.div>
```

**use cases**：
- 滑动删除
- 抽屉拖动
- 卡片拖拽重排
- 图片轮播

### 4. 滚动动画（Scroll）

```tsx
import { useScroll, useMotionValueEvent, useTransform } from 'framer-motion'

function Component() {
  const { scrollY } = useScroll()
  const y = useTransform(scrollY, [0, 500], [0, -100])
  const opacity = useTransform(scrollY, [0, 300], [1, 0])

  return <motion.div style={{ y, opacity }}>滚动效果</motion.div>
}
```

**use cases**：
- 视差
- 顶部导航透明度
- 滚动加载
- 进度条

### 5. 进入视口（whileInView）

```tsx
<motion.div
  initial={{ opacity: 0, y: 50 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: '-100px' }}
  transition={{ duration: 0.5 }}
>
  滚动到这里才显示
</motion.div>
```

**use cases**：
- 滚动触发动画
- 懒加载内容
- 营销页 hero 文字

## 性能优化

### 1. transform / opacity 优先

```tsx
// ✅ 性能好（GPU 加速）
animate={{ x: 100, scale: 1.1, opacity: 0.5 }}

// ❌ 触发 reflow
animate={{ width: 200, height: 100, top: 50 }}
```

### 2. layout 动画谨慎使用

```tsx
// ❌ 整树 layout 动画很慢
<motion.div layout>...</motion.div>

// ✅ 局部 layout
<motion.div layout="position">...</motion.div>
```

### 3. 减少动效

```tsx
<motion.div
  initial={{ opacity: 0 }}
  animate={{ opacity: 1 }}
  transition={{ duration: 0.3 }}
  // 移动端关闭
  whileInView={{ opacity: 1 }}
  viewport={{ margin: '-50px' }}
/>
```

```css
/* 全局响应 prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

## 反模式

- ❌ 动画时长 > 500ms（用户开始焦虑）
- ❌ 同时动画多个属性（容易掉帧）
- ❌ 触发 layout 属性的动画（width/height/top）
- ❌ 忽略 `prefers-reduced-motion`
- ❌ 路由切换无过渡（生硬）
- ❌ 列表项同时动画（应该是 stagger）
- ❌ 删除元素无 exit 动画（突然消失）

## 实战模板

### 卡片悬浮

```tsx
<motion.div
  whileHover={{ y: -4, scale: 1.02 }}
  transition={{ type: 'spring', stiffness: 400, damping: 25 }}
  className="card"
>
  卡片
</motion.div>
```

### 列表错开

```tsx
const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05 } }
}
const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
}

<motion.ul variants={container} initial="hidden" animate="show">
  {items.map(i => (
    <motion.li key={i.id} variants={item}>{i.name}</motion.li>
  ))}
</motion.ul>
```

### 页面切换

```tsx
<AnimatePresence mode="wait">
  <motion.main
    key={router.pathname}
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -20 }}
    transition={{ duration: 0.3 }}
  >
    <Component {...pageProps} />
  </motion.main>
</AnimatePresence>
```

### 滑动删除

```tsx
<motion.div
  drag="x"
  dragConstraints={{ left: -200, right: 0 }}
  dragElastic={0.1}
  onDragEnd={(_, info) => {
    if (info.offset.x < -150) handleDelete()
  }}
>
  滑动我
</motion.div>
```

## 配合

- 配合 `frontend-pro` 走组件设计
- 配合 `tailwind-pro` 验证样式
- 配合 `react-pro` 40+ 性能规则
- 配合 `animation-systems` 走 Stripe/Linear 级别动效
