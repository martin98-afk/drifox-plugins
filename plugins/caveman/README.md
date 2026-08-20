# Caveman

Ultra-compressed communication mode for AI agents. 实测降低约 65% 输出 token，同时保持完整技术准确性。

> 原项目：[JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman)（MIT）。本目录为该插件的 DriFox 移植版，源码随本仓库分发。

## 组件

- **skills/caveman** — 核心沟通模式。让智能体像 caveman 一样 terse 表达，保留全部技术实质。支持强度：`lite` / `full`（默认）/ `ultra` / `wenyan-lite` / `wenyan-full` / `wenyan-ultra`。
- **skills/caveman-compress** — 记忆文件压缩工具。把 `CLAUDE.md`、todos、preferences 等自然语言文件压缩为 caveman 格式以节省输入 token。脚本在 `skills/caveman-compress/scripts/`，运行：`python -m skills.caveman-compress.scripts <FILE>`（需配置 Claude API）。
- **skills/cavecrew** — 子智能体调度决策指南，配合下方 agents 使用。
- **agents/cavecrew-\*** — 三个 subagent 预设：`cavecrew-investigator`（只读代码定位）、`cavecrew-builder`（1-2 文件精准编辑）、`cavecrew-reviewer`（diff 审查），输出均为 caveman 压缩格式。

## 说明

- 原仓库的 `caveman-stats` 依赖 Claude Code 专用 Node hook（DriFox 无对应机制），本移植版未包含，以免成为空壳。
- 原仓库的 Go proxy / CLI 引擎非 DriFox 插件形态，未纳入。
- 图标使用用户提供的 PNG（`icon.png`）。
