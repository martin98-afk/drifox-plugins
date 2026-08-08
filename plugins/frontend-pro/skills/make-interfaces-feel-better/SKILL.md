---
name: make-interfaces-feel-better
description: UI 细节打磨 — 对齐 / 阴影 / 间距 / 圆角 / 字体基线 / 排版节奏的精细调整，让界面从"能用"到"高级"。源自 jakubkrehel/make-interfaces-feel-better。触发关键词：界面打磨、细节优化、UI 细节、精致、高级感、动效、refine、polish、pixel-perfect、make it feel better。
---

# Make Interfaces Feel Better — UI 细节打磨

源自 [jakubkrehel/make-interfaces-feel-better](https://github.com/jakubkrehel/make-interfaces-feel-better)，helloianneo/awesome-claude-code-skills **强推**。

本技能为 AI 提供"像素级"UI 细节打磨方法论，专注于让界面**感觉更好**而非只是能用。

## 何时触发

- 用户："让界面更精致"、"提升 UI 质感"、"细节优化"
- 用户："感觉不够"、"不高级"、"看起来像 demo"
- AI 完成 UI 后自检"打磨度"

## 五大打磨维度

### 1. 对齐（Alignment）

#### 1.1 字体基线对齐

```css
/* ❌ 文字与图标错位 */
<button class="flex items-center gap-2">
  <Icon class="self-start" />
  <span>Click</span>
</button>

/* ✅ 真正居中（基线对齐） */
<button class="inline-flex items-baseline gap-2">
  <Icon class="translate-y-0.5" />
  <span>Click</span>
</button>
```

#### 1.2 视觉对齐 ≠ 几何对齐

小图标要**视觉居中**而非几何居中（因为 descender/ascender 不对称）。

```css
/* 24px 图标在 24px 容器中视觉偏上 1-2px */
.icon { transform: translateY(-1px); }
```

#### 1.3 父子间距 < 兄弟间距

```
Label
  Input      ← 4-8px 间隔（紧密）

Label              ← 24-32px 间隔（松散）
Input
```

#### 1.4 网格对齐

用 4px / 8px 网格：
- 4px grid：精细（小图标、按钮内边距）
- 8px grid：标准（卡片、间距）
- 12 列 grid：响应式布局

### 2. 阴影（Shadow）

#### 2.1 阴影不对称

```css
/* ❌ 阴影均匀（廉价） */
box-shadow: 0 0 8px rgba(0,0,0,0.1);

/* ✅ y 偏移 + 模糊 + 扩散（高级） */
box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1),
            0 2px 4px -2px rgba(0,0,0,0.1);
```

#### 2.2 阴影颜色感知

```css
/* ❌ 黑色阴影（生硬） */
box-shadow: 0 4px 6px rgba(0,0,0,0.1);

/* ✅ 冷调阴影（柔和） */
box-shadow: 0 4px 6px rgba(99,102,241,0.1);

/* ✅ 暗色模式阴影减弱 */
@media (prefers-color-scheme: dark) {
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
```

#### 2.3 阴影层级表

| 名称 | 用途 | Tailwind |
|------|------|---------|
| xs | 按钮焦点 | `shadow-xs` |
| sm | 卡片默认 | `shadow-sm` |
| md | 悬浮卡片 | `shadow-md` |
| lg | 弹窗 | `shadow-lg` |
| xl | 模态 | `shadow-xl` |
| 2xl | 抽屉 | `shadow-2xl` |

### 3. 间距（Spacing）

#### 3.1 8 倍数与微调

```css
/* 推荐基础 */
4px  / 8px  / 12px / 16px / 24px / 32px / 48px / 64px / 96px

/* ❌ 混用多种间距单位 */
padding: 7px 13px 11px 9px;

/* ✅ 严格 8 倍数 */
padding: 8px 16px;
```

#### 3.2 间距比例

| 元素关系 | 间距建议 |
|---------|---------|
| 标签-输入框 | 4-8px |
| 段落-段落 | 1.5em |
| 章节-章节 | 2-3em |
| 区块-区块 | 4-6em |
| 容器内边距 | 16-32px |

#### 3.3 容器内边距 vs 容器间距

```
容器 A
[      16px 内边距      ]
[      内容              ]
                       32px 容器间距
容器 B
[      16px 内边距      ]
```

容器内边距 < 容器间距（让"呼吸"感更强）。

### 4. 圆角（Border Radius）

#### 4.1 圆角公式

| 元素 | 推荐 |
|------|------|
| 按钮 | 6-8px |
| 卡片 | 12-16px |
| 模态 | 16-24px |
| 头像 | 9999px |
| 输入框 | 6-8px |
| 标签 | 4-6px |

#### 4.2 内嵌圆角

```css
/* 卡片圆角 12px → 内嵌元素圆角应该更小 */
.card { border-radius: 12px; }
.card .badge { border-radius: 6px; } /* 内嵌 = 父圆角 - 6 */
.card .button { border-radius: 8px; }
```

#### 4.3 圆角与高度的视觉关系

```
24px 圆角 + 32px 高度 = 完美
24px 圆角 + 16px 高度 = 圆角过大（看起来像椭圆）
```

#### 4.4 圆角 vs 形状

小元素（按钮、输入）用小圆角，大元素（卡片、模态）用大圆角。

### 5. 字体基线（Typography）

#### 5.1 字号阶梯（严格比例）

```css
/* 1.2 紧凑 */
12 / 14 / 17 / 20 / 24 / 29 / 35 / 42

/* 1.25 普通 */
12 / 15 / 19 / 24 / 30 / 37 / 47 / 59

/* 1.333 经典 */
12 / 16 / 21 / 28 / 37 / 50 / 67 / 89

/* 1.5 宽松 */
12 / 18 / 27 / 41 / 61 / 92 / 138 / 207
```

#### 5.2 字重阶梯

| 用途 | 字重 |
|------|------|
| 正文 | 400 |
| 强调 | 500 |
| 标题 | 600-700 |
| 大型标题 | 800 |

#### 5.3 行高（leading）

| 元素 | 行高 |
|------|------|
| 标题 | 1.1-1.3 |
| 正文 | 1.5-1.7 |
| 大段文字 | 1.6-1.8 |
| 列表 | 1.4-1.5 |

#### 5.4 字距（tracking）

| 元素 | 字距 |
|------|------|
| 正文 | 0 |
| 标题 | -0.02em |
| 大写 | 0.05em |
| 中文 | 0.02-0.05em |

#### 5.5 字体渲染

```css
body {
  font-feature-settings: "ss01", "cv01"; /* 风格化 */
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}
```

## 完整打磨 Checklist

```markdown
## UI 打磨 Checklist

### 对齐
- [ ] 所有图标与文字 baseline 对齐
- [ ] 父子间距 < 兄弟间距
- [ ] 网格对齐（4px / 8px）

### 阴影
- [ ] 阴影不对称（y 偏移 + 模糊）
- [ ] 阴影有色彩倾向（冷调）
- [ ] 暗色模式阴影减弱

### 间距
- [ ] 严格 8 倍数
- [ ] 容器内边距 < 容器间距
- [ ] 段落间距 1.5em

### 圆角
- [ ] 内嵌圆角 < 父圆角
- [ ] 圆角与高度匹配
- [ ] 全站 ≤ 3 档圆角

### 字体
- [ ] 字阶严格（1.2 / 1.25 / 1.333 / 1.5）
- [ ] 字重阶梯清晰
- [ ] 行高按元素类型
- [ ] 标题字距 -0.02em
```

## 反模式

- ❌ 整站统一圆角（应该有 2-3 档）
- ❌ 阴影颜色纯黑（应该有冷调倾向）
- ❌ 字阶自定义（应该用 1.2 / 1.25 / 1.333 等经典比例）
- ❌ 间距 1px 调整（应该用 4px / 8px 整数倍）
- ❌ 删除 focus 环（永远不会"高级"）

## 配合

- 配合 `mobile-first` 反推（看 mobile 桌面是否一致）
- 配合 `tailwind-pro` 应用 Tailwind v4 token
- 配合 `web-design-guidelines` 跑 12 大类审查
- 配合 `web-design-engineer` 视觉验证
