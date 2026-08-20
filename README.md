# DriFox 社区插件模板分支

[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)

> 本分支（community）是 DriFox 插件的**社区开发模板分支**。
> 只保留 `example-plugin` 作为最小可运行模板；社区开发者 fork 后基于它开发，代码留在各自 fork，
> 本仓库的 `marketplace.json` 只汇聚**来源**（不复制代码）。

DriFox 是一个 AI Agent 运行时。插件是可热插拔的扩展单元，提供 9 类能力：tools / commands / agents / skills / themes / hooks / mcp / lsp / ui。

## 分支定位

| 项 | 说明 |
|----|------|
| `plugins/example-plugin` | 官方最小参考实现，社区插件的起点（展示全部 9 类组件） |
| `docs/community-cookbook.md` | 跨组件实战手册（来自 80+ 真实插件的模式精炼） |
| `marketplace.json` | 官方模板 + 各 fork 社区插件来源（由 `sync-community.yml` 周更） |
| `tools/validate_plugins.py` / `generate_marketplace.py` | 校验与生成工具 |
| `schemas/plugin.schema.json` | `.drifox-plugin/plugin.json` 的 JSON Schema |

> 完整官方实现在 DriFox 运行时内置 `plugins/system/`（不在本仓库）。本仓库的 `example-plugin` 是最小化可工作版本。

## 开始开发

```bash
# 1. fork 本分支（在 GitHub 上）
# 2. 复制模板作为起点
cp -r plugins/example-plugin plugins/your-plugin

# 3. 改 .drifox-plugin/plugin.json 的 name / description / version / components
# 4. 改各组件占位内容
# 5. 本地用 DriFox 热重载验证
# 6. 跑校验
python tools/validate_plugins.py
```

## 发布到社区市场

1. fork 本分支 → 在 fork 的 `plugins/` 下开发（保留 example-plugin 作模板）
2. push 到你的 fork
3. 本仓库 CI 每周扫描所有 fork，把你的插件**来源**写进 `marketplace.json` 并开 PR
4. 维护者审核合并后，用户在 plugin-marketplace 看到你的插件，去你的 fork 下载

代码不汇入本仓库（保持模板纯净、作者拥有自己的仓库）。流程详见 `docs/community-cookbook.md` §10。

## 权威参考

各组件字段级规范见 `docs/`：

- 命令：[`docs/commands.md`](docs/commands.md)
- 智能体：[`docs/agents.md`](docs/agents.md)
- 技能：[`docs/skills.md`](docs/skills.md)
- 主题：[`docs/themes.md`](docs/themes.md)
- 钩子：[`docs/hooks.md`](docs/hooks.md)
- MCP：[`docs/mcp.md`](docs/mcp.md)
- LSP：[`docs/lsp.md`](docs/lsp.md)
- 架构：[`docs/architecture.md`](docs/architecture.md)
- manifest：[`docs/plugin-manifest.md`](docs/plugin-manifest.md)
- 开发：[`docs/plugin-development.md`](docs/plugin-development.md)
- 注册：[`docs/plugin-registry.md`](docs/plugin-registry.md)
- 安全：[`docs/plugin-security.md`](docs/plugin-security.md)

**实战手册（必读）**：[`docs/community-cookbook.md`](docs/community-cookbook.md) — 跨组件方法论、真实模式、踩坑、反模式。

## 校验

```bash
python tools/validate_plugins.py
```
