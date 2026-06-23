# 架构

DriFox 的插件系统是一套「manifest + 组件目录」约定。任何遵循约定的目录即可被 DriFox 识别、加载并执行。

## 权威参考

> **完整的官方实现**见 DriFox 运行时的内置 `plugins/system/` 目录（不在本仓库内）。它包含 7 类组件的真实示例：
>
> - commands: `plugins/system/commands/`（12 个）
> - agents: `plugins/system/agents/`（10 个）
> - skills: `plugins/system/skills/`（25+ 个）
> - themes: `plugins/system/themes/`（11 个）
> - hooks: `plugins/system/hooks/hooks.json`
> - mcp: `plugins/system/.mcp.json`
> - lsp: `plugins/system/.lsp.json`
>
> 本仓库中的 [`plugins/example-plugin/`](../plugins/example-plugin/) 给出最小化的可工作版本；`plugins/evolver/` 给出真实生产插件。所有约定以 system 插件为准。

## 设计目标

- **零侵入**：插件不修改 DriFox 主进程，通过 manifest 暴露能力
- **七组件解耦**：commands / agents / skills / themes / hooks / mcp / lsp 互不依赖
- **目录即插件**：一个目录就是一个完整插件，便于复制、版本化、独立分发
- **可静态校验**：所有信息都集中在 `plugin.json`，可被 lint 工具独立验证

## 顶层模型

```
DriFox 启动
   │
   │  扫描 PLUGIN_DIRS（如 ~/.drifox/plugins/）
   ▼
发现所有 <plugin-name>/ 子目录
   │
   │  读取 <plugin-name>/.drifox-plugin/plugin.json
   ▼
manifest 解析层（校验 JSON Schema）
   │
   ├──► 加载 commands/<name>.md        ─── 注册为 /<name> 斜杠命令
   ├──► 加载 agents/<name>.md          ─── 注册为 @<name> 智能体
   ├──► 加载 skills/<name>/SKILL.md    ─── 注册为可被 AI 检索的技能
   ├──► 加载 themes/<theme>/*.yaml     ─── 注册主题方案
   ├──► 加载 hooks/hooks.json          ─── 在事件上挂载钩子函数
   ├──► 加载 .mcp.json                 ─── 注入 MCP 服务器
   └──► 加载 .lsp.json                 ─── 注入 LSP 语言服务器
```

详见 [plugin-registry.md](plugin-registry.md)。

## 七大组件

| 组件 | 触发方 | 用途 | 详见 |
|------|--------|------|------|
| **commands** | 用户输入 `/xx` | 显式发起工作流；支持 prompt/function/agent 三种 type | [commands.md](commands.md) |
| **agents** | 用户输入 `@xx` 或 DriFox 自动 | 限定任务域与权限的预配置 AI 工作角色 | [agents.md](agents.md) |
| **skills** | AI 自动匹配 | 注入领域知识与最佳实践 | [skills.md](skills.md) |
| **themes** | 用户 `/theme xx` | 配色方案（窗口、背景、卡片、文本等 token） | [themes.md](themes.md) |
| **hooks** | DriFox 事件 | 自动响应（拦截、记录、增强） | [hooks.md](hooks.md) |
| **mcp** | DriFox 启动 | 注册外部 MCP 服务器，扩展工具集 | [mcp.md](mcp.md) |
| **lsp** | DriFox 启动 | 注册 LSP 语言服务器，扩展代码智能 | [lsp.md](lsp.md) |

### 组件协同关系

- **commands** 给用户操作
- **agents** 给 AI 角色定位
- **skills** 让 AI 知道领域知识
- **hooks** 在后台采集数据
- **themes** 改变视觉呈现
- **mcp / lsp** 扩展运行时能力

一个完整插件通常**按需组合**，不一定全用。最小可用 = 只用 commands；完整套件 = 七件全开。

## 目录约定（强制）

```
<plugin-name>/
├── .drifox-plugin/
│   ├── plugin.json          # 必需：manifest
│   └── command_format.md    # 可选：自定义命令格式说明（仅在扩展时）
├── commands/                # 可选：当 components.commands=true
│   └── <command>.md
├── agents/                  # 可选：当 components.agents=true
│   └── <agent>.md
├── skills/                  # 可选：当 components.skills=true
│   └── <skill-name>/
│       ├── SKILL.md
│       ├── references/      # 可选：参考材料
│       ├── scripts/         # 可选：辅助脚本
│       └── examples/        # 可选：示例
├── themes/                  # 可选：当 components.themes=true
│   └── <theme-name>/
│       └── <theme-name>.yaml
├── hooks/                   # 可选：当 components.hooks=true
│   ├── hooks.json
│   └── <plugin>_hook.py
├── .mcp.json                # 可选：当 components.mcp=true（插件根）
├── .lsp.json                # 可选：当 components.lsp=true（插件根）
├── README.md                # 必需：插件说明
└── __init__.py              # 必需：标记为 Python 包
```

> **任何目录只要满足 `.drifox-plugin/plugin.json` + `README.md` + `__init__.py`，且 manifest 校验通过，就是一个合法插件。** 其它组件按需启用。

## manifest 核心字段

```json
{
  "name": "evolver",
  "description": "一句话说明插件做什么",
  "version": "1.0.0",
  "type": "user",
  "components": {
    "commands": true,
    "agents": true,
    "skills": true,
    "themes": false,
    "hooks": true,
    "mcp": false,
    "lsp": false
  }
}
```

完整字段定义见 [plugin-manifest.md](plugin-manifest.md)。

## 与 Claude Code 插件系统的差异

| 项 | Claude Code | DriFox |
|----|-------------|--------|
| manifest 目录名 | `.claude-plugin/` | `.drifox-plugin/` |
| 钩子实现语言 | shell / 内置 | Python（统一） |
| 命令类型 | prompt | **prompt / function / agent** |
| 命令 frontmatter | 标准 YAML | 扩展 frontmatter（`mutex_groups` / `parameters` / `prompt_sections`） |
| 智能体 | agents/*.md | 同 |
| 主题 | — | **themes/<name>/*.yaml** |
| 外部工具 | .mcp.json | 同 |
| 语言服务器 | — | **.lsp.json** |

## 版本兼容性

DriFox 插件 manifest 在 v1.0 内保证向后兼容。破坏性变更时：

- 升级 plugin.json 中的 `version` 主版本号
- 在 `docs/` 下加迁移指南
- 旧插件目录保留至少 1 个 minor 版本
