---
description: 检查当前 Git 分支命名是否符合规范，建议规范化命名，支持 feature/fix/hotfix/release 等前缀
type: prompt
parameters:
  - name: "--suggest"
    description: "根据当前分支名自动建议规范化命名"
    param_type: flag
  - name: "--type="
    description: "指定分支类型前缀：feature（新功能）、fix（修复）、hotfix（热修复）、release（发布）、refactor（重构）、docs（文档）"
    param_type: value
mutex_groups:
  mode: ["--suggest"]
prompt_sections:
  --suggest: "suggest"
  --type=: "type"
---

# /git-workflow:branch — Git 分支命名检查与建议

你正在处理 `/git-workflow:branch` 命令。检查当前分支命名是否符合团队约定，并提供规范化建议。

## 执行流程

1. **执行 `git branch --show-current`** — 获取当前分支名
2. **执行 `git status`** — 确认工作区状态（可选，了解是否有未提交的变更）
3. **检查分支命名** — 按规范验证当前分支名
4. **生成建议** — 如有不规范，给出修正方案

## 分支命名规范

### 合法前缀

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feature/` | 新功能开发 | `feature/user-auth`, `feature/add-dashboard` |
| `fix/` | Bug 修复 | `fix/login-crash`, `fix/memory-leak` |
| `hotfix/` | 紧急热修复 | `hotfix/critical-security`, `hotfix/prod-outage` |
| `release/` | 发布准备 | `release/v1.2.0`, `release/q4-milestone` |
| `refactor/` | 重构 | `refactor/extract-service`, `refactor/cleanup-utils` |
| `docs/` | 文档更新 | `docs/api-guide`, `docs/update-readme` |
| `test/` | 测试相关 | `test/integration`, `test/performance` |
| `chore/` | 杂务 | `chore/upgrade-deps`, `chore/cleanup` |

### 命名规则

- 使用 **kebab-case**：`feature/user-auth` 而不是 `feature/userAuth` 或 `feature/user_auth`
- 分支描述应简洁、有意义，长度不超过 50 字符
- 不使用个人名字作为分支名
- 不使用中文

## 检查逻辑

<!-- section:suggest -->
### --suggest 建议模式

自动分析当前分支名：
1. 如果已符合规范，输出 ✅ 通过
2. 如果缺少前缀，建议添加合适的前缀
3. 如果使用了不推荐的前缀，建议替换
4. 输出完整的规范化分支名和重命名命令

<!-- end -->

<!-- section:type -->
### --type 指定类型

根据用户指定的类型前缀重新生成分支名建议：
- 如果当前分支没有前缀 → 建议添加 `--type` 指定的前缀
- 如果当前分支有前缀但与 `--type` 不符 → 建议替换
- 输出重命名命令：`git branch -m <old> <new>`

<!-- end -->

## 默认检查行为

无参数时，按以下优先级检查：

1. **是否有合法前缀**？没有 → 输出警告和建议
2. **是否符合 kebab-case**？不符合 → 输出警告
3. **是否过长**（>50字符）？是 → 输出警告
4. **是否包含中文字符**？是 → 输出警告

## 输出格式

### 规范情况

```
✅ 分支命名检查通过

当前分支：feature/user-auth
规范前缀：feature/ ✅
命名格式：kebab-case ✅
长度：17 字符 ✅

无需修改。
```

### 不规范情况

```
⚠️ 分支命名不符合规范

当前分支：user_login_feature
问题：
  ❌ 缺少规范前缀（应为 feature/、fix/ 等）
  ❌ 使用了下划线分隔（应为 kebab-case）

建议命名：
  feature/user-login

重命名命令：
  git branch -m user_login_feature feature/user-login

（如果当前已在目标分支）
  git branch -m feature/user-login
```

## 注意事项

- 如果用户当前不在要重命名的分支上，提醒先切换分支
- 如果分支已推送到远程，需要额外执行 `git push origin -u <new-name>` 和 `git push origin --delete <old-name>`
- 检查前先执行 `git branch` 确认当前分支状态