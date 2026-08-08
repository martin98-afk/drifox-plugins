---
name: react-pro
description: React / Next.js 性能优化与最佳实践 — 45 条规则覆盖 RSC 边界、Client Components、App Router、数据获取、缓存策略、Streaming、Bundle 优化、SEO、性能诊断。触发关键词：react、nextjs、next.js、rsc、server component、client component、app router、bundle、performance、next.js 性能、react 优化、use client、use server、useFormState、useFormStatus、next/link、next/image、next/dynamic、next/font、unstable_cache、revalidate、streaming、suspense、waterfall、clash、lcp、inp、cls、web vitals、core web vitals、react-pro。
---

# React / Next.js 性能优化技能

本技能为 AI 提供 React / Next.js 性能优化与最佳实践知识，覆盖 **45 条 react-best-practices 规则**。

## 何时触发

- 用户："优化 React 性能"、"Next.js 性能"
- 用户："为什么页面加载慢"、"LCP / INP / CLS 不达标"
- 用户："Bundle 太大"、"Bundle 优化"
- AI 编写 React/Next.js 代码时自动注入

## 45 条规则

### A. Server Components（5 条）

#### A.1 组件默认是 Server Components（除非显式 `"use client"`）

```tsx
// ✅ 默认 Server Component（无 "use client"）
async function ProductList() {
  const products = await db.product.findMany()
  return <ul>{products.map(...)}</ul>
}

// ❌ 不必要 client
"use client"
function ProductList() { ... }
```

#### A.2 data fetching 在 Server Component 完成

```tsx
// ✅ Server Component 直接 fetch
async function Dashboard() {
  const stats = await fetch('https://api.example.com/stats').then(r => r.json())
  return <Stats data={stats} />
}

// ❌ 不必要 client fetch
"use client"
function Dashboard() {
  const [stats, setStats] = useState(null)
  useEffect(() => { fetch(...).then(r => r.json()).then(setStats) }, [])
}
```

#### A.3 避免把 fetch 移到 Client Component

理由：失去 RSC 优势（SSR/数据共置/bundle 减小）。

#### A.4 Server Component 不能用 hooks / DOM API

```tsx
// ❌ Server Component 误用 hooks
function BadServer() {
  const [x, setX] = useState(0)  // 编译错
  return <div>{x}</div>
}
```

#### A.5 跨 RSC 边界需要序列化（JSON 兼容）

```tsx
// ❌ 函数不能跨边界
<ClientComponent onClick={() => doSomething()} />

// ✅ 函数定义在 client 内部
"use client"
function ClientComponent() {
  const handleClick = () => doSomething()
  return <button onClick={handleClick} />
}
```

### B. Client Components（5 条）

#### B.1 仅在需要交互/状态/浏览器 API 时加 `"use client"`

```tsx
// ✅ client（需要状态）
"use client"
function Counter() {
  const [count, setCount] = useState(0)
  return <button onClick={() => setCount(c => c + 1)}>{count}</button>
}

// ✅ server（仅展示）
function Header({ title }: { title: string }) {
  return <h1>{title}</h1>
}
```

#### B.2 叶子组件优先 client（push `"use client"` 往下）

```tsx
// ❌ 整棵树 client
"use client"
function Page() {
  return (
    <div>
      <Header />
      <Sidebar />
      <Content />  // 实际需要 client
    </div>
  )
}

// ✅ 叶子 client
function Page() {  // server
  return (
    <div>
      <Header />
      <Sidebar />
      <Content />  // 自身有 "use client"
    </div>
  )
}
```

#### B.3 不要在 Server Component 中 import client 组件再传 children

```tsx
// ❌ children 是函数
function Server() {
  return <Client onRender={() => ...} />
}

// ✅ children 是元素
function Server() {
  return <Client>{() => ...}</Client>
}
```

#### B.4 `useState` 不可跨 RSC 边界

#### B.5 `useEffect` 仅在客户端使用

### C. App Router（5 条）

#### C.1 `app/` 默认 RSC
#### C.2 `loading.tsx` 触发 Suspense
#### C.3 `error.tsx` 错误边界
#### C.4 `not-found.tsx` 404 UI
#### C.5 `layout.tsx` 跨路由复用（不参与 prefetch）

```tsx
// app/layout.tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body>{children}</body>
    </html>
  )
}
```

### D. 数据获取（5 条）

#### D.1 默认使用 React `cache()` 去重

```tsx
import { cache } from 'react'

export const getUser = cache(async (id: string) => {
  return await db.user.findUnique({ where: { id } })
})
```

#### D.2 `fetch()` 自动 dedupe（GET 同一 URL）

#### D.3 Server Action 用 `"use server"` 顶部

