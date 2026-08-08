---
description: 对 React/Next.js 代码跑 45 条性能优化规则审查，输出结构化问题清单与修复建议
type: prompt
parameters:
  - name: "<path>"
    description: "目标路径（文件或目录），默认 ./
    param_type: positional
  - name: "--category="
    description: "聚焦类别：rsc/client/app-router/data/cache/streaming/bundle/seo/diagnostic"
    param_type: value
  - name: "--severity="
    description: "最低严重度：info/warning/error"
    param_type: value
allowed-tools:
  - read
  - grep
  - glob
  - bash
hidden: false
---

# /react-review 命令 — React/Next.js 45 条性能优化审查

你正在处理 `/react-review` 命令。本命令对指定路径跑 **45 条 react-best-practices 规则审查**，按 `error > warning > info` 输出问题清单。

## 📋 执行规则

1. **解析参数**：
   - `<path>`：默认 `./`，可用文件 / 目录
   - `--category=`：聚焦某类（默认全跑）
   - `--severity=`：最低严重度（默认 `info`）

2. **发现目标文件**：
   ```
   glob(**/*.{ts,tsx,js,jsx})
   ```

3. **按 45 条规则逐项检查**（按类别）：

   ### A. Server Components（5 条）

   - A.1 组件默认是 Server Components（除非显式 `"use client"`）
   - A.2 data fetching 在 Server Component 完成
   - A.3 避免把 fetch 移到 Client Component
   - A.4 Server Component 不能用 hooks / DOM API
   - A.5 跨 RSC 边界需要序列化（JSON 兼容）

   **检测方法**：
   ```bash
   # A.1: 没有 "use client" 指令的 .tsx 文件数量
   grep -L "use client" --include="*.tsx" -r .

   # A.4: Server Component 中误用 hooks
   # 移除有 "use client" 的文件后，再 grep hooks
   ```

   ### B. Client Components（5 条）

   - B.1 仅在需要交互/状态/浏览器 API 时加 `"use client"`
   - B.2 叶子组件优先 client
   - B.3 不要在 Server Component 中 import client 组件再传 children
   - B.4 `useState` 不可跨 RSC 边界
   - B.5 `useEffect` 仅在客户端使用

   **检测方法**：
   ```bash
   # B.1: useState/useEffect 在无 "use client" 文件中的误用
   ```

   ### C. App Router（5 条）

   - C.1 `app/` 默认 RSC
   - C.2 `loading.tsx` 存在
   - C.3 `error.tsx` 存在
   - C.4 `not-found.tsx` 存在
   - C.5 `layout.tsx` 跨路由复用

   ### D. 数据获取（5 条）

   - D.1 默认使用 React `cache()` 去重
   - D.2 `fetch()` 自动 dedupe
   - D.3 Server Action 用 `"use server"`
   - D.4 Form 使用 `useFormState` / `useFormStatus`
   - D.5 避免 waterfall

   **检测方法**：
   ```bash
   # D.5: 串行 await
   grep -B0 -A5 "await" --include="*.tsx" -r . | grep -B0 "fetch"
   ```

   ### E. 缓存策略（5 条）

   - E.1 Next.js 14+ 默认 `force-cache`
   - E.2 `revalidate: 60` ISR
   - E.3 `revalidate: 0` 关闭缓存
   - E.4 `unstable_cache` 函数级缓存
   - E.5 缓存键要稳定

   ### F. Streaming（5 条）

   - F.1 `loading.tsx` 触发 Suspense
   - F.2 `<Suspense fallback={...}>` 异步边界
   - F.3 慢查询移到独立组件
   - F.4 `use(promise)` 读 19+
   - F.5 避免串行 waterfall

   ### G. Bundle 优化（5 条）

   - G.1 `next/dynamic` 懒加载
   - G.2 `next/font` 自托管
   - G.3 `next/image` 自动优化
   - G.4 `next/link` prefetch
   - G.5 Server Component 不进 bundle

   **检测方法**：
   ```bash
   # G.3: 直接用 <img> 标签
   grep -E "<img" --include="*.tsx" -r .

   # G.4: 直接用 <a> 而非 <Link>
   grep -E "<a href" --include="*.tsx" -r .
   ```

   ### H. 元数据与 SEO（5 条）

   - H.1 `metadata` 导出
   - H.2 `generateMetadata` 动态
   - H.3 `openGraph` 字段
   - H.4 `robots.txt` / `sitemap.ts`
   - H.5 JSON-LD

   ### I. 性能诊断（5 条）

   - I.1 Lighthouse Performance > 90
   - I.2 CLS < 0.1 / LCP < 2.5s / INP < 200ms
   - I.3 `next build` 输出
   - I.4 `@next/bundle-analyzer` 集成
   - I.5 React DevTools Profiler

4. **每条问题输出格式**：
   ```
   [E/W/I] <规则 ID> <规则名>
   位置：<文件>:<行>
   现状：<代码片段 / 状态>
   建议：<具体修复>
   影响：<性能影响 / bundle 体积 / UX>
   ```

5. **底部汇总**：
   - 各类别命中数
   - 总分（按严重度加权）
   - 优化路线图（按 P0→P1→P2 排序）

## 子行为

<!-- section:category -->
### `--category=<name>` 聚焦类别

可选：`rsc`、`client`、`app-router`、`data`、`cache`、`streaming`、`bundle`、`seo`、`diagnostic`

例：`/react-review ./src --category=bundle` 仅跑 Bundle 优化类规则。
<!-- end -->

<!-- section:severity -->
### `--severity=<level>` 最低严重度

- `info`：所有提示（含 `info` 级）
- `warning`：仅 `warning` + `error`
- `error`：仅 `error` 级

例：`/react-review . --severity=warning` 隐藏 `info`。
<!-- end -->

## 模板变量

- `$ARGUMENTS`：用户输入的完整参数
- `$PLUGIN_NAME`：当前插件名（react-pro）
- `$PROJECT_ROOT`：当前工作项目根目录

## 提示

- 配合 `frontend-pro` 验证 a11y
- 配合 `tailwind-pro` 验证样式
- 配合 `web-design-skills` 验证视觉
- 大型项目推荐 `--category=bundle` 先优化 bundle
