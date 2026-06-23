# skills 组件

skills 是 AI 视角的「领域知识包」。当 AI 处理与该技能相关的问题时，DriFox 会自动把 `SKILL.md` 内容注入到上下文。

## 文件结构

```
<plugin-name>/
└── skills/
    └── <skill-name>/
        └── SKILL.md
```

> 一个插件可以有多个 skills，**每个 skill 一个子目录**。`<skill-name>` 是 kebab-case 标识符，**建议与插件名一致**以便 DriFox 匹配。

## 最小示例

```markdown
---
name: my-skill
description: 一句话说明该技能涵盖什么场景、什么关键词会触发它
---

# 技能标题

详细描述本技能的核心概念、API、最佳实践。

## 适用场景

- 场景 A
- 场景 B

## 关键 API

```python
from my_skill import do_thing
do_thing(...)
```

## 反模式

- 不要 xxx
- 避免 yyy
```

## frontmatter 字段

### 必填

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 技能名，kebab-case，与目录名一致 |
| `description` | string | 触发条件描述，AI 据此判断是否注入 |

### 选填

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | string | 技能版本 |
| `triggers` | string[] | 显式触发关键词（不推荐，主要靠 description 自然匹配） |

## `description` 怎么写

`description` 是 AI 决定是否加载该技能的唯一依据。**写法 = 「做什么 + 何时用 + 关键词」**。

✅ 好的写法：
> 处理 Evolver 自进化引擎相关问题：扫描 memory 日志、生成 GEP 进化 prompt、调试 evolver CLI。常用词：evolver、进化、GE、毛细血管、gene、capsule。

❌ 不好的写法：
> 这是 evolver 技能。（太短，AI 无法判断何时用）
> Evolver 工具的完整手册，涵盖安装、配置、API、所有边界情况……（太长，包含非触发信息）

完整示例见 [`plugins/evolver/skills/evolver/SKILL.md`](../plugins/evolver/skills/evolver/SKILL.md)。

## 多 skill 场景

一个插件可以提供多个 skill：

```
plugins/your-plugin/
└── skills/
    ├── main/                # 主体技能
    │   └── SKILL.md
    ├── troubleshooting/     # 排错场景
    │   └── SKILL.md
    └── migration/           # 迁移指南
        └── SKILL.md
```

每个 skill 必须独立可匹配（description 写得区分度足够）。

## 与 commands / hooks 的关系

```
[用户] ── /your-plugin:xx ──► commands/xx.md
                                ↓
                          注入 AI 上下文
                                ↓
[AI]  ←─ 检索 ── skills/yy/SKILL.md（自动）
   │
   ├──► [事件] ── hooks/your-plugin_hook.py（自动）
   │
   └──► 回应用户
```

- **commands** 显式激活
- **skills** AI 隐式检索
- **hooks** 事件自动触发
