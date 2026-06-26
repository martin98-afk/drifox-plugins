# commands 组件

commands 是用户视角的入口。每个命令对应一个 `commands/<name>.md` 文件，渲染为 `/<name>` 斜杠命令。

## 文件位置

```
<plugin-name>/
└── commands/
    ├── hello.md          # 注册为 /hello
    ├── plugin.md         # 注册为 /plugin
    └── compact.md        # 注册为 /compact
```

文件名（不含 `.md`）即为命令名。

## 最小示例

```markdown
---
description: 一句话说明命令做什么
type: prompt
---

# /hello 命令

你正在处理 `/hello` 命令。

## 行为

1. 第一步做什么
2. 第二步做什么
```

## 完整 frontmatter 字段

### 必填

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 命令简介，显示在命令卡片和 `/help` 中 |
| `type` | enum | `prompt` \| `function` \| `agent` |

### 选填

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `argument-hint` | dict | 无 | 旧式参数提示（用 `parameters` 替代） |
| `parameters` | list | 无 | **结构化参数定义**（新格式，推荐） |
| `mutex_groups` | dict | 无 | 互斥组，同组参数只能选其一 |
| `prompt_sections` | dict | 无 | **参数→提示词分段映射**（核心） |
| `shortcut` | string | 无 | 快捷键，如 `Ctrl+Shift+C` |
| `allowed-tools` | list | 无 | 工具白名单（旧） |
| `tools` | list/dict | 无 | 工具白名单 |
| `permission` | dict | 无 | 权限配置（`deny` 模式） |
| `hidden` | bool | false | 设为 true 时不显示在命令卡片中 |

## 三种 type

| 类型 | 说明 | 触发方式 |
|------|------|---------|
| `prompt` | 提示词替换命令。body + 选中段拼装后发送给 AI | 用户输入 `/xx` |
| `function` | 函数型命令。触发 Python 处理器，**不**发送给 AI | 用户输入 `/xx` |
| `agent` | 同 `prompt`，额外支持 `--subagent` 子智能体模式 | 用户输入 `/xx` |

## 参数定义（parameters）

### 数组格式（推荐）

```yaml
parameters:
  - name: "--quick"
    description: "快速模式"
    param_type: flag
    mutex: mode

  - name: "--save-to="
    description: "输出路径"
    param_type: value

  - name: "<query>"
    description: "搜索关键词"
    param_type: positional
```

### param_type

| 值 | 说明 | 示例输入 |
|----|------|---------|
| `flag` | 开关参数，无值 | `--quick` |
| `value` | 带值参数 | `--save-to=report.md` |
| `positional` | 位置参数 | 无前缀的文本 |

### value_options（枚举值列表）

`value` 类型参数可声明 `value_options` 枚举值列表。声明后，DriFox 会在用户输入该参数前缀时**自动弹出可选值列表**，支持实时搜索过滤。

```yaml
parameters:
  - name: "--language="
    description: "安装指定语言的 LSP"
    param_type: value
    value_options:
      - python
      - typescript
      - rust
      - go
      - cpp
```

**效果**：
- 用户输入 `/lsp-install --lan` 时自动弹出语言列表
- 用户输入 `--language=py` 时列表实时过滤为包含 `py` 的选项
- 用户点击列表项或按 Tab 选中后，值自动补全到输入框

**规则**：
- 仅 `param_type: value` 的参数支持 `value_options`
- 列表为空或不声明时，该参数不触发值选择 UI
- `--model=` 参数特殊处理：使用运行时动态数据源（非静态列表），不需要声明 `value_options`
- 也支持 `enum` 作为 `value_options` 的兼容别名

### 简化格式（argument-hint，兼容旧版）

```yaml
argument-hint:
  "[--quick]": "快速模式"
  "[--save-to=]": "输出路径"
  "[<query>]": "搜索主题"
```

`[]` → 可选参数，`=` 结尾 → 带值参数。

## 互斥组（mutex_groups）

同组参数互斥，只取第一个匹配的：

```yaml
mutex_groups:
  mode: ["--quick", "--thorough", "--deep"]
  output: ["--markdown", "--html"]
```

**效果**：
- `/v --tests --build` → 不同组 → **都追加**对应 sections
- `/v --quick --deep` → 同 `mode` 组 → **只追加 --quick** section

> `prompt_sections` 选择也遵循此互斥规则。

## prompt_sections：参数→提示词分段

### YAML 格式

`prompt_sections` 的值是**短引用字符串**：

```yaml
prompt_sections:
  --tests: "tests"
  --build: "build"
  --all: "all"
```

### body 标记语法

在正文中，每段参数相关的内容用 `<!-- section:id -->` 和 `<!-- end -->` 包裹：

```markdown
公共内容（始终发送）……

<!-- section:tests -->
## 测试验证
测试流程指令……
<!-- end -->

<!-- section:build -->
## 构建验证
构建流程指令……
<!-- end -->
```

### 装配规则

| 用户输入 | 发送给 AI 的内容 |
|----------|-----------------|
| `/verify`（无参数） | 完整 body |
| `/verify --tests` | 公共部分 + `--tests` 段 |
| `/verify --tests --build` | 公共部分 + `--tests` 段（mode 互斥） |
| `/verify --quick --html` | 公共部分 + `--quick` + `--html` 段（不同组叠加） |

完整规范见 [DriFox 文档（.drifox-plugin/command_format.md）](../plugins/system/.drifox-plugin/command_format.md)（在 system 插件中）。

## 工具限制

```yaml
# 白名单
allowed-tools:
  - Read
  - Glob
  - Grep

# Deny 模式
permission:
  question: deny
  subagent_para: deny
```

## hidden

设为 `true` 时不显示在命令卡片中，但仍可通过 `/xx` 调用。适合内部命令或父命令。

## 模板变量

命令正文可使用以下变量，运行时替换：

| 变量 | 含义 |
|------|------|
| `$ARGUMENTS` | 用户在命令后输入的完整参数 |
| `$PLUGIN_NAME` | 当前插件名 |
| `$PLUGIN_DIR` | 插件根目录的绝对路径 |
| `$PROJECT_ROOT` | 当前工作项目根目录 |

## 校验

- 文件名必须 `^[a-z][a-z0-9-]*\.md$`
- frontmatter 必填字段缺失时报错
- `type` 必须是 `prompt` / `function` / `agent`
- 引用的 `prompt_sections` 段必须在正文里能找到对应 `<!-- section:xxx -->` 标记
- `parameters` 列表中每项必须是 dict，且 `param_type`（如存在）必须是 `flag`/`value`/`positional`
- `value_options`（如存在）必须是 list，且仅在 `param_type: value` 时有效
