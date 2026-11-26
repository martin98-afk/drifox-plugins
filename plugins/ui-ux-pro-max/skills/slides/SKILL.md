---
name: slides
description: "做有策略的 HTML 演示稿：Chart.js 数据可视化、设计 token、响应式布局、文案公式、分场景的幻灯片策略。要 PowerPoint 或可编辑 pptx 时用 ppt-deck 技能，这里只产 HTML。"
argument-hint: "[主题] [页数]"
version: 1.0.0
license: MIT
metadata:
  author: claudekit
  upstream: nextlevelbuilder/ui-ux-pro-max-skill
  localized: zh-CN
---

# Slides

带数据可视化的策略型 HTML 演示设计。

## 什么时候用

- 营销演示与路演稿
- 用 Chart.js 做数据驱动的页面
- 讲究版式策略的幻灯片设计
- 需要文案优化的演示内容

## 子命令

| 子命令 | 作用 | 参考 |
|--------|------|------|
| `create` | 创建策略型演示页 | `references/create.md` |

## 脚本路径

本技能与其 `references/` 里的脚本路径，相对于本 SKILL.md 所在目录，不是项目目录：`scripts/<file>` 是本技能自己的 `scripts/`，`../<skill>/scripts/<file>` 是同级子技能的。用这个目录拼出完整路径，工作目录保持在项目根：脚本按项目根读写 `docs/brand-guidelines.md`、`assets/design-tokens.json`、`src/` 这些文件。

## 参考库

| 主题 | 文件 |
|------|------|
| 版式范式 | `references/layout-patterns.md` |
| HTML 模板 | `references/html-template.md` |
| 文案公式 | `references/copywriting-formulas.md` |
| 幻灯片策略 | `references/slide-strategies.md` |

## 路由

1. 从 `$ARGUMENTS` 里取第一个词作为子命令
2. 加载对应的 `references/{子命令}.md`
3. 用剩下的参数执行