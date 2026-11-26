---
name: brand
description: "品牌声音、视觉识别、信息框架、资产管理、品牌一致性。做品牌内容、语气把控、营销物料、品牌合规、风格指南时使用。"
argument-hint: "[update|review|create] [args]"
version: 1.0.0
license: MIT
metadata:
  author: claudekit
  upstream: nextlevelbuilder/ui-ux-pro-max-skill
  localized: zh-CN
---

# Brand

品牌识别、语气、信息、资产管理与一致性框架。

## 什么时候用

- 定义品牌声音、给内容定语气
- 视觉识别标准与风格指南的编写
- 信息框架（messaging framework）搭建
- 品牌一致性评审与审计
- 资产的组织、命名与审批
- 配色管理与字体规格

## 脚本路径

本技能与其 `references/` 里的脚本路径，相对于本 SKILL.md 所在目录，不是项目目录：`scripts/<file>` 是本技能自己的 `scripts/`，`../<skill>/scripts/<file>` 是同级子技能的。用这个目录拼出完整路径，工作目录保持在项目根：脚本按项目根读写 `docs/brand-guidelines.md`、`assets/design-tokens.json`、`src/` 这些文件。

## 快速开始

**把品牌上下文注入提示词：**

```bash
node scripts/inject-brand-context.cjs
node scripts/inject-brand-context.cjs --json
```

**校验一个资产：**

```bash
node scripts/validate-asset.cjs <asset-path>
```

**提取或对比颜色：**

```bash
node scripts/extract-colors.cjs --palette
node scripts/extract-colors.cjs <image-path>
```

## 品牌同步流程

```bash
# 1. 改 docs/brand-guidelines.md（或执行 /brand update）
# 2. 同步到设计 token
node scripts/sync-brand-to-tokens.cjs
# 3. 验证
node scripts/inject-brand-context.cjs --json | head -20
```

同步在检测到这些情况时会停下：常见 CSS 入口及其本地 import 里已有 token 文件、`:root` 自定义属性或 Tailwind v4 `@theme` 变量；或已有 Tailwind 主题色与预设。先看它报告的来源再决定。如果检测到的文件就是上一次同步产出的 `assets/design-tokens.*`，而且你确实要覆盖它们，再加 `--force` 重跑。

**同步涉及的文件：**

- `docs/brand-guidelines.md`：唯一真相
- `assets/design-tokens.json`：token 定义
- `assets/design-tokens.css`：CSS 变量

## 子命令

| 子命令 | 作用 | 参考 |
|--------|------|------|
| `update` | 更新品牌识别并同步到各设计体系 | `references/update.md` |

## 参考库

| 主题 | 文件 |
|------|------|
| 语气框架 | `references/voice-framework.md` |
| 视觉识别 | `references/visual-identity.md` |
| 信息框架 | `references/messaging-framework.md` |
| 一致性检查 | `references/consistency-checklist.md` |
| 指南模板 | `references/brand-guideline-template.md` |
| 资产组织 | `references/asset-organization.md` |
| 配色管理 | `references/color-palette-management.md` |
| 字体规格 | `references/typography-specifications.md` |
| logo 使用规则 | `references/logo-usage-rules.md` |
| 审批清单 | `references/approval-checklist.md` |

## 脚本

| 脚本 | 用途 |
|------|------|
| `scripts/inject-brand-context.cjs` | 提取品牌上下文，供注入提示词 |
| `scripts/sync-brand-to-tokens.cjs` | 把 brand-guidelines.md 同步成 design-tokens.json/css |
| `scripts/validate-asset.cjs` | 校验资产命名、尺寸、格式 |
| `scripts/extract-colors.cjs` | 提取颜色并与配色表对比 |

## 模板

| 模板 | 用途 |
|------|------|
| `templates/brand-guidelines-starter.md` | 新品牌的完整起步模板 |

## 路由

1. 从 `$ARGUMENTS` 里取第一个词作为子命令
2. 加载对应的 `references/{子命令}.md`
3. 用剩下的参数执行

## 本地化说明

本文件由英文原文译写为中文。脚本是 `.cjs`，需要 Node；环境里没有 Node 时，按 `references/` 里的规则人工完成同步与校验，并在交付说明里注明脚本未运行。