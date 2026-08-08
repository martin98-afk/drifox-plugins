---
name: web-design-guidelines
description: 对照 Vercel Labs 100+ UI 最佳实践审查前端代码，找出对齐 / 阴影 / 间距 / 圆角 / 字体 / 色彩 / 动效 / 可访问性 / 性能 / 响应式 / 暗色模式等细节问题。触发关键词：UI 审查、设计审查、UI 最佳实践、设计规范、design review、UI guidelines、UI 规则、design system、UI 检查。
---

# Web Design Guidelines 技能 — Vercel Labs 100+ UI 最佳实践

源自 [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills)，helloianneo/awesome-claude-code-skills **必装 Top 10** 第 3 名。本技能为 AI 提供对照审查 UI 细节问题的能力。

## 何时触发

- 用户："审查 UI"、"UI 审查"、"检查设计问题"
- 用户："为什么看起来不对"、"不够精致"
- 用户："对照最佳实践"、"design review"
- AI 完成 UI 后自检

## 12 大类审查规则

### 1. 字体（Typography）

| 规则 | 描述 |
|------|------|
| 1.1 字体形态 | 字体锐利 vs 圆润（阅读类用 Inter，SaaS 用 GT America） |
| 1.2 字重对比 | 标题 600-700 + 正文 400，过渡自然 |
| 1.3 字距 | 标题 -0.02em，正文 0，大写 +0.05em |
| 1.4 行高 | 标题 1.1-1.3，正文 1.5-1.7 |
| 1.5 行长 | 50-75 字符（中文 30-50） |
| 1.6 字体阶梯 | 严格 1.2 / 1.25 / 1.333 / 1.5 / 1.618 |
| 1.7 字体加载 | `next/font` 自托管，避免 FOIT |

### 2. 色彩（Color）

| 规则 | 描述 |
|------|------|
| 2.1 主色单一 | 1 个主色 + N 个中性色，避免彩虹 |
| 2.2 中性色阶梯 | 9 阶灰阶（50-900） |
| 2.3 语义色 | success / warning / danger / info 各 1 个 |
| 2.4 对比度 | 正 ≥ 4.5:1（AA），大文本 ≥ 3:1 |
| 2.5 暗色模式 | 不用纯黑，用 zinc-900 / neutral-900 |
| 2.6 色彩空间 | 优先 OKLCH，渐进降级 hex |

### 3. 间距（Spacing）

| 规则 | 描述 |
|------|------|
| 3.1 8 倍数 | 4/8/12/16/24/32/48/64/96 |
| 3.2 父子间距 < 兄弟间距 | 0.6-0.8 倍 |
| 3.3 段落间距 | 1.5-2 倍行高 |
| 3.4 区块间距 | 64-128px |
| 3.5 容器内边距 | 16-32px |
| 3.6 避免 1px 边界 | 用 2px |

### 4. 圆角（Border Radius）

| 规则 | 描述 |
|------|------|
| 4.1 圆角统一 | 4/8/12/16/full，最多 3 档 |
| 4.2 卡片圆角 | 8-16px |
| 4.3 按钮圆角 | 6-8px（小）/ 9999px（pill） |
| 4.4 头像圆角 | full |
| 4.5 圆角与高度 | 圆角 ≤ 高度 |

### 5. 阴影（Shadow）

| 规则 | 描述 |
|------|------|
| 5.1 阴影层级 | 3-4 档（xs/sm/md/lg） |
| 5.2 阴影方向 | 向下 1-2px，避免向上 |
| 5.3 阴影模糊 | 2-3 倍 X 偏移 |
| 5.4 阴影色 | 低饱和度（rgba）或 token（shadow） |
| 5.5 暗色模式 | 阴影减弱，改用 backdrop-blur |

### 6. 对齐（Alignment）

| 规则 | 描述 |
|------|------|
| 6.1 基线对齐 | 文字与图标 baseline 对齐 |
| 6.2 网格对齐 | 4/8/12 列网格 |
| 6.3 居中陷阱 | 慎用 text-center，flex 优先 |
| 6.4 视觉对齐 | 元素中心 vs 视觉中心（光学对齐） |
| 6.5 关联性 | 关联元素靠近（格式塔原则） |

### 7. 动效（Motion）

| 规则 | 描述 |
|------|------|
| 7.1 缓动函数 | ease-out（入场）/ ease-in（出场）/ ease-in-out（双向） |
| 7.2 时长 | 短 150-200ms / 中 300-400ms / 长 500ms+ |
| 7.3 距离 | 短距离快，长距离慢 |
| 7.4 延迟 | 列表项错开 30-50ms |
| 7.5 减少动效 | `prefers-reduced-motion` |
| 7.6 性能 | transform / opacity 优先，避开 width/height |

