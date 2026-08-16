---
name: router
description: 思维模式路由技能 — 按任务类型自动选择推理模式（build→react / fix→spec / 模糊→weak），含行为带判定、关键词分类、复杂度分派、多轮重分类与闲聊退出规则。触发词：路由、router、思维模式、build/fix 分类、任务分类、模式选择、行为带。
---

# router 技能

本技能实现 **任务感知思维模式路由**（源自 dsh-routing-suite / dsh-router-standard，MIT 授权翻译）。

## 路由工作流总结

会话任务进入 → build/fix 关键词正则计数分类 → 按行为带注入 persona + 收窄首轮工具面 → 首个持久工具调用后放开 → weak 带每条消息追加近场引导（1-2 轮基线，3 轮起抗稀释重分类，按复杂度追加收敛/深度尾句）→ `dev_router_status` / `dev_router_mode` 查看改写路由。

**核心发现**：模型行为沿 spec↔react 呈三段稳定带，过渡带（0.2-0.5）不稳定应避免；模型无法自路由，外部路由必要。

## 行为带判定（bandOf）

| mode 值 | 行为带 | 处理 |
|---------|--------|------|
| < 0.2 | spec | 计划优先 |
| 0.2 - 0.5 | transition | **禁止自动选择**，需显式指定 |
| ≥ 0.5 | react | 直接执行 |
| 'weak' | weak | 自主路由（模型自分类） |

## 任务分类规则（classifyTask）

按任务文本关键词命中计数，build 与 fix 各自统计：

- **build 关键词（REACT_RE）**：`开发|创建|写一个|生成|从零|做一个|游戏|网页|网站|构建|新项目|搭建|实现|做出|上线|落地|脚本|工具|应用|build|create|develop|generate|implement|make a|new project`
- **fix 关键词（SPEC_RE）**：`修复|修一下|调试|重构|维护|排查|报错|出错|崩溃|优化|审查|review|fix|debug|refactor|maintain|repair|broken|break|为什么|异常|故障|迁移|升级|兼容`

判定：
- react 命中数 > spec 命中数 → **react**
- spec 命中数 > react 命中数 → **spec**
- 相等 / 均无命中 → **weak**（自主路由）

## 复杂度分派（isComplexTask）

满足任一条件即视为复杂任务：

- 文本 > 120 字符
- 命中关键词：`重构|架构|全面|详细|设计|系统|优化|分析|survey|overview|architecture|refactor|comprehensive|detailed|design|system|optimize|analyze`

复杂任务 → 追加**深度引导**尾句（见下）。

## 引导注入规则

### 标准引导（默认）

> Router: classify this task (build or fix) now, then adopt the matching style — build: direct production; fix: inspect-first. Think deeply first, then commit and act.

### 深度引导（复杂任务）

> Router: classify this task (build or fix) now, then adopt the matching style — build: direct production; fix: inspect-first. Think deeply about the architecture, edge cases, and integration points. Do not spend reasoning on the environment or tooling. Produce when your information is complete. End each reasoning block with a decision or an information need.

### 多轮重分类（3 轮起 / 新任务检测）

> Router: this is a NEW task, different from the previous ones. Classify it fresh (build or fix) and adopt the matching style — build: direct production; fix: inspect-first. Do not follow the previous task's style.

### 闲聊退出（isChatTask）

文本命中 `你好|您好|hello|hi|hey|谢谢|thanks|ok` → **不注入路由引导**，直接正常回复。

## Persona 注入

| 带 | Persona | 工具面 |
|----|---------|--------|
| spec | SPEC：`You are a helpful software engineer assistant.` + plan mode 提示词 | read/edit/glob/grep 优先 |
| react | REACT：`You are a hands-on software engineer who delivers working output fast...` | 全放开 |
| mixed | MIXED：`Work directly: prefer writing or editing code over describing plans...` | 全放开（仅显式选择） |
| weak | WEAK_PRO + WEAK_FLASH 增强句 | 首轮收窄，首个持久工具调用后放开 |

## 近场引导节奏（weak 带）

- **1-2 轮**：基线引导（标准引导句）
- **3 轮起**：抗稀释重分类（多轮重分类引导）
- **按复杂度追加**：收敛尾句（`Produce when your information is complete.`）与深度尾句（`End each reasoning block with a decision or an information need.`）

## 自优化

- `/status`：查看当前路由状态
- `/route --mode=...`：改写路由模式（spec/react/mixed/weak/auto）
- 原版 dsh 的 `dev_router_status` / `dev_router_mode` / `dev_mode_subagent` 工具，DriFox 版以 `/status`、`/route` 命令替代

## 使用方式

- 显式：`/route --mode=spec|react|mixed|weak|auto`
- 自动：不指定模式，按本技能规则自动分类
- 查看状态：`/status`
