# ECC — Everything Claude Code

> 原插件：[affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code)（MIT，GitHub 25k★，Anthropic 黑客松冠军）

**ECC** 是社区最全面的 AI 工程工作流集合：67 个专业智能体、284 个领域技能、94 个开发命令，覆盖工程全生命周期。

## 内容总览

| 类别 | 数量 | 说明 |
|------|------|------|
| **agents** | 67 | `@architect` `@code-reviewer` `@doc-updater` `@e2e-runner` 等专业角色（masm 深度 2 级） |
| **skills** | 284 | 领域技能：TDD、调试、架构、API 设计、后端模式、前端、测试、安全、文档等 |
| **commands** | 94 | `/code-review` `/build-fix` `/ecc-guide` `/checkpoint` /`evolve` 等开发命令 |

代表性能力：

- **工程方法论**：TDD、基准测试、agent 评估、AI 回归测试
- **多语言覆盖**：Go/Rust/Java/C++/PyThon/Flutter/Dart 等 build/review/test 命令
- **质量保障**：代码审查、错误处理、架构审计、e2e 测试
- **文档与沟通**：文章写作、品牌、文档更新、邮件处理

## 适配说明

- **提示词层**（agents/skills/commands）完整移植，与上游一致
- 所有命令已补齐 DriFox 必需的 `type: prompt` frontmatter
- 5 个技能目录名与 `name` 字段对齐（scientific-* 系列）
- **hooks 未移植**：上游 hooks 为解析式 node 内联脚本，强依赖 Claude Code 特有环境变量（`CLAUDE_PLUGIN_ROOT`）与运行时，DriFox 下不适用
- 部分命令正文含 Claude 特有路径说明（`~/.claude/*`），DriFox 下按需替换为自身配置目录即可

## 许可证

MIT（与上游一致）。