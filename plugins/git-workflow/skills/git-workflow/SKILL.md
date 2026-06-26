---
name: git-workflow
description: Git 工作流最佳实践技能 — 处理 commit 规范、branch 命名、PR 模板、Conventional Commits 相关问题。触发关键词：git commit、提交规范、branch 分支、PR pull request、conventional commits、git workflow、提交消息格式、分支命名规范。
---

# Git 工作流最佳实践

本技能为 DriFox 提供 Git 工作流相关的领域知识，确保 AI 在处理 Git 相关任务时遵循团队约定。

## Conventional Commits 规范

### 格式

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### 类型（type）参考表

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `feat` | 新功能 | 添加用户登录功能 |
| `fix` | Bug 修复 | 修复登录崩溃问题 |
| `docs` | 文档 | 更新 README |
| `style` | 代码格式 | 调整缩进、空格 |
| `refactor` | 重构 | 提取公共方法 |
| `perf` | 性能优化 | 添加索引、优化查询 |
| `test` | 测试 | 新增单元测试 |
| `chore` | 杂务 | 升级依赖版本 |
| `ci` | CI/CD | 配置 GitHub Actions |
| `revert` | 回退 | 回退某个提交 |

### Scope 命名

Scope 应使用受影响模块的短名称（kebab-case）：

| 场景 | 建议 Scope |
|------|-----------|
| 认证相关 | `auth`、`login`、`oauth` |
| API 相关 | `api`、`rest`、`graphql` |
| UI 相关 | `ui`、`components`、`styles` |
| 数据库相关 | `db`、`migration`、`models` |
| 文档相关 | `docs`、`readme`、`changelog` |
| 通用/跨模块 | 不使用 scope |

### Description 规则

- **祈使句**：使用 "add" 而不是 "added" / "adds"
- **现在时态**：描述代码变更，而非已完成的事件
- **首字母小写**：description 部分首字母小写
- **不超过 72 字符**：单行描述长度限制
- **不添加句点**：描述行末尾不加句号

### 正确示例

```
feat(auth): add Google OAuth login
fix(api): handle null response in user endpoint
docs: update installation guide
refactor(core): extract validation logic to utility
perf(db): add index on user_id column
```

### 错误示例

```
Added new feature for user login        ❌ 过去式
FEAT(auth): Add login feature           ❌ 大写 type
feat: 新增登录功能                       ❌ 中文描述
feat(authentication): added login       ❌ scope 过长 + 过去式
feat: A new feature that allows users to log in with their credentials and provides session management. ❌ 过长
```

## 分支命名约定

### 命名格式

```
<type>/<short-description>
```

### 合法前缀

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feature/` | 新功能开发 | `feature/user-auth`、`feature/add-dashboard` |
| `fix/` | Bug 修复 | `fix/login-crash`、`fix/memory-leak` |
| `hotfix/` | 紧急热修复 | `hotfix/security-patch`、`hotfix/prod-outage` |
| `release/` | 发布准备 | `release/v1.2.0`、`release/q4-milestone` |
| `refactor/` | 重构 | `refactor/extract-service`、`refactor/cleanup-utils` |
| `docs/` | 文档更新 | `docs/api-guide`、`docs/update-readme` |
| `test/` | 测试相关 | `test/integration`、`test/performance` |
| `chore/` | 杂务 | `chore/upgrade-deps`、`chore/cleanup` |

### 命名规则

- **kebab-case**：`feature/user-auth` 而非 `feature/userAuth` 或 `feature/user_auth`
- **简洁描述**：分支描述应简洁，长度不超过 50 字符
- **无个人标识**：不包含个人名字或昵称
- **纯 ASCII**：不使用中文字符

### 错误示例

```
master                      ❌ 过时命名
main-dev                    ❌ 非标准命名
feature/UserAuth            ❌ PascalCase
feature/user_auth           ❌ snake_case
新功能/用户登录              ❌ 中文
feature-login               ❌ 缺少分隔符
very-long-branch-name-here  ❌ 过长
```

## PR 模板格式

### 基础模板

```markdown
## 变更摘要
<!-- 简要说明这个 PR 做了什么 -->

## 变更详情
<!-- 详细说明变更内容 -->

## 测试
- [ ] 本地测试通过
- [ ] 新增功能有测试覆盖
- [ ] 手动验证场景

## 截图（如有 UI 变更）
<!-- 截图 -->

## 相关 Issue
Closes #123
```

### Release PR 模板

```markdown
## Changelog

### ✨ 新功能
<!-- 新功能列表 -->

### 🐛 修复
<!-- 修复列表 -->

### ⚠️ Breaking Changes
<!-- 破坏性变更 -->
```

## 常见反模式

### Commit 反模式

1. **提交信息模糊**
   - ❌ `update code`、`fix stuff`、`changes`
   - ✅ `feat(api): add pagination to user list`

2. **提交粒度过大**
   - ❌ 一个 commit 包含多个不相关功能
   - ✅ 每个 commit 只做一件事

3. **提交信息包含实现细节**
   - ❌ `changed for-loop to map in userService.js`
   - ✅ `refactor(user): use map instead of for-loop for better readability`

4. **提交中包含无关变更**
   - ❌ commit 中同时有功能代码和格式化改动
   - ✅ 功能代码和格式化代码分开提交

### Branch 反模式

1. **长期存在的特性分支**
   - ❌ `feature/xyz` 存在超过 2 周
   - ✅ 频繁 rebase 到 main/develop，小步合并

2. **在 main/master 直接开发**
   - ❌ 直接在 main 分支修改代码
   - ✅ 所有变更通过特性分支

3. **分支命名随意**
   - ❌ `dev`、`test`、`my-work`
   - ✅ `feature/xxx`、`fix/xxx`

### PR 反模式

1. **PR 过大**
   - ❌ 一个 PR 超过 1000 行代码
   - ✅ 拆分多个小 PR，每个 PR 不超过 300 行

2. **缺少描述**
   - ❌ PR 描述为空或仅 "fixes bug"
   - ✅ 完整的变更说明、测试结果

3. **不审查自己提交**
   - ❌ 自己合并自己的 PR
   - ✅ 至少一人 review 后再合并