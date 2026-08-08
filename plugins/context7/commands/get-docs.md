---
description: 拉取并展示 <library> 的最新 API 文档（通过 Context7 MCP）
type: prompt
parameters:
  - name: "<library>"
    description: "库名或包名，如 react / tailwindcss / three / @supabase/supabase-js"
    param_type: positional
  - name: "--topic="
    description: "可选，仅拉取指定主题（如 useInfiniteQuery、server actions）"
    param_type: value
  - name: "--tokens="
    description: "可选，上限 token 数（默认 5000）"
    param_type: value
allowed-tools:
  - mcp
  - read
  - grep
hidden: false
---

# /get-docs 命令 — 拉取任意库的最新文档

你正在处理 `/get-docs` 命令。本命令通过 Context7 MCP 拉取**用户指定库**的最新文档片段，避免把文档链接贴进对话。

## 📋 执行规则

1. **解析参数**：
   - 取出 `<library>`、`--topic=`、`--tokens=`（缺省 5000）
   - 库名去掉无意义修饰词（"the" / "latest" / "documentation for" / "how to use"）

2. **调用 MCP 工具**：

   **Step 1 — resolve-library-id**：
   ```
   mcp__context7__resolve-library-id(libraryName="<library>")
   ```
   返回类似 `/reactjs/react.dev` 或 `/tailwindlabs/tailwindcss.com` 的 ID。

   **Step 2 — get-library-docs**：
   ```
   mcp__context7__get-library-docs(
       context7CompatibleLibraryID="<id>",
       topic="<topic>",            # 可选
       tokens=<tokens>             # 默认 5000
   )
   ```

3. **格式化输出**：
   - 顶部：`📚 <library> 文档（来自 Context7）`
   - 主体：MCP 返回的文档原文（Markdown）
   - 底部：列出 3-5 条最相关的代码示例（含 import / 完整 API 签名）

4. **错误处理**：
   - 库名未找到：建议 2-3 个最接近的库名
   - 主题无结果：降级为全量文档
   - token 超限：自动切到 3000 重试

## 子行为

<!-- section:topic -->
### `--topic=<topic>` 限定主题

仅拉取该主题相关章节，例如：
- `/get-docs react --topic=hooks`
- `/get-docs tailwindcss --topic=arbitrary-values`
- `/get-docs d3 --topic=force-directed-graph`
<!-- end -->

<!-- section:tokens -->
### `--tokens=<n>` 自定义上限

```
--tokens=8000   大型库深度文档
--tokens=3000   仅 API 速查
--tokens=1000   极简提示
```
<!-- end -->

## 输出模板

```
📚 tailwindcss 文档（来自 Context7）

## 任意值（Arbitrary Values）

[...文档原文...]

### 关键 API

```ts
// 任意值语法
<div class="top-[117px] bg-[#bada55]">
```

### 来源

- 上游：context7.com/tailwindlabs/tailwindcss.com
- 拉取时间：2026-08-08 14:32
- token 数：4200
```

## 模板变量

- `$ARGUMENTS`：用户输入的完整参数
- `$PLUGIN_NAME`：当前插件名（context7）

## 提示

- 库名不区分大小写（`React` / `react` / `REACT` 等价）
- 不需要先注册账号或 API Key
- 适合先用 `/get-docs` 拉文档，再让 AI 写代码
- 配合 `react-pro` / `tailwind-pro` 等插件使用效果最佳
