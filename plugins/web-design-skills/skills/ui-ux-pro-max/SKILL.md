---
name: ui-ux-pro-max
description: 视觉层级 × 色彩心理学 × 交互模式 — UI/UX 设计方法论，让界面从"AI 味"到"高级感"。源自 nextlevelbuilder/ui-ux-pro-max-skill。触发关键词：ui ux、视觉层级、色彩心理学、交互模式、UI 设计、UX 设计、ui ux pro、visual hierarchy、interaction design。
---

# UI-UX-Pro-Max — 视觉层级 × 色彩心理学 × 交互模式

源自 [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)，helloianneo/awesome-claude-code-skills **必装 Top 10** 第 4 名。

本技能为 AI 提供让 UI "摆脱 AI 味"的设计方法论——视觉层级、色彩心理学、交互模式三件套。

## 何时触发

- "提升 UI 质量"、"减少 AI 味"
- "视觉层级"、"色彩搭配"
- "交互模式"、"动画节奏"
- AI 写 UI 时自动注入

## 三大模块

### 模块 1：视觉层级（Visual Hierarchy）

#### 1.1 5 大视觉权重

| 权重 | 用途 | 元素 |
|------|------|------|
| 1（极弱） | 装饰、面包屑 | 灰色小字、辅助元素 |
| 2（弱） | 次要信息 | 副标题、placeholder |
| 3（中） | 正文 | 段落、卡片标题 |
| 4（强） | 重要信息 | 关键数字、CTA |
| 5（极强） | 焦点 | Hero 标题、CTA 主按钮 |

#### 1.2 视觉层级 5 要素

```
1. 尺寸（Size）          : 大小对比
2. 颜色（Color）         : 饱和度对比
3. 间距（Spacing）       : 层级关系
4. 字重（Weight）        : 重要性
5. 位置（Position）      : 注意力
```

##### 1.2.1 尺寸法则

```
Hero 标题：48-72px
页面标题：32-40px
卡片标题：18-24px
正文：14-16px
辅助：12-14px
```

##### 1.2.2 颜色对比

```css
/* ❌ 灰度对比不够 */
.text-primary { color: #333; }
.text-muted { color: #555; }

/* ✅ 强对比 */
.text-primary { color: #000; }   /* 100% */
.text-secondary { color: #555; } /* 60% */
.text-muted { color: #888; }     /* 40% */
.text-disabled { color: #ccc; }  /* 20% */
```

##### 1.2.3 字重对比

```css
/* ❌ 字重差异小 */
.title { font-weight: 500; }
.body { font-weight: 400; }  /* 差距 100 */

/* ✅ 字重阶梯 */
.hero { font-weight: 800; }
.title { font-weight: 700; }
.subtitle { font-weight: 600; }
.body { font-weight: 400; }
.caption { font-weight: 300; }
```

#### 1.3 信息层级

```
# 一级（最重要）
  唯一 CTA，唯一价值

# 二级（重要）
  章节标题，核心功能

# 三级（次要）
  描述，解释

# 四级（辅助）
  元数据，时间戳

# 五级（极弱）
  装饰，分割线
```

### 模块 2：色彩心理学（Color Psychology）

#### 2.1 色彩情绪映射

| 颜色 | 情绪 | 适用场景 |
|------|------|---------|
| 蓝 | 信任、专业、冷静 | SaaS、金融、企业 |
| 绿 | 增长、自然、健康 | 环保、医疗、金融 |
| 红 | 紧急、激情、警告 | 错误、激进、电商 |
| 黄 | 乐观、警告、年轻 | 儿童、警告、活力 |
| 紫 | 奢华、神秘、创意 | 美妆、游戏、奢侈品 |
| 橙 | 活力、友好、行动 | 社交、电商、健身 |
| 黑 | 高级、严肃、神秘 | 奢侈品、专业工具 |
| 白 | 简约、纯净、空间 | 极简、医疗、SaaS |

#### 2.2 配色策略

##### 2.2.1 60-30-10 法则

```
60%  主色（背景、中性）
30%  辅色（标题、卡片）
10%  点缀（CTA、强调）
```

##### 2.2.2 单一主色 + 中性

```css
:root {
  --color-brand: #0066FF;        /* 主色 10% */
  --color-bg: #FAFAFA;           /* 背景 60% */
  --color-surface: #FFFFFF;      /* 卡片 30% */
  --color-text: #0A0A0A;         /* 文本 */
  --color-text-muted: #6B7280;   /* 次文本 */
}
```

##### 2.2.3 OKLCH 色彩空间

```css
/* 高级感的色彩 */
:root {
  --color-primary: oklch(0.65 0.21 260);   /* 蓝 */
  --color-success: oklch(0.7 0.17 145);    /* 绿 */
  --color-warning: oklch(0.78 0.16 80);    /* 黄 */
  --color-danger: oklch(0.65 0.25 25);     /* 红 */
}
```

#### 2.3 色彩对比度

| 关系 | 比例 | 适用 |
|------|------|------|
| 极强 | 7:1 | Hero 标题 + 背景 |
| 强 | 4.5:1 | 正文 + 背景（WCAG AA） |
| 中 | 3:1 | 大字 + 背景 |
| 弱 | 1.5:1 | 装饰元素 |
| 极弱 | 1:1 | 不可访问（避免） |

