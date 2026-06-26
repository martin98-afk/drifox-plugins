---
description: 根据当前分支与目标分支之间的 commits 自动生成 PR 描述模板，包含变更摘要、解决的问题、测试说明
type: prompt
parameters:
  - name: "--target="
    description: "指定 PR 目标分支（默认从当前分支名推断，如 feature/* → develop）"
    param_type: value
  - name: "--base="
    description: "PR 的基础分支，如 main、master、develop"
    param_type: value
  - name: "--template="
    description: "使用指定模板：simple（简单）、detailed（详细）、changelog（变更日志风格）"
    param_type: value
prompt_sections:
  --target=: "target"
  --base=: "base"
  --template=: "template"
---

# /git-workflow:pr — PR 描述模板生成

你正在处理 `/git-workflow:pr` 命令。根据当前分支与目标分支之间的 commits，自动生成规范的 PR（Pull Request）描述模板。

## 执行流程

1. **获取当前分支**：`git branch --show-current`
2. **推断目标分支**：根据分支前缀推断（feature/* → develop，hotfix/* → main 等）
3. **获取 commits**：`git log <base>..HEAD --oneline`
4. **分析每个 commit**：识别 type、scope、描述
5. **生成 PR 模板**：按选定模板格式输出

## 分支到目标分支映射

| 当前分支前缀 | 默认目标分支 |
|-------------|-------------|
| `feature/` | `develop` |
| `fix/` | `develop` 或 `main` |
| `hotfix/` | `main` |
| `release/` | `main` |
| `refactor/` | `develop` |
| `docs/` | `develop` |

> 如果用户通过 `--base` 明确指定目标分支，以用户指定的为准。

## Commit 分析

分析从 base 到 HEAD 的每个 commit：

```bash
git log <base>..HEAD --format="%s%n%b---COMMIT_END---"
```

识别每个 commit 的：
- **type**：从消息开头提取（feat、fix、docs 等）
- **scope**：圆括号中的内容
- **description**：type(scope) 之后的部分

## PR 模板格式

<!-- section:target -->
### --target 指定目标分支

将指定的分支作为 PR 目标分支：
- 执行 `git log <target>..HEAD` 获取变更 commits
- 在模板中填入正确的目标分支名

<!-- end -->

<!-- section:base -->
### --base 指定基础分支

使用用户指定的分支作为 base：
- 直接使用 `--base` 的值作为基准分支
- 覆盖默认推断逻辑

<!-- end -->

<!-- section:template -->
### --template 选择模板风格

**simple（默认）**：简洁版，适合小型变更
```
## 变更摘要
- feat(auth): add Google OAuth login
- fix(ui): correct button alignment

## 测试
- [ ] 本地测试通过
- [ ] 覆盖新增功能的测试
```

**detailed**：详细版，适合重要变更
```
## 概述
一句话说明这个 PR 做什么

## 变更详情
### 新增
- feat(auth): add Google OAuth login

### 修复
- fix(ui): correct button alignment

## 测试
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 手动验证场景 X

## 截图（如有 UI 变更）
<!-- 截图位置 -->

## 相关 Issue
Closes #42
```

**changelog**：变更日志风格，适合 release PR
```
## changelog

### ✨ 新功能
- feat(auth): add Google OAuth login (#45)

### 🐛 修复
- fix(ui): correct button alignment (#44)
```

<!-- end -->

## 默认行为（无参数）

1. 自动推断当前分支和目标分支
2. 使用 `simple` 模板
3. 分析 commits 生成 PR 描述

## 输出格式

```
📋 PR 描述模板

---

## 变更摘要
- feat(auth): add OAuth2 login with Google provider
- fix(ui): correct login button padding on mobile
- docs(readme): update installation guide

## 解决的问题
<!-- 描述这个 PR 解决了什么问题 -->

## 测试说明
- [ ] 本地测试通过
- [ ] 新增功能有单元测试覆盖
- [ ] 手动验证登录流程

## 相关截图（如有 UI 变更）
<!-- 截图位置 -->

## 相关 Issue
Closes #42

---

建议命令：
gh pr create --base develop --title "feat(auth): add Google OAuth login" --body-file pr-template.md
```

## 注意事项

- 如果当前分支没有 commits，提示用户先提交代码
- 如果有大量 commits（>20），提示可能需要 squash 或拆分成多个 PR
- 如果 commit 消息不符合 Conventional Commits，生成时给出警告
- 提供 `gh pr create` 命令示例（如系统有 gh CLI）