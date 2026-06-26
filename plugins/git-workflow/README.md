# git-workflow 插件 — DriFox 官方插件

将 Git 工作流最佳实践集成到 DriFox，覆盖分支命名、提交规范、PR 描述生成三大场景，让团队协作自动化。

## 功能

| 功能 | 说明 |
|------|------|
| 📋 **提交生成** | `/git-workflow:commit` 根据 diff 生成符合 Conventional Commits 规范的提交消息 |
| 🌿 **分支检查** | `/git-workflow:branch` 检查当前分支命名是否符合约定，建议规范化命名 |
| 📝 **PR 模板** | `/git-workflow:pr` 根据分支 commits 自动生成 PR 描述模板 |
| 🔍 **提交校验** | Hook 在 `git commit` 前自动检查消息格式，不合规则警告 |

## 安装

插件位于 `plugins/git-workflow/`，DriFox 启动时自动发现（需在 `~/.drifox/plugins/` 下有对应目录）。

验证加载：

```
/git-workflow:branch
```

看到分支检查结果即表示插件正常工作。

## 目录结构

```
plugins/git-workflow/
├── .drifox-plugin/         # 插件清单
│   └── plugin.json
├── __init__.py             # Python 包标记
├── README.md               # 本文件
├── commands/
│   ├── commit.md           # /git-workflow:commit — 生成提交消息
│   ├── branch.md           # /git-workflow:branch — 分支命名检查
│   └── pr.md               # /git-workflow:pr — PR 模板生成
├── hooks/
│   ├── hooks.json          # Hook 配置
│   └── git-workflow_hook.py # PreToolUse 钩子实现
└── skills/
    └── git-workflow/       # Git 工作流最佳实践
        └── SKILL.md
```

## 命令列表

| 命令 | 说明 | 触发词 |
|------|------|--------|
| `/git-workflow:commit` | 生成 Conventional Commits 格式的提交消息 | commit、提交、git commit |
| `/git-workflow:branch` | 检查并建议分支命名规范 | branch、分支、git branch |
| `/git-workflow:pr` | 根据 commits 生成 PR 描述模板 | pr、pull request、PR |

### `/git-workflow:commit`

生成符合 Conventional Commits 规范的提交消息。

**参数：**
- `--amend` — 追加到上次提交（`git commit --amend`）
- `--scope=<scope>` — 指定 scope（如 `auth`、`api`）
- `--type=<type>` — 指定类型（`feat`/`fix`/`docs`/`style`/`refactor`/`test`/`chore`）

**使用示例：**
```
/git-workflow:commit --type=feat --scope=auth
/git-workflow:commit --amend
/git-workflow:commit --type=fix --scope=ui
```

### `/git-workflow:branch`

检查当前分支命名是否符合约定，建议规范化命名。

**分支类型前缀：**
- `feature/` — 新功能开发
- `fix/` — Bug 修复
- `hotfix/` — 紧急热修复
- `release/` — 发布准备
- `refactor/` — 重构
- `docs/` — 文档更新

### `/git-workflow:pr`

根据当前分支与目标分支之间的 commits 自动生成 PR 描述模板，包含：变更类型、解决的问题、测试说明。

## Hook 事件列表

| 事件 | 触发时机 | 功能 |
|------|----------|------|
| `PreToolUse` | 工具执行前 | 检测 `git commit` 命令，验证提交消息格式 |

## Conventional Commits 规范

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### 类型（type）

| 类型 | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(auth): add OAuth2 login` |
| `fix` | Bug 修复 | `fix(api): handle null response` |
| `docs` | 文档更新 | `docs(readme): update install guide` |
| `style` | 代码格式（不影响功能） | `style(ui): format button padding` |
| `refactor` | 重构（不修复 bug 不加新功能） | `refactor(core): extract validator` |
| `perf` | 性能优化 | `perf(db): add index on user_id` |
| `test` | 测试相关 | `test(api): add unit tests for login` |
| `chore` | 构建/工具/依赖 | `chore: upgrade pytest to 8.0` |
| `ci` | CI/CD 配置 | `ci: add GitHub Actions lint` |
| `revert` | 回退提交 | `revert: undo feat(auth)` |

### Scope 约定

Scope 通常是受影响的模块名：`auth`、`api`、`ui`、`db`、`cli`、`docs`。

### 描述（description）

- 使用祈使句、现在时态："add" 而不是 "added" / "adds"
- 首字母小写，不加句点
- 不超过 72 字符