# doc-coauthoring

> 文档协作写作助手 — 起草、迭代、定稿三阶段流程，结构化访谈、风格统一、决策追踪。

源自 [anthropics/skills/doc-coauthoring](https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring)。

## 何时使用

- 写技术文档、规范文档、决策文档
- 团队协作写作（多人/AI 协作）
- 需要结构化访谈 + 迭代精炼

## 3 大阶段

### 阶段 1：起草（Drafting）

AI 通过结构化访谈收集信息：

```
1. 提出 5-10 个开放问题
2. 收集回答（用户填）
3. 生成第一稿草稿
4. 标记不确定之处
```

### 阶段 2：迭代（Iterating）

```
1. 用户审阅草稿
2. AI 提问澄清模糊点
3. 标记所有未决决策
4. 精炼 + 改进
```

### 阶段 3：定稿（Finalizing）

```
1. 检查一致性
2. 检查完整性
3. 校对语法
4. 输出最终版本
```

## 实战模板

### PRD 文档

1. 问题陈述
2. 目标用户
3. 核心功能
4. 成功指标
5. 范围/非范围
6. 时间线
7. 风险

### RFC 文档

1. 摘要
2. 动机
3. 详细设计
4. 取舍
5. 部署计划
6. 备选方案

## 5 个反模式

- ❌ **跳过访谈直接写** — 错过上下文
- ❌ **一次写完** — 应当迭代
- ❌ **不标未决** — 后续无法追溯
- ❌ **风格不一致** — 多种语气混用
- ❌ **不审校** — 语法错误

## 配合

- 配合 `beautiful-article-skills` 排版
- 配合 `internal-comms` 内部沟通
- 配合 `superpowers` 走 TDD 流程

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
