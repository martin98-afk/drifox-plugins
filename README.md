# DriFox 插件生态

[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)

DriFox 的官方插件仓库。每个插件是一个独立、可热插拔的扩展单元，提供 7 类能力：

- **commands** — 斜杠命令（`/xx`）
- **agents** — 智能体（`@xx`）
- **skills** — AI 技能（自动匹配）
- **themes** — 主题方案
- **hooks** — 事件钩子
- **mcp** — MCP 服务器配置
- **lsp** — LSP 语言服务器配置

> **DriFox** 是一个 AI Agent 运行时（参考 Claude Code 的定位）。本仓库用于托管 DriFox 生态的官方插件。

## 权威参考

完整的官方实现见 DriFox 运行时的内置 `plugins/system/` 目录（不在本仓库）。它包含全部 7 类组件的真实示例：

| 组件 | 数量 | 位置 |
|------|------|------|
| commands | 12 | `plugins/system/commands/` |
| agents | 10 | `plugins/system/agents/` |
| skills | 25+ | `plugins/system/skills/` |
| themes | 11 | `plugins/system/themes/` |
| hooks | 1 配置 | `plugins/system/hooks/hooks.json` |
| mcp | 4 server | `plugins/system/.mcp.json` |
| lsp | 1 server | `plugins/system/.lsp.json` |

所有约定以 system 插件为准；本仓库的 `example-plugin` 是最小化可工作版本，`evolver` 是真实生产插件。

## 仓库结构

```
drifox-plugins/
├── README.md                        # 本文件
├── AGENTS.md                        # AI Agent 开发规约
├── CONTRIBUTING.md                  # 插件贡献指南
├── LICENSE                          # GPL-3.0-or-later
├── docs/                            # 架构与组件规范
│   ├── architecture.md              # 插件系统整体架构
│   ├── plugin-manifest.md           # plugin.json 字段定义
│   ├── plugin-development.md        # 从零开发一个插件
│   ├── plugin-registry.md           # DriFox 如何发现与加载插件
│   ├── commands.md                  # commands 组件规范
│   ├── agents.md                    # agents 组件规范
│   ├── skills.md                    # skills 组件规范
│   ├── themes.md                    # themes 组件规范
│   ├── hooks.md                     # hooks 组件规范
│   ├── mcp.md                       # mcp 组件规范
│   └── lsp.md                       # lsp 组件规范
├── schemas/
│   └── plugin.schema.json           # .drifox-plugin/plugin.json 的 JSON Schema
├── tools/
│   └── validate_plugins.py          # 校验所有插件 manifest
└── plugins/                         # 官方插件集合
    ├── README.md                    # 插件索引
    ├── evolver/                     # 首个官方插件：Evolver 自进化引擎
    └── example-plugin/              # 最小参考插件，定义官方约定（含全部 7 类组件）
```

## 官方插件

| 名称 | 描述 | 类型 | 组件覆盖 |
|------|------|------|----------|
| [`evolver`](plugins/evolver/) | Evolver 自进化引擎 — 通过 GEP 协议沉淀 Agent 经验 | user | commands + hooks + skills |
| [`example-plugin`](plugins/example-plugin/) | 最小参考实现，展示全部 7 类组件的标准写法 | user | 全部 7 类 |

完整索引见 [plugins/README.md](plugins/README.md)。

## 快速开始

### 安装一个插件到 DriFox

将 `plugins/<name>/` 整个目录复制到 DriFox 的插件目录：

```bash
# Windows
xcopy plugins\evolver %USERPROFILE%\.drifox\plugins\evolver /E /I /Y

# Linux / macOS
cp -r plugins/evolver ~/.drifox/plugins/
```

启动 DriFox，插件会被自动发现并加载。

### 开发一个新插件

1. 阅读 [docs/plugin-development.md](docs/plugin-development.md)
2. 复制 `plugins/example-plugin/` 作为起点
3. 修改 manifest (`plugins/<your-plugin>/.drifox-plugin/plugin.json`)，按需启用 7 类组件
4. 实现 commands / agents / skills / themes / hooks / mcp / lsp
5. 跑校验脚本：`python tools/validate_plugins.py`
6. 提交 PR

## 校验

```bash
# 需要 Python 3.10+ 和 jsonschema（pip install jsonschema）
python tools/validate_plugins.py
```

校验脚本会检查：

- 每个 `plugins/*/.drifox-plugin/plugin.json` 符合 [JSON Schema](schemas/plugin.schema.json)
- 启用的组件（commands/agents/skills/themes/hooks/mcp/lsp）对应资源存在
- 钩子 Python 文件能通过 `ast.parse` 语法检查
- 钩子 `.mcp.json` / `.lsp.json` 是合法 JSON
- 主题 yaml 文件可读
- agent frontmatter 关键字段合法

## 贡献

欢迎通过 Issue 和 PR 贡献新插件或改进现有插件。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本仓库整体采用 [GPL-3.0-or-later](LICENSE)。各插件可在自己的 `plugin.json` 中声明不同的 `license` 字段（system 插件声明的是 `MIT`）。
