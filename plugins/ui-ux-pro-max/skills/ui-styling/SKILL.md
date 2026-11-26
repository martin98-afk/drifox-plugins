---
name: ui-styling
description: "用 shadcn/ui（Radix UI + Tailwind）、Tailwind 原子类与 canvas 视觉设计做漂亮且可访问的界面。构建界面、落地设计体系、做响应式布局、加可访问组件（弹窗、下拉、表单、表格）、定制主题与配色、实现暗色模式、生成视觉设计与海报、统一全应用的样式范式时使用。"
argument-hint: "[组件或布局]"
version: 1.0.0
license: MIT
metadata:
  author: claudekit
  upstream: nextlevelbuilder/ui-ux-pro-max-skill
  localized: zh-CN
---

# UI Styling

把 shadcn/ui 组件、Tailwind 原子样式与 canvas 视觉设计体系合起来用的综合技能。

## 什么时候用

- 用 React 系框架做 UI（Next.js、Vite、Remix、Astro）
- 实现可访问组件（弹窗、表单、表格、导航）
- 用原子类做样式
- 移动优先的响应式布局
- 暗色模式与主题定制
- 用一致的 token 搭设计体系
- 生成视觉设计、海报、品牌物料
- 需要即时视觉反馈的快速原型
- 加复杂 UI 模式（数据表、图表、命令面板）

## 技术栈三层

### 组件层：shadcn/ui

- 基于 Radix UI 原语的可访问组件
- 复制式分发：组件代码落在你的仓库里
- TypeScript 优先，类型完整
- 可组合的原语，支撑复杂 UI
- CLI 安装与管理

### 样式层：Tailwind CSS

- 原子优先的 CSS 框架
- 构建期处理，运行时零开销
- 移动优先的响应式
- 一致的设计 token（颜色、间距、字体）
- 自动摇掉无用代码

### 视觉设计层：Canvas

- 美术馆级的视觉构图
- 由设计哲学驱动
- 讲究的视觉表达
- 少文字，强视觉冲击
- 系统化范式与精炼美学

## 脚本路径

本技能与其 `references/` 里的脚本路径，相对于本 SKILL.md 所在目录，不是项目目录：`scripts/<file>` 是本技能自己的 `scripts/`，`../<skill>/scripts/<file>` 是同级子技能的。用这个目录拼出完整路径，工作目录保持在项目根：脚本按项目根读写 `docs/brand-guidelines.md`、`assets/design-tokens.json`、`src/` 这些文件。

## 快速开始

**装 shadcn/ui 与 Tailwind：**

```bash
npx shadcn@latest init
```

CLI 会问框架、TypeScript、路径与主题偏好，一次配好 shadcn/ui 与 Tailwind CSS。

**加组件：**

```bash
npx shadcn@latest add button card dialog form
```

**组件 + 原子类一起用：**

```tsx
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"

export function Dashboard() {
  return (
    <div className="container mx-auto p-6 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      <Card className="hover:shadow-lg transition-shadow">
        <CardHeader>
          <CardTitle className="text-2xl font-bold">Analytics</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground">View your metrics</p>
          <Button variant="default" className="w-full">View Details</Button>
        </CardContent>
      </Card>
    </div>
  )
}
```

**只用 Tailwind（Vite 项目）：**

```bash
npm install -D tailwindcss @tailwindcss/vite
```

```javascript
// vite.config.ts
import tailwindcss from '@tailwindcss/vite'
export default { plugins: [tailwindcss()] }
```

```css
/* src/index.css */
@import "tailwindcss";
```

## 组件库指南

组件目录、用法范式、安装与组合示例见 `references/shadcn-components.md`，覆盖：

- 表单与输入（Button、Input、Select、Checkbox、Date Picker、表单校验）
- 布局与导航（Card、Tabs、Accordion、Navigation Menu）
- 浮层与弹窗（Dialog、Drawer、Popover、Toast、Command）
- 反馈与状态（Alert、Progress、Skeleton）
- 展示组件（Table、Data Table、Avatar、Badge）

