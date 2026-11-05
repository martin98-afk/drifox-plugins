# DriFox 社区插件模板分支

[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)

> 本分支（community）是 DriFox 插件的**社区开发模板分支**。
> 只保留 `example-plugin` 作为最小可运行模板；社区开发者 fork 后基于它开发，代码留在各自 fork。
> fork 推完插件，CI 自动发布 tarball 到你的 fork 并生成清单——你的 fork 就是一个独立插件市场源。

DriFox 是一个 AI Agent 运行时。插件是可热插拔的扩展单元，提供 9 类能力：tools / commands / agents / skills / themes / hooks / mcp / lsp / ui。

## 分支定位

| 项 | 说明 |
|----|------|
| `plugins/example-plugin` | 官方最小参考实现，社区插件的起点（展示全部 9 类组件） |
| `docs/community-cookbook.md` | 跨组件实战手册（来自 80+ 真实插件的模式精炼） |
| `marketplace.json` | 插件清单（CI 自动生成，永远与 `plugins/` 同步） |
| `tools/validate_plugins.py` / `generate_marketplace.py` | 校验与生成工具 |
| `.github/workflows/release-plugins.yml` | tarball 自动构建与发布（fork 即源的核心） |
| `schemas/plugin.schema.json` | `.drifox-plugin/plugin.json` 的 JSON Schema |

> 完整官方实现在 DriFox 运行时内置 `plugins/system/`（不在本仓库）。本仓库的 `example-plugin` 是最小化可工作版本。

## 开始开发

1. 在 GitHub 上 fork 本仓库，切到 `community` 分支
2. **启用 fork 的 Actions**：fork 仓库 Actions 默认禁用，进 `Actions` 页手动启用（一次性）
3. 复制模板作为起点：

```bash
cp -r plugins/example-plugin plugins/your-plugin

# 改 .drifox-plugin/plugin.json 的 name / description / version / components
# 改各组件占位内容
# 本地用 DriFox 热重载验证
python tools/validate_plugins.py
```

## 发布：fork 即源

推完插件，你的 fork 立即可用，无需官方仓库参与：

1. push 插件到你 fork 的 `community` 分支（新插件或版本变更都会触发 CI）
2. CI 自动完成：校验 → 构建 tarball（按平台含依赖）→ 发布到你 fork 的 GitHub Releases → 重新生成 `marketplace.json` → 写回分支
3. 在 DriFox 的 plugin-marketplace 添加源，源 URL 填：

```
https://raw.githubusercontent.com/<你的用户名>/<fork 仓库名>/community/marketplace.json
```

清单里每个插件的下载地址都指向你的 fork（git-subdir 或 Release tarball），
其他用户从源里看到并直接安装你的插件。

> 仓库地址自适应：CI 在哪个仓库、哪个分支上跑，清单里的 `source.url` / `ref` / tarball 链接就指向哪里，fork 无需改任何脚本。

详见 `docs/community-cookbook.md` §10。

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
