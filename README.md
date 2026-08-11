# DriFox 插件生态

[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)

DriFox 的官方插件仓库。每个插件是一个独立、可热插拔的扩展单元，提供 8 类能力：

- **commands** — 斜杠命令（`/xx`）
- **agents** — 智能体（`@xx`）
- **skills** — AI 技能（自动匹配）
- **themes** — 主题方案
- **hooks** — 事件钩子
- **mcp** — MCP 服务器配置
- **lsp** — LSP 语言服务器配置
- **ui** — 浮动卡片 / 内容块渲染器 / 消息元素工厂

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
├── CHANGELOG.md                     # 变更日志
├── LICENSE                          # GPL-3.0-or-later
├── marketplace.json                 # 插件市场清单（自动生成，勿手动编辑）
├── .github/
│   ├── workflows/
│   │   └── validate.yml             # CI 自动校验
│   ├── pull_request_template.md     # PR 模板
│   └── ISSUE_TEMPLATE/              # Issue 模板
├── docs/                            # 架构与组件规范
│   ├── architecture.md              # 插件系统整体架构
│   ├── plugin-manifest.md           # plugin.json 字段定义
│   ├── plugin-development.md        # 从零开发一个插件
│   ├── plugin-registry.md           # DriFox 如何发现与加载插件
│   ├── plugin-security.md           # 插件安全审查指引
│   ├── marketplace-improvement-plan.md # 插件市场完善方案
│   ├── commands.md                  # commands 组件规范
│   ├── agents.md                    # agents 组件规范
│   ├── skills.md                    # skills 组件规范
│   ├── themes.md                    # themes 组件规范
│   ├── hooks.md                     # hooks 组件规范
│   ├── mcp.md                       # mcp 组件规范
│   ├── lsp.md                       # lsp 组件规范
│   └── ui.md                        # ui 组件规范
├── schemas/
│   └── plugin.schema.json           # .drifox-plugin/plugin.json 的 JSON Schema
├── tools/
│   ├── validate_plugins.py          # 校验所有插件 manifest + marketplace 一致性
│   └── generate_marketplace.py      # 从 plugin.json 自动生成 marketplace.json
└── plugins/                         # 官方插件集合
    ├── README.md                    # 插件索引
    ├── code-reviewer/               # 自动化代码审查
    ├── evolver/                     # 首个官方插件：Evolver 自进化引擎
    └── example-plugin/              # 最小参考插件，定义官方约定（含全部 8 类组件）
