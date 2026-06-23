# agents 组件

agents 是 AI 视角的「预配置工作角色」。每个 agent 是 `agents/<name>.md`，DriFox 通过 `@<name>` 引用或自动选择。

## 文件位置

```
<plugin-name>/
└── agents/
    ├── build.md            # @build
    ├── explore.md          # @explore
    └── code-reviewer.md    # @code-reviewer
```

文件名（不含 `.md`）即为智能体名。

## 最小示例

```markdown
---
description: 快速代码探索智能体，深入分析代码库
mode: subagent
steps: 30
permission:
  write: deny
  edit: deny
  "*": allow
---

# Role

你是一个代码探索专家...

# Primary Goal
- 项目结构分析
- 代码理解
```

## frontmatter 字段

### 必填

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 智能体描述，显示在 `@` 引用列表中 |

### 选填

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mode` | enum | `all` | `all` / `subagent` / `primary` |
| `steps` | int | 30 | 最大执行步数（防止失控） |
| `temperature` | float | 默认 | 模型温度参数 |
| `hidden` | bool | false | 不显示在 `@` 引用列表中 |
| `permission` | dict | 全允许 | 工具权限白/黑名单 |

## 三种 mode

| mode | 说明 |
|------|------|
| `all` | 任何上下文都可使用（主对话 + 子智能体） |
| `subagent` | 仅可作为子智能体被主对话调用，不能直接 `@` 引用 |
| `primary` | 仅作主对话的工作角色，**不能**被 subagent_para 等派发 |

典型用法：

- `mode: subagent`：限定任务域的专家（如 `explore`、`code-reviewer`、`test-engineer`）
- `mode: all`：通用工具（如 `build`）
- `mode: primary`：主对话专用（如某些只与人交互的智能体）

## permission 权限

```yaml
permission:
  write: deny       # 禁止写文件
  edit: deny        # 禁止 edit
  multi_edit: deny  # 禁止 multi_edit
  bash: deny        # 禁止 shell
  question: deny    # 禁止向用户提问
  subagent_para: deny  # 禁止派发子任务
  "*": allow        # 其它工具全部允许
```

支持的工具键（与 DriFox runtime 对齐）：

- 文件类：`read`、`write`、`edit`、`multi_edit`、`glob`、`grep`
- 执行类：`bash`
- 流程类：`todowrite`、`todoread`、`subagent_para`、`subagent_dag`、`question`、`keyboard`、`mouse`、`screenshot`、`webfetch`、`websearch`、`upload_file`、`stage_files`
- 元工具类：`skill`、`mcp__*`、`lsp`
- 通配符：`*`（其它未列出的工具）

值：`allow` | `deny`。`deny` 优先级高于 `allow`。

## hidden

设为 `true` 时不显示在 `@` 引用列表中，但仍可被自动选择或显式 `@` 触发。适合：
- 实验性智能体
- 仅作为子智能体使用的工具（结合 `mode: subagent`）

## steps 步数限制

智能体执行步数（一次回复中允许的工具调用次数）。超过会强退。典型值：
- 只读探索：`30`
- 编码构建：`100`
- 审查类：`20`

## 模板变量

智能体正文可使用：

| 变量 | 含义 |
|------|------|
| `$PLUGIN_NAME` | 当前插件名 |
| `$PLUGIN_DIR` | 插件根目录绝对路径 |

## 校验

- 文件名必须 `^[a-z][a-z0-9-]*\.md$`
- frontmatter 必填 `description`
- `mode`（如存在）必须是 `all`/`subagent`/`primary`
- `steps`（如存在）必须是整数
- `hidden`/`temperature` 类型对应

## 与 commands / skills 的区别

| 维度 | commands | agents | skills |
|------|----------|--------|--------|
| 触发方 | 用户 `/xx` | 用户 `@xx` 或 DriFox 派发 | AI 自动匹配 |
| 角色定位 | 一次性工作流 | 长期角色 | 临时知识 |
| 权限粒度 | 命令级 | 工具级 | 无 |
| 执行上下文 | 主对话 | 主对话/子智能体 | 注入到当前上下文 |

**推荐组合**：commands 显式触发 → agents 承担工作 → skills 提供领域知识。
