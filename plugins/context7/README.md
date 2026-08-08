# context7

> 实时拉取任意库的最新 API 文档与代码示例到上下文窗口，省去贴文档链接。

源自 [upstash/context7](https://github.com/upstash/context7)，Helloianneo/awesome-claude-code-skills **必装 Top 10** 第 2 名、intellectronica 出品。

## 作用

当 AI 需要调用某个库（React、Vue、Tailwind、Three.js、Stripe、Supabase …）时，**不必把文档链接贴进对话**，context7 会自动：
1. 解析库名（去除 `get_` / `how to` 等修饰）
2. 从 context7.com 拉取该库最新版本 API 文档
3. 注入到当前上下文中
4. AI 基于真实文档生成代码

## 安装

```bash
# 1. 复制到 ~/.drifox/plugins/
cp -r plugins/context7 ~/.drifox/plugins/

# 2. 通过 marketplace 安装
/plugin marketplace add martin98-afk/drifox-plugins
/plugin install context7@drifox-official
```

无需 API Key，本地 `npx` 直跑。

## 命令

| 命令 | 用途 |
|------|------|
| `/get-docs <library>` | 拉取并展示 `<library>` 的最新文档 |
| `/get-docs <library> --topic=<topic>` | 仅拉取指定 topic 的文档片段 |

## MCP 工具

启用本插件后，会自动注册 `context7` MCP 工具集，AI 可直接调用：

- `resolve-library-id` — 把用户给的库名解析为 context7 ID（去修饰词）
- `get-library-docs` — 按 ID + 主题 + token 上限拉文档

## 典型用法

**用户**：用 React Query 写一个无限滚动列表

**AI 调用**：
```
mcp__context7__resolve-library-id("react query") → "/tanstack/query"
mcp__context7__get-library-docs("/tanstack/query", topic="useInfiniteQuery", tokens=5000)
```

返回 5000 tokens 的最新文档 + 示例代码，AI 据此生成代码。

## 触发关键词

`context7`、`拉文档`、`查 API`、`最新文档`、`library docs`、`API 文档`、`实时文档`

## 许可

MIT（Context7 本身）+ GPL-3.0-or-later（DriFox 适配层）
