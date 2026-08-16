# dsh-router — dsh-routing-suite 路由预设的 DriFox 翻译版

**来源**：[yjh051108/dsh-routing-suite](https://github.com/yjh051108/dsh-routing-suite) 的
[dsh-router-standard](https://github.com/yjh051108/dsh-router-standard) 组件（MIT 授权迁移）。

## 功能概述

- **确定性自动路由（硬路由）**：Hook 按关键词计数确定性分类——生成任务走 react（执行者）、维护任务走 spec（计划-集体）、模糊任务进 weak 内路由（模型自分类）。分类规则为硬编码正则，模型无法自改。
- **两步注入**：`BuildSystemPrompt` 在会话构建时注入 persona（按当前 mode）＋ 静态路由说明；`UserPromptSubmit` 每轮消息按分类注入近场引导（weak 带：多轮重分类 + 复杂度尾句；spec/react 带：消息层补 persona 首行）。
- **防缓存污染**：斜杠命令（/route /status）、闲聊（你好/谢谢/ok 等）、过短无意图消息 → 返回空串不注入，避免污染可缓存消息（短文本命中任务关键词仍放行）。
- **状态存储**：路由状态（mode/round）落盘 `~/.drifox/memory/dsh-router-state.json`（固定绝对路径，两事件共享；滚动上限 100 会话键）。
- **已知局限**：persona 动态化（BuildSystemPrompt 按分类读 mode）依赖主程序在 `UserPromptSubmit` ctx 补充 `project_root`/会话标识——当前读不到时回退静态 WEAK_PRO + 路由说明（静态到头保缓存）。
- **三行为带 + 单任务三锚**：persona 静态锚定（回顾 + 收敛 + 反跑题），开放任务完成率 0% → 100%（P1-P23 实测）。
- **近距离引导**：每轮用户消息后注入固定引导，缓存 92-94% 命中，路由 96% + 收敛 100%。
- **AI 自优化**：`/status` 查看路由状态、`/route --mode=` 手动改写路由模式（命令级覆盖，hook 侧仍按自动分类执行）。

## 自动路由判定规则

| 判定 | 规则 |
|------|------|
| build 关键词 | 开发/创建/写一个/生成/从零/做一个/游戏/网页/网站/构建/新项目/搭建/实现/做出/上线/落地/脚本/工具/应用/build/create/develop/generate/implement/make a/new project |
| fix 关键词 | 修复/修一下/调试/重构/维护/排查/报错/出错/崩溃/优化/审查/review/fix/debug/refactor/maintain/repair/broken/break/为什么/异常/故障/迁移/升级/兼容 |
| 分类 | 计数比较：react > spec → react；spec > react → spec；相等/无 → weak |
| 复杂度 | 文本 >120 字符 或 命中 重构/架构/全面/详细/设计/系统/优化/分析 等 → 追加深度引导尾句 |

## 组件

| 目录 | 内容 |
|---|---|
| `commands/` | `/route`（模式选择）、`/status`（路由状态） |
| `agents/` | `@spec`（计划优先）、`@react`（直接执行）、`@mixed`（平衡过渡）、`@weak`（自主路由） |
| `skills/` | `router`（路由规则）、`build-style`（build 执行风格）、`fix-style`（fix 执行风格） |
| `hooks/` | 硬路由 Hook：BuildSystemPrompt（persona 注入）+ UserPromptSubmit（分类引导），状态落盘 `memory/dsh-router-state.json` |

## 与软路由的关系

本插件同时提供软路由（`router` skill 供 AI 自觉遵循）与硬路由（Hook 确定性注入）。硬路由优先——分类由代码保证，skill 作为引导规则补充。

## 许可证

MIT（原始项目 dsh-routing-suite 亦为 MIT，已获作者授权迁移）。
