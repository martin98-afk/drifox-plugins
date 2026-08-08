# react-pro

> React / Next.js 性能优化与最佳实践 — 45 条 RSC 边界、Server Components、App Router、缓存策略、Streaming、bundle 优化。

源自 [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) 的 `react-best-practices` skill，helloianneo/awesome-claude-code-skills **强推**。

## 45 条核心规则概览

### A. Server Components（默认）

1. 组件默认是 Server Components（除非显式 `"use client"`）
2. data fetching 在 Server Component 完成
3. 避免把 fetch 移到 Client Component
4. Server Component 不能用 hooks / DOM API
5. 跨 RSC 边界需要序列化（JSON 兼容）

### B. Client Components

6. 仅在需要交互/状态/浏览器 API 时加 `"use client"`
7. 叶子组件优先 client（push `"use client"` 往下）
8. 不要在 Server Component 中 import client 组件再传 children
9. `useState` 不可跨 RSC 边界
10. `useEffect` 仅在客户端使用

### C. App Router

11. `app/` 默认 RSC，`pages/` 自动 client
12. `loading.tsx` → `Suspense` fallback
13. `error.tsx` → ErrorBoundary
14. `not-found.tsx` → 404 UI
15. `layout.tsx` 跨路由复用，不参与 prefetch

### D. 数据获取

16. 默认使用 React `cache()` 去重
17. `fetch()` 自动 dedupe（GET 同一 URL）
18. Server Action 用 `"use server"` 顶部
19. Form 使用 `useFormState` / `useFormStatus`
20. 避免 waterfall：先并行，再串行

### E. 缓存策略

21. Next.js 14+ 默认 `force-cache`（GET）
22. `revalidate: 60` ISR 60 秒
23. `revalidate: 0` 关闭缓存
24. `unstable_cache` 函数级缓存
25. 缓存键要稳定（避免随机值）

### F. Streaming

26. `loading.tsx` 触发 Suspense 流式
27. `<Suspense fallback={...}>` 异步组件边界
28. 慢查询移到独立组件，便于流式
29. `use(promise)` 读 19+ 异步
30. 避免串行 waterfall

### G. Bundle 优化

31. `next/dynamic` 懒加载组件
32. `next/font` 自托管字体
33. `next/image` 自动优化
34. `next/link` prefetch
35. Server Component 不进 bundle

### H. 元数据与 SEO

36. `metadata` 导出（顶 layout）→ 全局
37. `generateMetadata` 动态 metadata
38. `openGraph` 字段自动 OG 生成
39. `robots.txt` 和 `sitemap.ts` 用 App Router
40. JSON-LD 写在 Server Component

### I. 性能诊断

41. Lighthouse 目标 Performance > 90
42. CLS < 0.1 / LCP < 2.5s / INP < 200ms
43. `next build` 输出首字节、bundle 大小
44. `@next/bundle-analyzer` 分析
45. React DevTools Profiler 找 re-render

## 安装

```bash
/plugin marketplace add martin98-afk/drifox-plugins
/plugin install react-pro@drifox-official
```

## 命令

| 命令 | 用途 |
|------|------|
| `/react-review [path]` | 对指定路径跑 45 条规则审查 |
| `/react-migrate` | Pages Router → App Router 迁移助手 |

## 提示

- 配合 `frontend-pro`（a11y / 组件设计）
- 配合 `tailwind-pro`（样式）
- 配合 `web-design-skills`（视觉）

## 许可

MIT（agent-skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
