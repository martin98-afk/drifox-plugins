# Feature Dev

> 原插件：Anthropic 官方 [feature-dev](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/feature-dev)（MIT）

**Feature Dev** 提供完整的功能开发工作流：理解代码库 → 澄清需求 → 设计架构 → 实现 → 审查。内置三个专业智能体分工协作。

## 命令

- `/feature-dev [特性描述]` — 启动引导式功能开发流程

## 内置智能体

| 智能体 | 职责 |
|--------|------|
| `@code-explorer` | 深度分析代码库：追踪执行路径、映射架构分层 |
| `@code-architect` | 基于既有模式设计特性架构 |
| `@code-reviewer` | 审查实现：bug、逻辑错误、安全漏洞、代码质量 |

## 核心原则

- 先理解代码库，再动手
- 主动澄清所有未明确的细节，不擅自假设
- 设计优雅架构后再实现

## 适配说明

- `agents/` 与 `commands/` 与上游一致，零改动
- 命令 frontmatter 补充了 DriFox 必需的 `type: prompt` 字段

## 许可证

MIT（与上游一致）。