### 8. 无障碍（Accessibility）

| 规则 | 描述 |
|------|------|
| 8.1 语义 HTML | button / nav / main / aside / article |
| 8.2 焦点环 | 永远显示，自定义不删除 |
| 8.3 键盘导航 | Tab 顺序与视觉顺序一致 |
| 8.4 ARIA | 仅在必要补 HTML 缺失时用 |
| 8.5 表单标签 | label[for] 与 input[id] 关联 |
| 8.6 颜色对比 | WCAG AA ≥ 4.5:1 |
| 8.7 跳过导航 | 跳到 main content |
| 8.8 替代文本 | 装饰图 alt=""，信息图 alt 描述 |

### 9. 性能（Performance）

| 规则 | 描述 |
|------|------|
| 9.1 字体加载 | 自托管 + font-display: swap |
| 9.2 图片格式 | WebP / AVIF，`<Image>` 组件 |
| 9.3 LCP < 2.5s | 优化首屏图片 |
| 9.4 CLS < 0.1 | 图片/视频/iframe 显式宽高 |
| 9.5 INP < 200ms | 避免长任务 |
| 9.6 JS 体积 | 路由级 < 100KB |
| 9.7 关键 CSS | 内联 above-the-fold 样式 |

### 10. 响应式（Responsive）

| 规则 | 描述 |
|------|------|
| 10.1 移动优先 | 默认 mobile，`md:` 才加桌面样式 |
| 10.2 断点 | sm 640 / md 768 / lg 1024 / xl 1280 / 2xl 1536 |
| 10.3 触控目标 | ≥ 44×44px |
| 10.4 字体缩放 | 浏览器 zoom 100% 起工作 |
| 10.5 容器 | max-w-7xl mx-auto px-4 |
| 10.6 隐藏元素 | `hidden md:block` 而非 `display: none` |

### 11. 暗色模式（Dark Mode）

| 规则 | 描述 |
|------|------|
| 11.1 不用纯黑 | zinc-900 / neutral-900 |
| 11.2 文本分级 | 主文本 zinc-100，次 zinc-400 |
| 11.3 阴影减弱 | 改用 border 区分 |
| 11.4 色彩降饱和 | 暗色降低 10-20% 饱和度 |
| 11.5 状态色保留 | 维持 brand 色的可识别度 |
| 11.6 切换动画 | 200ms 平滑过渡 |

### 12. 国际化（i18n）

| 规则 | 描述 |
|------|------|
| 12.1 文本方向 | LTR / RTL 通用 |
| 12.2 留白扩展 | 德语比英语长 30% |
| 12.3 字体回退 | 中文用 Noto Sans / 思源黑体 |
| 12.4 日期数字 | 区域感知（Intl.DateTimeFormat） |
| 12.5 单复数 | i18n 库支持 plural rule |
| 12.6 别拼接词 | 留 `<i18n>` 占位 |

## 审查流程

### Step 1 — 抓取目标

```bash
# 文件
read /path/to/file.tsx

# URL
webfetch url="https://target.com"
```

### Step 2 — 分类检查

按 12 大类逐项对照。

### Step 3 — 输出问题清单

```markdown
## [2. 色彩] 2.4 主文本对比度不足
**位置**：Header.tsx:42
**现状**：`text-zinc-500 on bg-white` 对比度 4.2:1
**建议**：改用 `text-zinc-700`（对比度 7.1:1）
**影响**：WCAG AA 失败，移动端阳光下不可读

## [3. 间距] 3.6 1px 边界
**位置**：Card.tsx
**现状**：`<div class="border border-zinc-200">`
**建议**：改用 `border-zinc-200 border-[0.5px]` 或 `border-2`
**影响**：Hi-DPI 屏渲染抖动
```

### Step 4 — 给出评分

```
总分 = 各类别得分加权平均
- 字体 25% + 色彩 20% + 间距 15% + 圆角 5% + 阴影 5% + 对齐 10% + 动效 5% + 无障碍 10% + 性能 5%
```

## 提示

- 配合 `frontend-pro` 走 a11y + 性能深审
- 配合 `tailwind-pro` 验证 Tailwind 写法
- 配合 `web-design-engineer` 验证整体视觉
- 配合 `react-pro` 跑 45 条性能优化
