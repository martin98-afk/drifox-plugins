---
name: context7
description: 当用户询问或使用任意第三方库（React/Vue/Tailwind/Three.js/Stripe/Supabase 等）的 API、最佳实践、代码示例时，触发 Context7 实时文档拉取。触发关键词：查 API、查文档、API 文档、最新文档、library docs、how to use <库>、<库> 怎么用、context7、拉文档。
---

# Context7 技能 — 实时拉取第三方库文档

本技能让 AI 在编写涉及第三方库的代码前**主动调用 Context7 拉取最新文档**，避免基于过期知识编造 API。

## 何时调用

以下任意条件满足，**必须**先调用再回答：

1. 用户要求"用 X 库写..."、`X 怎么用`、`X 的 API`
2. AI 不确定某个库/版本的具体 API 签名
3. AI 准备生成代码但内部知识可能过期（库版本更新很快）
4. 用户引用了某个库的特定 topic（如 `useInfiniteQuery`、`server actions`、`arbitrary values`）

## 调用流程

### Step 1 — 解析库名

去掉无关修饰词：
```
输入："react query 怎么用" → libraryName="react query"
输入："the latest docs for vue 3" → libraryName="vue 3"
输入："how to use stripe webhooks" → libraryName="stripe"
```

### Step 2 — resolve-library-id

```python
mcp__context7__resolve-library-id(libraryName="<library>")
```

返回 context7 ID（`/org/project` 格式），用户可能没指明版本时**默认带最新稳定版**。

### Step 3 — get-library-docs

```python
mcp__context7__get-library-docs(
    context7CompatibleLibraryID="<id>",
    topic="<topic>",       # 可选，从用户问题中提取
    tokens=5000            # 默认
)
```

### Step 4 — 整合输出

把文档切片**放进当前上下文**，基于真实文档回答用户问题，给出可运行代码示例。

## 主题提取规则

从用户问题中提取最相关的 topic：

| 用户问题 | topic |
|---------|-------|
| React Query 无限滚动 | `useInfiniteQuery` |
| Tailwind 任意值 | `arbitrary-values` |
| Stripe webhook | `webhooks` |
| Next.js server actions | `server-actions` |
| Three.js 加载模型 | `gltf-loader` |

## 反模式

- ❌ **不要**基于记忆瞎编 API — 直接调用 MCP 拿真实文档
- ❌ **不要**在不确定时跳过调用 — 一次 5000 token 成本远低于返工
- ❌ **不要**把整个文档贴回用户 — 提取与问题相关的部分
- ❌ **不要**忽略版本 — 拉文档时带上版本号（如 `react@18`、`vue@3`）

## 典型表现

**❌ 错误示范**（基于记忆瞎编）：
```ts
// AI 编的，可能不存在
const query = useInfiniteQuery(['items'], fetchFn, { cursor: '...' })
```

**✅ 正确示范**（基于 Context7）：
```ts
// 来自 context7 拉取的 React Query v5 文档
import { useInfiniteQuery } from '@tanstack/react-query'

const {
  data,
  fetchNextPage,
  hasNextPage,
} = useInfiniteQuery({
  queryKey: ['items'],
  queryFn: ({ pageParam = 0 }) => fetchItems(pageParam),
  getNextPageParam: (lastPage) => lastPage.nextCursor,
  initialPageParam: 0,
})
```

## 提示词集成

在 system prompt 中加入：

> 调用任何第三方库 API 前，**先调用 Context7 MCP 拉取最新文档**。库名解析失败时，提示 2-3 个最接近的库名让用户选择。
