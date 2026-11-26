---
name: design-system
description: "Token 架构、组件规格与幻灯片生成。三层 token（原始→语义→组件）、CSS 变量、间距与字体尺度、组件规格、策略型幻灯片。做设计 token、系统化设计、品牌合规演示时使用。"
argument-hint: "[组件或 token]"
version: 1.0.0
license: MIT
metadata:
  author: claudekit
  upstream: nextlevelbuilder/ui-ux-pro-max-skill
  localized: zh-CN
---

# Design System

Token 架构、组件规格、系统化设计与幻灯片生成。

## 什么时候用

- 创建设计 token
- 定义组件状态
- 搭建 CSS 变量体系
- 间距与字体尺度
- 设计到代码的交付
- Tailwind 主题配置
- **幻灯片/演示生成**

## Token 架构

加载 `references/token-architecture.md`。

### 三层结构

```
Primitive（原始值）
       ↓
Semantic（用途别名）
       ↓
Component（组件专用）
```

**示例：**

```css
/* Primitive */
--color-blue-600: #2563EB;
/* Semantic */
--color-primary: var(--color-blue-600);
/* Component */
--button-bg: var(--color-primary);
```

## 脚本路径

本技能与其 `references/` 里的脚本路径，相对于本 SKILL.md 所在目录，不是项目目录：`scripts/<file>` 是本技能自己的 `scripts/`，`../<skill>/scripts/<file>` 是同级子技能的。用这个目录拼出完整路径，工作目录保持在项目根：脚本按项目根读写 `docs/brand-guidelines.md`、`assets/design-tokens.json`、`src/` 这些文件。

## 快速开始

**生成 token：**

```bash
node scripts/generate-tokens.cjs --config tokens.json -o tokens.css
```

**校验用法：**

```bash
node scripts/validate-tokens.cjs --dir src/
```

## 参考库

| 主题 | 文件 |
|------|------|
| Token 架构 | `references/token-architecture.md` |
| 原始 token | `references/primitive-tokens.md` |
| 语义 token | `references/semantic-tokens.md` |
| 组件 token | `references/component-tokens.md` |
| 组件规格 | `references/component-specs.md` |
| 状态与变体 | `references/states-and-variants.md` |
| Tailwind 集成 | `references/tailwind-integration.md` |

## 组件规格范式

| 属性 | 默认 | 悬停 | 按下 | 禁用 |
|------|------|------|------|------|
| 背景 | primary | primary-dark | primary-darker | muted |
| 文字 | white | white | white | muted-fg |
| 边框 | none | none | none | muted-border |
| 阴影 | sm | md | none | none |

## 脚本

| 脚本 | 用途 |
|------|------|
| `generate-tokens.cjs` | 从 JSON token 配置生成 CSS |
| `validate-tokens.cjs` | 检查代码里的硬编码值 |
| `search-slides.py` | BM25 搜索 + 上下文感知建议 |
| `slide-token-validator.py` | 校验幻灯片 HTML 的 token 合规 |
| `fetch-background.py` | 从 Pexels/Unsplash 取图 |

## 模板

| 模板 | 用途 |
|------|------|
| `design-tokens-starter.json` | 带三层结构的起步 JSON |

## 集成

- **与 brand**：从品牌配色/字体里提取原始 token。
- **与 ui-styling**：组件 token → Tailwind 配置。

## 幻灯片系统

用设计 token + Chart.js + 上下文决策系统做品牌合规的演示。

### 唯一真相

| 文件 | 用途 |
|------|------|
| `docs/brand-guidelines.md` | 品牌识别、语气、配色 |
| `assets/design-tokens.json` | token 定义（原始→语义→组件） |
| `assets/design-tokens.css` | CSS 变量（幻灯片里 import） |
| `assets/css/slide-animations.css` | CSS 动画库 |

### 幻灯片搜索（BM25）

```bash
# 基础搜索（自动判断 domain）
python scripts/search-slides.py "investor pitch"
# 指定 domain
python scripts/search-slides.py "problem agitation" -d copy
python scripts/search-slides.py "revenue growth" -d chart
# 上下文搜索
python scripts/search-slides.py "problem slide" --context --position 2 --total 9
python scripts/search-slides.py "cta" --context --position 9 --prev-emotion frustration
```

### 决策数据表

| 文件 | 用途 |
|------|------|
| `data/slide-strategies.csv` | 15 种演示结构 + 情绪曲线 + sparkline 节拍 |
| `data/slide-layouts.csv` | 25 种版式 + 组件变体 + 动画 |
| `data/slide-layout-logic.csv` | 目标 → 版式 + break_pattern 标记 |
| `data/slide-typography.csv` | 内容类型 → 字体尺度 |
| `data/slide-color-logic.csv` | 情绪 → 配色处理 |
| `data/slide-backgrounds.csv` | 页型 → 图片类别（Pexels/Unsplash） |
| `data/slide-copy.csv` | 25 个文案公式（PAS、AIDA、FAB） |
| `data/slide-charts.csv` | 25 类图表及 Chart.js 配置 |

### 上下文决策流程

```
1. 解析目标与上下文
        ↓
2. 查 slide-strategies.csv → 得到策略 + 情绪节拍
        ↓
3. 逐页：
   a. 查 slide-layout-logic.csv → 版式 + break_pattern
   b. 查 slide-typography.csv → 字体尺度
   c. 查 slide-color-logic.csv → 配色处理
   d. 查 slide-backgrounds.csv → 需要时取图
   e. 套 slide-animations.css 里的动画类
        ↓
4. 用设计 token 生成 HTML
        ↓
5. 用 slide-token-validator.py 校验
```

### 打断范式（Duarte Sparkline）

高级演示在情绪之间交替，维持吸引力：

```
"What Is"（挫败）↔ "What Could Be"（希望）
```

系统在 1/3 与 2/3 位置计算打断点。

### 幻灯片硬要求

**每一页都必须：**

1. import `assets/design-tokens.css`，它是唯一真相
2. 用 CSS 变量：`var(--color-primary)`、`var(--slide-bg)` 等
3. 图表用 Chart.js（不要只用 CSS 画条）
4. 带导航（键盘方向键、点击、进度条）
5. 内容居中
6. 服务于说服与转化

## 本地化说明

本文件由英文原文译写为中文。`.cjs` 脚本需要 Node，`.py` 脚本需要 Python 3（`fetch-background.py` 还要 Pexels/Unsplash 的 key）。对应运行时缺失时，按 `references/` 的规则人工生成与校验，并在交付说明里注明脚本未运行。