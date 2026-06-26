---
description: 生成符合 Conventional Commits 规范的提交消息，可指定类型、scope，支持 --amend 追加到上次提交
type: prompt
parameters:
  - name: "--amend"
    description: "追加到上次提交（git commit --amend），用于补充漏掉的文件或修改提交消息"
    param_type: flag
  - name: "--scope="
    description: "指定提交影响的模块范围，如 auth、api、ui、db、docs"
    param_type: value
  - name: "--type="
    description: "指定提交类型：feat（新功能）、fix（修复）、docs（文档）、style（格式）、refactor（重构）、perf（性能）、test（测试）、chore（杂务）、ci（CI）、revert（回退）"
    param_type: value
mutex_groups:
  mode: ["--amend"]
prompt_sections:
  --amend: "amend"
  --scope=: "scope"
  --type=: "type"
---

# /git-workflow:commit — Conventional Commits 提交消息生成

你正在处理 `/git-workflow:commit` 命令。解析 `$ARGUMENTS` 中的参数，根据当前 git diff 生成符合 Conventional Commits 规范的提交消息。

## 参数解析

解析以下参数（从 `$ARGUMENTS` 中提取）：
- `--amend`：追加到上次提交模式（此时需要 `git commit --amend --no-edit`）
- `--scope=<value>`：提取 scope 值（如未提供，分析 diff 自动推断）
- `--type=<value>`：提取 type 值（如未提供，分析 diff 自动推断）

> 如果参数为空，用户期望 AI **自动分析 diff 内容**判断 type 和 scope。

## 自动推断规则

根据 diff 内容推断 type 和 scope：

| diff 特征 | 推断 type | 常见 scope |
|-----------|-----------|-----------|
| 新增功能逻辑 | `feat` | 根据文件路径推断模块 |
| 修复 bug | `fix` | 根据出错模块 |
| 修改文档/注释 | `docs` | `docs` |
| 代码格式、空格调整 | `style` | — |
| 重构（功能不变） | `refactor` | 根据重构范围 |
| 性能优化 | `perf` | 根据优化目标 |
| 新增/修改测试 | `test` | 根据测试模块 |
| 构建脚本、依赖更新 | `chore` | `deps` |
| CI/CD 配置变更 | `ci` | `ci` |

## Conventional Commits 格式

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### 格式规则

- **type**：小写，如 `feat`、`fix`、`docs`
- **scope**：小写，可选，如 `auth`、`api`、`ui`
- **description**：
  - 使用祈使句、现在时态："add" 不是 "added"
  - 首字母小写
  - 不超过 72 字符
  - 不加句点结尾
- **body**（可选）：换行后详细说明，用祈使句
- **footer**（可选）：关联的 Issue/PR，格式 `Closes #123`

## 输出要求

<!-- section:amend -->
### --amend 追加模式

检查当前 staged changes，输出追加命令：

1. 先执行 `git diff --cached --stat` 确认已暂存的内容
2. 如果有新增 staged 内容，输出 `git commit --amend --no-edit`
3. 如果没有新增 staged 内容但用户要修改消息，输出 `git commit --amend` 后的交互提示

<!-- end -->

<!-- section:scope -->
### --scope 指定范围

在生成提交消息时强制使用提供的 scope，即使自动推断结果不同。

<!-- end -->

<!-- section:type -->
### --type 指定类型

在生成提交消息时强制使用提供的 type，即使自动推断结果不同。

<!-- end -->

## 默认行为（无 --amend）

1. **执行 `git diff --cached`** — 获取已暂存的变更内容
2. **如果没有 staged 内容**，提示用户先 `git add` 需要提交的文件
3. **分析 diff 内容**，推断 type 和 scope
4. **生成提交消息**，输出完整命令供用户确认

## 输出格式

```
✓ Conventional Commits 格式提交消息：

feat(auth): add OAuth2 login with Google provider

支持 Google 账号登录，包含 token 生成和会话管理。
Closes #42
```

```
建议执行的命令：
git commit -m "feat(auth): add OAuth2 login with Google provider" -m "Closes #42"
```

## 注意事项

- 如果 diff 涉及多个不相关的变更，提示用户拆分成多个 commit
- 如果无法推断 type，默认为 `feat`
- Scope 应基于受影响最多的模块，而非最小模块