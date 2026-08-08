---
description: 在项目里初始化 Tailwind CSS v4（含 v3→v4 迁移检测）
type: prompt
parameters:
  - name: "--migration"
    description: "从 v3 迁移到 v4 模式"
    param_type: flag
  - name: "--framework="
    description: "前端框架：next / vite / remix / astro / nuxt / sveltekit / 静态"
    param_type: value
allowed-tools:
  - read
  - bash
  - write
  - grep
hidden: false
---

# /tailwind-init 命令 — 初始化 Tailwind CSS v4

你正在处理 `/tailwind-init` 命令。本命令在当前项目中安装并配置 Tailwind CSS v4。

## 📋 执行规则

1. **解析参数**：
   - `--framework=`：next / vite / remix / astro / nuxt / sveltekit / 静态(无)
   - `--migration`：从 v3 迁移到 v4

2. **检测当前状态**：

   ```bash
   # 检查是否已安装
   grep "tailwindcss" package.json
   ls tailwind.config.* postcss.config.* 2>/dev/null
   ```

3. **按框架执行**：

   ### Next.js / Vite / Remix / Astro / Nuxt / SvelteKit

   一行安装：
   ```bash
   npm install -D tailwindcss @tailwindcss/vite
   ```

   在 `vite.config.ts` 添加：
   ```ts
   import tailwindcss from '@tailwindcss/vite'
   export default defineConfig({
     plugins: [react(), tailwindcss()],
   })
   ```

   在 CSS 顶部加：
   ```css
   @import "tailwindcss";
   ```

   不再需要 `tailwind.config.js` / `postcss.config.js`（v4 默认配置）。

   ### 静态 HTML

   ```html
   <!doctype html>
   <html>
   <head>
     <script src="https://cdn.tailwindcss.com"></script>
   </head>
   <body>
     <h1 class="text-3xl font-bold text-blue-600">Hello</h1>
   </body>
   </html>
   ```

4. **--migration 模式**：

   - 删除 `tailwind.config.js`（可选保留兼容）
   - 把 `tailwind.config.js` 的 `theme.extend` 移到 CSS：
     ```css
     @import "tailwindcss";

     @theme {
       --color-brand-500: oklch(0.7 0.2 240);
       --spacing-18: 4.5rem;
     }
     ```
   - 替换 `@tailwind base/components/utilities` 为 `@import "tailwindcss"`
   - 重命名类名（v3 → v4）：
     - `bg-gradient-to-r` → `bg-linear-to-r`
     - `shadow-sm` → `shadow-xs`（v4 改 `box-shadow` 简写）
     - 移除 `ring-{color}` 中的颜色默认（v4 默认不应用）

5. **验证**：
   ```bash
   npm run dev
   # 浏览器打开 → 看到样式即成功
   ```

## 子行为

<!-- section:migration -->
### `--migration` v3 → v4 迁移清单

| v3 写法 | v4 写法 |
|--------|--------|
| `tailwind.config.js` | `@theme` CSS 变量 |
| `@tailwind base` | `@import "tailwindcss"` |
| `@apply` | `@utility` |
| `bg-gradient-to-r` | `bg-linear-to-r` |
| `shadow-sm` | `shadow-xs` |
| `ring-{color}` 默认着色 | 需显式 `ring-{color}/N` |
| `darkMode: 'class'` | `@custom-variant dark` |
| `content` 配置 | 自动检测（无需配置） |
| `safelist` | 自动 tree-shake |
<!-- end -->

## 模板变量

- `$ARGUMENTS`：用户输入的完整参数
- `$PLUGIN_NAME`：当前插件名（tailwind-pro）
- `$PROJECT_ROOT`：当前工作项目根目录

## 提示

- 初始化后会自动启用 `tailwind-pro` LSP（class 名 hover / 补全 / 颜色预览）
- 配合 `frontend-pro` / `react-pro` 使用最佳
- 详细迁移文档：https://tailwindcss.com/docs/upgrade-guide