```

## 官方插件

| 名称 | 描述 | 类型 | 组件覆盖 |
|------|------|------|----------|
| [`code-reviewer`](plugins/code-reviewer/) | 自动化代码审查 — checklist 审查、质量评分、报告生成 | user | commands + agents + skills |
| [`evolver`](plugins/evolver/) | Evolver 自进化引擎 — 通过 GEP 协议沉淀 Agent 经验 | user | commands + hooks + skills |
| [`example-plugin`](plugins/example-plugin/) | 最小参考实现，展示全部 8 类组件的标准写法 | user | 全部 8 类 |
| [`frontend-pro`](plugins/frontend-pro/) | 前端开发增强 — 组件规范、a11y 检查、性能最佳实践 | user | commands + skills |
| [`git-workflow`](plugins/git-workflow/) | Git 工作流增强 — 分支检查、提交规范、PR 模板 | user | commands + hooks + skills |
| [`python-pro`](plugins/python-pro/) | Python 开发增强 — PEP 8 / 类型标注 / lint 自动检查 | user | skills + hooks |
| [`test-scaffold`](plugins/test-scaffold/) | 测试脚手架生成 — 测试骨架、覆盖率分析 | user | commands + skills |

### Claude Code 市场适配精选

以下插件从 Claude Code 官方/社区市场适配而来，带来生态验证过的工程工作流：

| 名称 | 描述 | 组件覆盖 | 来源 |
|------|------|----------|------|
| [`superpowers`](plugins/superpowers/) | 核心技能库 — TDD/调试/头脑风暴/计划/代码审查 14 技能 | skills + hooks | obra/superpowers（123k★） |
| [`ecc`](plugins/ecc/) | 工程工作流全集 — 67 智能体 + 284 技能 + 94 命令 | agents + skills + commands | affaan-m/everything-claude-code（25k★） |
| [`skill-creator`](plugins/skill-creator/) | 技能创作/优化/评测完整流程 | skills | Anthropic 官方 |
| [`code-simplifier`](plugins/code-simplifier/) | 代码简化重构智能体 | agents | Anthropic 官方 |
| [`security-guidance`](plugins/security-guidance/) | AI 生成代码安全审查（静态模式检查） | hooks | Anthropic 官方 |
| [`feature-dev`](plugins/feature-dev/) | 功能开发工作流 — 探索→架构→实现→审查 | commands + agents | Anthropic 官方 |

### 创意与趣味插件（Claude 生态）

| 名称 | 描述 | 组件覆盖 | 来源 |
|------|------|----------|------|
| [`algorithmic-art`](plugins/algorithmic-art/) | 程序化艺术生成 — p5.js 流动场/粒子系统 | skills | Anthropic 官方 |
| [`canvas-design`](plugins/canvas-design/) | 设计海报生成 — PNG/PDF 视觉作品 | skills | Anthropic 官方 |
| [`slack-gif-creator`](plugins/slack-gif-creator/) | 动画 GIF 生成 — Slack 尺寸约束 + 校验 | skills | Anthropic 官方 |
| [`theme-factory`](plugins/theme-factory/) | 主题换肤工厂 — 10 套预设主题 + 即时造新 | skills | Anthropic 官方 |
| [`web-artifacts-builder`](plugins/web-artifacts-builder/) | 复杂交互 HTML 构建 — React + Tailwind + shadcn | skills | Anthropic 官方 |
| [`playground`](plugins/playground/) | 交互式 HTML 练习场 — 控件 + 实时预览 | skills | Anthropic 官方 |
| [`excalidraw-diagram`](plugins/excalidraw-diagram/) | 手绘风格图表 — 流程图/时序图/ER 图/思维导图 | skills | github/awesome-copilot |
| [`voice-clone`](plugins/voice-clone/) | MiniMax 语音克隆 — 音频样本克隆音色 + TTS 合成 | commands + skills | DriFox 原生 |

完整索引见 [plugins/README.md](plugins/README.md)。

> **DriFox 运行时内置插件**（如 `plugin-manager`、`plugin-marketplace`、`context-usage-stats`、`file-tree` 等）随 DriFox 分发，**不收录在插件市场中**，避免用户重复安装造成困惑。它们由 DriFox 自带，无需手动安装。

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
3. 修改 manifest (`plugins/<your-plugin>/.drifox-plugin/plugin.json`)，按需启用 8 类组件
4. 实现 commands / agents / skills / themes / hooks / mcp / lsp / ui
5. 跑校验脚本：`python tools/validate_plugins.py`
6. 生成市场清单：`python tools/generate_marketplace.py`
7. 提交 PR

## 校验

```bash
# 需要 Python 3.10+ 和 jsonschema（pip install jsonschema）
python tools/validate_plugins.py
```

校验脚本会检查：

- 每个 `plugins/*/.drifox-plugin/plugin.json` 符合 [JSON Schema](schemas/plugin.schema.json)
- 启用的组件（commands/agents/skills/themes/hooks/mcp/lsp/ui）对应资源存在
- 钩子 Python 文件能通过 `ast.parse` 语法检查
- 钩子 `.mcp.json` / `.lsp.json` 是合法 JSON
- 主题 yaml 文件可读
- agent frontmatter 关键字段合法
- ui 插件 `ui/__init__.py` 必须定义 `register_ui(registry)` 顶层函数
- `dependencies` 中引用的插件存在
- `marketplace.json` 与各 `plugin.json` 关键字段一致

## CI / CD

仓库自带 GitHub Actions 工作流（`.github/workflows/validate.yml`），在 PR 与 push main 时自动跑校验。**marketplace.json 的同步已实现全自动**：

1. **检测**：CI 跑 `generate_marketplace.py --check`，发现 `plugin.json` 与 `marketplace.json` 不一致时该 step 失败
2. **自动修复**：`auto-fix-marketplace` job 触发，重新生成 `marketplace.json` 并自动 commit / push：
   - **PR 场景**：push 回 PR head 分支
   - **push main 场景**：push 回 main，保证 main 始终 green
3. **防循环**：bot commit 携带 `[skip ci]`，GitHub Actions 原生跳过整个 workflow
4. **其他失败**：如果失败原因不是 marketplace 漂移（例如 schema / hooks 语法 / 链接断链），CI 会在 PR 留 comment（PR 场景）或让 job 失败（main 场景），不会自动 commit

> 开发者新增 / 修改插件后**无需手动跑 `generate_marketplace.py`**，CI 会自动帮你补上。

## marketplace.json 生成

`marketplace.json` 是插件市场清单，由脚本自动生成，**请勿手动编辑**：

```bash
# 从所有 plugin.json 汇总生成
python tools/generate_marketplace.py

# 检查 marketplace.json 是否与实际一致（CI 用）
python tools/generate_marketplace.py --check
```

新增或修改插件后，运行生成脚本更新 `marketplace.json`。

## 插件下载量统计

`marketplace.json` 中每个插件可含 `downloads` 字段（累计安装次数），统计链路全自动：

1. **客户端上报**：DriFox 客户端安装/更新插件成功后，后台线程向计数服务 `GET /hit/drifox-plugins-{插件名}` 计数 +1（尽力而为，失败不影响安装）
2. **定时拉取**：GitHub Actions（`.github/workflows/update-downloads.yml`，每 6 小时）运行 `python tools/fetch_downloads.py`，从计数服务读取各插件计数，缓存到 `downloads_cache.json`
3. **回写市场**：同一 workflow 再运行 `generate_marketplace.py`，把计数注入 `marketplace.json` 的 `downloads` 字段并自动提交
4. **客户端展示**：插件卡片与详情面板显示 `⬇ N`

本地手动更新统计：

```bash
python tools/fetch_downloads.py          # 拉取计数并更新 downloads_cache.json
python tools/fetch_downloads.py --check  # 仅检查计数服务可达性
python tools/generate_marketplace.py     # 重新生成 marketplace.json（注入 downloads）
```

> **计数服务**：经典 countapi.xyz 已不稳定，当前使用其开源替代 CountAPI（`countapi.mileshilliard.com`，免注册无鉴权）。服务地址与 key 命名规则在 `tools/downloads_stats.py` 与客户端 `installer.py` 中保持一致，切换服务时需同步修改两侧。
> **防刷说明**：计数服务无鉴权，计数可被伪造 URL 刷高；如需精确统计可换用带鉴权的自建服务（如 Cloudflare Worker + KV）。

## 贡献

欢迎通过 Issue 和 PR 贡献新插件或改进现有插件。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本仓库整体采用 [GPL-3.0-or-later](LICENSE)。各插件可在自己的 `plugin.json` 中声明不同的 `license` 字段（system 插件声明的是 `MIT`）。
