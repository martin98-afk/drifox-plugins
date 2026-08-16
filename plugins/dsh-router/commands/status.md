---
description: 查看当前思维模式路由状态 — 输出当前路由模式、可用模式清单与切换方式（简化版 dev_router_status）
type: prompt
---

# /status — 路由状态查看

你正在处理 `/status` 命令。向用户报告当前思维模式路由的状态，输出结构如下：

## 当前路由状态

```
📡 思维模式路由状态
- 当前模式：<auto / spec / react / mixed / weak>（从会话上下文推断，未知则显示 auto）
- 行为带：<spec（计划优先）/ react（直接执行）/ weak（自主路由）/ mixed（过渡带，不稳定）>
- 上轮任务类型：<build / fix / 无>
```

## 可用模式清单

| 模式 | 行为 | 何时使用 |
|------|------|----------|
| `spec` | 计划优先，先查后改 | 修复、重构、维护、审查 |
| `react` | 直接执行，快速产出 | 开发、创建、写新代码 |
| `mixed` | 平衡过渡 | 仅显式选择，禁止自动落入 |
| `weak` | 自主路由 | 模糊任务、模型自分类 |
| `auto` | 自动分类 | 默认；按关键词正则判定 build/fix |

## 切换方式

- 手动切换：`/route --mode=spec|react|mixed|weak|auto`
- 自动路由：不指定模式时，按任务关键词自动分类（build → react；fix → spec；模糊 → weak）

## 输出要求

1. 简洁：只输出路由状态表格与建议，不展开任务本身
2. 若检测到当前任务类型模糊，建议用户显式指定 `--mode=` 或交给 `auto`
3. 结尾附一句：`> 路由规则详见 skills/router/SKILL.md`

> 本命令为 `type: prompt` 风格，是 dsh 原版 `dev_router_status` 工具的命令形式简化版。