## 主题与定制

见 `references/shadcn-theming.md`，覆盖：

- 用 next-themes 做暗色模式
- CSS 变量体系
- 配色定制与调色板
- 组件变体定制
- 主题切换实现

## 无障碍范式

见 `references/shadcn-accessibility.md`，覆盖：

- Radix UI 的无障碍能力
- 键盘导航范式
- 焦点管理
- 屏幕阅读器播报
- 表单校验的无障碍

## Tailwind 原子类

见 `references/tailwind-utilities.md`，覆盖布局（Flex/Grid/定位）、间距体系、字体（字号/字重/对齐/行高）、颜色与背景、边框与阴影、任意值写法。

## 响应式

见 `references/tailwind-responsive.md`，覆盖移动优先、断点体系（sm/md/lg/xl/2xl）、响应式范式、容器查询、max-width 查询、自定义断点。

## Tailwind 定制

见 `references/tailwind-customization.md`，覆盖 `@theme` 自定义 token、自定义颜色与字体、间距与断点扩展、自定义工具类与变体、`@layer` 分层、用 `apply` 抽取组件类。

## 视觉设计体系

见 `references/canvas-design-system.md`，覆盖设计哲学、以视觉而非文字表达、系统化构图、颜色/形体/空间、极简文字融合、美术馆级执行、多页设计体系。

## 自动化脚本

**加 shadcn/ui 组件（含依赖处理）：**

```bash
python scripts/shadcn_add.py button card dialog
```

**生成 tailwind.config.js：**

```bash
python scripts/tailwind_config_gen.py --colors brand:blue --fonts display:Inter
```

同名目录里已存在 `tailwind.config.js`、`.cjs`、`.mjs` 或 `.ts` 时，生成器会拒绝创建或覆盖。先看它报告的那份配置，确认冲突是有意为之，再加 `--force`：

```bash
python scripts/tailwind_config_gen.py --colors brand:blue --force
```

## 最佳实践

1. **组件的组合**：用简单、可组合的原语拼复杂 UI。
2. **原子优先**：直接写 Tailwind 类；只有真正重复时才抽组件。
3. **移动优先**：先写移动端样式，再叠响应式变体。
4. **无障碍优先**：用 Radix 原语，补焦点态，用语义化 HTML。
5. **设计 token**：统一的间距尺度、配色与字体体系。
6. **暗色一致**：所有主题化元素都写暗色变体。
7. **性能**：靠自动 CSS 摇树，避免动态拼接类名。
8. **TypeScript**：用完整类型换更好的开发体验。
9. **视觉层级**：让构图引导注意力，间距与颜色都是有意的。
10. **手艺**：每个细节都算数，把 UI 当手艺对待。

## 参考导航

**组件库**：`references/shadcn-components.md`、`references/shadcn-theming.md`、`references/shadcn-accessibility.md`

**样式体系**：`references/tailwind-utilities.md`、`references/tailwind-responsive.md`、`references/tailwind-customization.md`

**视觉设计**：`references/canvas-design-system.md`

**自动化**：`scripts/shadcn_add.py`、`scripts/tailwind_config_gen.py`

## 常见范式

**带校验的表单**：用 react-hook-form + zod + shadcn 的 Form 组件组合，schema 定义字段规则，`FormField` 渲染每个字段并按需显示错误。完整示例见 `references/shadcn-components.md`。

**数据表**：TanStack Table + shadcn 的 Table 原语，先做排序与筛选，再按需加分页。

## 本地化说明

本文件由英文原文译写为中文，代码示例保留原样。上游随包的 54 个 TTF 字体（`canvas-fonts/`）未收录：canvas 视觉设计用系统字体或项目自带字体，`references/canvas-design-system.md` 里对 `canvas-fonts/` 的引用按此理解。脚本 `shadcn_add.py` 需要 Node/npx 与 Python 3，环境缺失时按 `references/` 手工装组件、写配置。