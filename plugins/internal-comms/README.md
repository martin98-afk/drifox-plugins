# internal-comms

> 内部沟通模板 — 3P 沟通（进度/计划/问题）、状态报告、事件复盘、决策通知、产品更新、客户邮件。

源自 [anthropics/skills/internal-comms](https://github.com/anthropics/skills/tree/main/skills/internal-comms)。

## 何时使用

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

## 6 个反模式

- ❌ **长邮件** — 简明扼要
- ❌ **没行动项** — 应当明确下一步
- ❌ **没指派人** — 谁负责
- ❌ **没时间线** — 什么时候完成
- ❌ **忽略负面** — 应当坦诚
- ❌ **形式 > 实质** — 走流程而不解决问题

## 配合

- 配合 `doc-coauthoring` 写文档
- 配合 `superpowers` 决策流程
- 配合 `teach` 培训团队

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
