# Code Simplifier

> 原插件：Anthropic 官方 [code-simplifier](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/code-simplifier)（MIT）

**Code Simplifier** 是一个代码简化重构智能体（`@code-simplifier`）：在不改变功能的前提下，简化、精炼代码，提升清晰度、一致性、可维护性。

## 用法

```
@code-simplifier 简化 src/utils/parser.py
```

默认聚焦最近修改的代码，也可显式指定文件。

## 工作方式

- 应用项目自身的最佳实践与既有风格
- 消除重复、简化分支、精炼命名
- **严格保持功能不变**（不引入行为变更）

## 适配说明

与上游一致，零改动。`agents/code-simplifier.md` 遵循 DriFox agent frontmatter 约定。

## 许可证

MIT（与上游一致）。