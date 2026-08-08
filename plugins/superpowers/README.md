# Superpowers

> 原插件：[obra/superpowers](https://github.com/obra/superpowers)（MIT，GitHub 123k★）

**Superpowers** 是一套完整的软件开发工作流技能库，让 AI 遵循资深工程师的纪律：先思考、再规划、后编码、必验证。

## 包含 14 个技能

| 技能 | 用途 |
|------|------|
| `brainstorming` | 创造性工作前必须使用——探索意图、需求、设计 |
| `writing-plans` | 拿到需求后写实施计划 |
| `executing-plans` | 按计划有序执行 |
| `test-driven-development` | TDD：先写测试再实现 |
| `systematic-debugging` | 系统化排错：复现→最小化→假设→修复→回归 |
| `requesting-code-review` | 完成大功能后请求代码审查 |
| `receiving-code-review` | 接审反馈时正确回应 |
| `subagent-driven-development` | 子智能体驱动开发 |
| `dispatching-parallel-agents` | 并行派发独立子任务 |
| `using-git-worktrees` | 用 worktree 隔离特性开发 |
| `finishing-a-development-branch` | 收尾开发分支 |
| `verification-before-completion` | 宣称完成前先验证 |
| `writing-skills` | 创建/编辑/校验技能 |
| `using-superpowers` | 入门指引（会话启动时自动注入） |

## 安装后行为

- 会话启动时，`using-superpowers` 技能内容自动注入上下文（见 `hooks/superpowers_hook.py`）
- 其余技能由 AI 在相关任务中自动检索匹配

## 适配说明（vs 原版）

- 14 个 `SKILL.md` 技能与官网一致，零改动
- SessionStart 注入从 bash 脚本改写为 DriFox 原生 Python hook
- Claude Code 专属的 `using-superpowers` 指令已适配 DriFox 语境

## 许可证

MIT（与上游一致）。