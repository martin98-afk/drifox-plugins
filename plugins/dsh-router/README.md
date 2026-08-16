# dsh-router — dsh-routing-suite 路由预设的 DriFox 翻译版

**来源**：[yjh051108/dsh-routing-suite](https://github.com/yjh051108/dsh-routing-suite) 的
[dsh-router-standard](https://github.com/yjh051108/dsh-router-standard) 组件（MIT 授权迁移）。

## 功能概述

- **任务感知思维模式路由**：按任务类型自动选择推理模式——生成任务走 react（执行者）、维护任务走 spec（计划-集体）、模糊任务进 weak 内路由（模型自分类）。
- **三行为带 + 单任务三锚**：persona 静态锚定（回顾 + 收敛 + 反跑题），开放任务完成率 0% → 100%（P1-P23 实测）。
- **weak persona 为 Pro/Flash 合并版**：Pro 版自分类句 + Flash 版会话回顾/防环境检查增强句合并（原版区分度 Pro +5.0 / Flash +5.7）。
- **近距离引导**：每轮用户消息后注入固定引导，缓存 92-94% 命中，路由 96% + 收敛 100%。
- **AI 自优化**：`/status` 查看路由状态、`/route --mode=` 改写路由模式，路由行为可被 AI 自查与调整（原版 dev_router_* 工具的 DriFox 命令化）。

## 组件

| 目录 | 内容 |
|---|---|
| `commands/` | `/route`（模式选择）、`/status`（路由状态） |
| `agents/` | `@spec`（计划优先）、`@react`（直接执行）、`@mixed`（平衡过渡）、`@weak`（自主路由） |
| `skills/` | `router`（路由规则）、`build-style`（build 执行风格）、`fix-style`（fix 执行风格） |

## 许可证

MIT（原始项目 dsh-routing-suite 亦为 MIT，已获作者授权迁移）。
