---
description: 向用户打招呼并展示当前插件信息（最小命令示例，使用完整 frontmatter）
type: prompt
parameters:
  - name: "--quiet"
    description: "安静模式：只显示一行问候"
    param_type: flag
  - name: "--name="
    description: "指定要问候的名字"
    param_type: value
  - name: "<topic>"
    description: "可选，附加话题（如 plugins、hooks）"
    param_type: positional
mutex_groups:
  style: ["--quiet"]
shortcut: Ctrl+Shift+H
allowed-tools:
  - read
  - glob
  - grep
hidden: false
---

# /hello 命令 — DriFox 插件最小命令示例

你正在处理 `/hello` 命令。这是最小命令示例，**演示完整 frontmatter 写法**。

## 📋 执行规则

1. **解析参数**：识别 `--quiet`、`--name=<value>`、`<topic>` 三种形式
2. **如果没有传 `--name=`**，使用 `$PROJECT_ROOT` 的目录名作为问候对象
3. **如果没有传 `<topic>`**，输出当前插件的 7 类组件清单
4. **所有输出必须明确告诉用户这是 example-plugin 在演示**

## 子行为

<!-- section:quiet -->
### `--quiet` 安静模式

仅输出一行 `Hello, <name>!`，省略组件清单。
<!-- end -->

## 默认行为

未传 `--quiet` 时，按以下结构输出：

```
👋 Hello, <name>!
来自 example-plugin v1.0.0

已启用组件：
  - commands  ✅
  - agents    ✅
  - skills    ✅
  - themes    ✅
  - hooks     ✅
  - mcp       ✅
  - lsp       ✅
```

如果有 `<topic>`，附加一段该 topic 的简介（如 `topic=hooks` 时简述 hooks 是什么）。

## 模板变量

本命令可用变量：
- `$ARGUMENTS`：用户输入的完整参数
- `$PLUGIN_NAME`：当前插件名（example-plugin）
- `$PROJECT_ROOT`：当前工作项目根目录

## 派生

派生一个新插件时，请参考 `plugins/example-plugin/README.md` 派生章节。

> 这是 `type: prompt` 风格的命令，整个 markdown 作为系统提示注入给 AI。
> 详细规范见 `docs/commands.md`。