```tsx
// actions.ts
"use server"
export async function createUser(formData: FormData) {
  await db.user.create({ ... })
  revalidatePath('/users')
}
```

#### D.4 Form 使用 `useFormState` / `useFormStatus`

```tsx
"use client"
import { useFormState, useFormStatus } from 'react-dom'

function Form() {
  const [state, action] = useFormState(createUser, { error: null })
  return <form action={action}>...</form>
}
```

#### D.5 避免 waterfall：先并行，再串行

```tsx
// ❌ 串行
const a = await fetchA()
const b = await fetchB()
const c = await fetchC()

// ✅ 并行
const [a, b, c] = await Promise.all([fetchA(), fetchB(), fetchC()])
```

### E. 缓存策略（5 条）

#### E.1 Next.js 14+ 默认 `force-cache`（GET）

```tsx
// 默认缓存
const data = await fetch('https://api.example.com/data')
```

#### E.2 `revalidate: 60` ISR 60 秒

```tsx
const data = await fetch('https://api.example.com/data', {
  next: { revalidate: 60 }
})
```

#### E.3 `revalidate: 0` 关闭缓存

#### E.4 `unstable_cache` 函数级缓存

```tsx
import { unstable_cache } from 'next/cache'

const getCached = unstable_cache(
  async (id: string) => db.user.findUnique({ where: { id } }),
  ['user-cache'],
  { revalidate: 3600 }
)
```

#### E.5 缓存键要稳定（避免随机值）

### F. Streaming（5 条）

#### F.1 `loading.tsx` 触发 Suspense 流式
#### F.2 `<Suspense fallback={...}>` 异步边界
#### F.3 慢查询移到独立组件，便于流式
#### F.4 `use(promise)` 读 19+ 异步
#### F.5 避免串行 waterfall

```tsx
// 流式渲染慢组件
function Page() {
  return (
    <>
      <FastComponent />
      <Suspense fallback={<Skeleton />}>
        <SlowComponent />
      </Suspense>
    </>
  )
}
```

### G. Bundle 优化（5 条）

#### G.1 `next/dynamic` 懒加载

```tsx
import dynamic from 'next/dynamic'

const HeavyChart = dynamic(() => import('./HeavyChart'), {
  loading: () => <Skeleton />,
  ssr: false
})
```

#### G.2 `next/font` 自托管字体

```tsx
import { Inter } from 'next/font/google'
const inter = Inter({ subsets: ['latin'] })
```

#### G.3 `next/image` 自动优化

```tsx
import Image from 'next/image'
<Image src="/hero.png" width={1200} height={600} alt="Hero" />
```

#### G.4 `next/link` prefetch

```tsx
import Link from 'next/link'
<Link href="/about">About</Link>
```

#### G.5 Server Component 不进 bundle

### H. 元数据与 SEO（5 条）

#### H.1 `metadata` 导出（顶 layout）

```tsx
export const metadata = {
  title: 'My App',
  description: 'Best app ever',
}
```

#### H.2 `generateMetadata` 动态

```tsx
export async function generateMetadata({ params }: { params: { id: string } }) {
  const product = await getProduct(params.id)
  return { title: product.name, description: product.description }
}
```

#### H.3 `openGraph` 字段自动 OG
#### H.4 `robots.txt` 和 `sitemap.ts` 用 App Router
#### H.5 JSON-LD 写在 Server Component

```tsx
function ProductJsonLd({ product }: { product: Product }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify({
          '@context': 'https://schema.org',
          '@type': 'Product',
          name: product.name,
          description: product.description,
        })
      }}
    />
  )
}
```

### I. 性能诊断（5 条）

#### I.1 Lighthouse Performance > 90
#### I.2 CLS < 0.1 / LCP < 2.5s / INP < 200ms
#### I.3 `next build` 输出首字节、bundle 大小
#### I.4 `@next/bundle-analyzer` 分析

```ts
// next.config.js
const withBundleAnalyzer = require('@next/bundle-analyzer')({ enabled: process.env.ANALYZE === 'true' })
module.exports = withBundleAnalyzer({})
```

#### I.5 React DevTools Profiler 找 re-render

## 反模式

- ❌ 整棵树 client（推送 `"use client"` 不到叶子）
- ❌ Server Component 用 hooks
- ❌ 函数跨 RSC 边界
- ❌ Client Component 中 fetch
- ❌ 串行 `await`（waterfall）
- ❌ 直接 `<img>` 而非 `<Image>`
- ❌ 直接 `<a>` 而非 `<Link>`
- ❌ 同步大数据到客户端

## 提示

- 配合 `frontend-pro` 验证 a11y
- 配合 `tailwind-pro` 验证样式
- 配合 `web-design-skills` 验证视觉
- 启用 `/react-review` 自动扫描
