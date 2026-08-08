---
name: internal-comms
description: 内部沟通模板 — 3P 沟通（进度/计划/问题）、状态报告、事件复盘、决策通知、产品更新、客户邮件。触发关键词：3p 沟通、状态报告、事件复盘、postmortem、决策通知、产品更新、客户邮件、内部沟通、status report、incident report、decision notice、product update。
---

# Internal Comms 技能 — 内部沟通模板

源自 [anthropics/skills/internal-comms](https://github.com/anthropics/skills/tree/main/skills/internal-comms)。

## 何时触发

- 团队周报 / 状态更新
- 事件复盘（postmortem）
- 决策通知
- 产品更新通告
- 客户邮件回复

## 5 大模板

### 1. 3P 状态报告（Progress / Plans / Problems）

```markdown
## 进度（Progress）
- ✅ 完成 X
- ✅ 完成 Y

## 计划（Plans）
- [ ] 下周目标 X
- [ ] 下周目标 Y

## 问题（Problems）
- ⚠️ 阻塞 Z（需要 X 决策）
```

### 2. 事件复盘

```markdown
## 事件
- 时间：2026-08-08
- 持续：30 分钟
- 影响：用户无法登录

## 时间线
- 10:00 部署
- 10:15 监控告警
- 10:18 确认
- 10:30 修复

## 根因
- config 错误

## 教训
- 部署前需 dry-run

## 行动
- [ ] 加预发测试
- [ ] 更新 runbook
```

### 3. 决策通知

```markdown
## 决策
- 标题：升级到 PostgreSQL 16
- 状态：已批准
- 决策者：@alice
- 日期：2026-08-08

## 上下文
- 性能需求提升
- 旧版本不再维护

## 影响
- 升级 1 周
- 风险中等
```

### 4. 产品更新

```markdown
## What's New
- 🎉 新功能 X
- ⚡ 性能提升 Y
- 🐛 修复 Z

## 升级指南
- 用户无需操作
- 开发者：更新 SDK
```

### 5. 客户邮件

```markdown
## 主题
[更新] Y 功能修复

## Hi {{name}},

我们修复了 Y 问题。

## 详情
- 修复：X
- 影响：你之前报告的 Y

## 立即查看
{{link}}

## 反馈
任何问题回复邮件。

Best,
{{team}}
```

## 7 个写好邮件的原则

1. **结论先行**：第一段说结论
2. **简短**：3-5 段，每段 1-2 句
3. **明确下一步**：每条都含明确行动
4. **指派人**：每条都有负责人
5. **含时间线**：什么时候完成
6. **坦诚负面**：不掩盖问题
7. **CTA 明确**：让读者知道做什么

## 6 个反模式

- ❌ **长邮件** — 简明扼要
- ❌ **没行动项** — 应当明确下一步
- ❌ **没指派人** — 谁负责
- ❌ **没时间线** — 什么时候完成
- ❌ **忽略负面** — 应当坦诚
- ❌ **形式 > 实质** — 走流程而不解决问题

## 5 大场景适用

| 场景 | 模板 |
|------|------|
| 周报 | 3P |
| 事故 | 复盘 |
| 决策 | 通知 |
| 发版 | 更新 |
| 客服 | 客户邮件 |

## 配合

- 配合 `doc-coauthoring` 写文档
- 配合 `superpowers` 决策流程
- 配合 `teach` 培训团队

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