#### 2.4 暗色模式

```css
/* 暗色模式不是反色，是降饱和 */
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: oklch(0.15 0 0);           /* 不是纯黑 */
    --color-surface: oklch(0.2 0 0);       /* 抬升 */
    --color-text: oklch(0.95 0 0);         /* 不是纯白 */
    --color-text-muted: oklch(0.7 0 0);
  }
}
```

### 模块 3：交互模式（Interaction Patterns）

#### 3.1 9 大基本交互

| 交互 | 触发 | 反馈 |
|------|------|------|
| 点击 | 鼠标按下 | 缩放 0.95 + 颜色变化 |
| 悬浮 | 鼠标进入 | 抬高 2px + 颜色变化 |
| 聚焦 | 键盘 Tab | 2px 轮廓 + 背景色 |
| 拖动 | 鼠标按下移动 | 缩放 1.05 + 阴影 |
| 滑动 | 水平拖动 | 跟随手指 + 阈值触发 |
| 切换 | 点击开关 | 滑块动画 + 颜色过渡 |
| 选中 | 单选/多选 | 边框色 + 勾选动画 |
| 加载 | 异步等待 | 骨架 / spinner |
| 错误 | 异常 | 抖动 + 红色 + 文本 |

#### 3.2 反馈时长

| 反馈 | 时长 |
|------|------|
| 按钮点击 | 100ms |
| 悬浮 | 150ms |
| 状态变化 | 200-300ms |
| 页面切换 | 300-400ms |
| 模态出现 | 200ms |
| 列表进入 | 错开 50ms |

#### 3.3 4 个黄金交互原则

##### 3.3.1 反馈优先

```tsx
// ❌ 点击无反馈
<button onClick={save}>保存</button>

// ✅ 点击有反馈
<button onClick={save} className="active:scale-95 transition">
  保存
</button>
```

##### 3.3.2 状态可见

```tsx
// ❌ 状态隐藏
<Uploader />

// ✅ 状态可见
<Uploader>
  上传中：45% · 剩余 12 秒
</Uploader>
```

##### 3.3.3 错误友好

```tsx
// ❌ 错误生硬
"Error: 500"

// ✅ 错误友好
"上传失败，请检查网络后重试"
[重试按钮]
```

##### 3.3.4 容错设计

```tsx
// ❌ 一次性操作
<button onClick={deleteAll}>删除全部</button>

// ✅ 可撤销
<button onClick={deleteAll}>删除全部</button>
{lastDeleted && <Toast>已删除 <button onClick={undo}>撤销</button></Toast>}
```

## 8 个 AI 味反模式

### 1. 全屏渐变背景

```css
/* ❌ AI 味 */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* ✅ 高级感 */
background: #FAFAFA;
```

### 2. 紫色光晕

```css
/* ❌ */
box-shadow: 0 0 80px rgba(124, 58, 237, 0.5);

/* ✅ 克制阴影 */
box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
```

### 3. 彩虹色

```css
/* ❌ */
.btn-primary { background: linear-gradient(90deg, red, orange, yellow, green, blue, indigo, violet); }

/* ✅ */
.btn-primary { background: #0066FF; }
```

### 4. 动画滥用

```tsx
// ❌
<motion.div animate={{ rotate: [0, 360] }} transition={{ repeat: Infinity }} />

// ✅ 静态或克制
<motion.div animate={{ opacity: 1 }} transition={{ duration: 0.3 }} />
```

### 5. 字号过大

```css
/* ❌ */
h1 { font-size: 96px; }

/* ✅ */
h1 { font-size: 48px; }
```

### 6. 圆角过大

```css
/* ❌ */
.card { border-radius: 32px; }

/* ✅ */
.card { border-radius: 12px; }
```

### 7. 装饰大于内容

```tsx
// ❌ 大量装饰
<div className="bg-gradient-to-br from-purple-500 to-pink-500 p-8">
  <div className="bg-white/95 backdrop-blur p-6">
    <h1>标题</h1>
  </div>
</div>

// ✅ 内容为主
<article className="p-6">
  <h1>标题</h1>
</article>
```

### 8. 信息密度过低

```tsx
// ❌ 太多留白
<div className="p-16">
  <h1>单个标题</h1>
</div>

// ✅ 合理信息密度
<div className="p-6 space-y-4">
  <h1>标题</h1>
  <p>正文段落</p>
  <button>CTA</button>
</div>
```

## 完整设计 Checklist

```markdown
## 视觉层级
- [ ] 5 大权重清晰
- [ ] Hero 标题 48-72px
- [ ] 字重阶梯清晰
- [ ] 颜色对比 ≥ 4.5:1

## 色彩
- [ ] 60-30-10 法则
- [ ] 主色 ≤ 1 个
- [ ] 暗色模式降饱和
- [ ] OKLCH 色彩空间

## 交互
- [ ] 所有交互有反馈
- [ ] 状态可见
- [ ] 错误友好
- [ ] 关键操作可撤销
- [ ] prefers-reduced-motion
```

## 配合

- 配合 `web-design-guidelines` 走 12 大类审查
- 配合 `make-interfaces-feel-better` 走细节打磨
- 配合 `motion` / `animation-systems` 走动效
- 配合 `tailwind-pro` 验证样式
- 配合 `frontend-pro` 走组件设计
