---
name: example-plugin
description: 处理 example-plugin 相关问题：插件结构咨询、命令/钩子/技能编写规范、最小参考示例的派生。触发关键词：example-plugin、插件模板、plugin 模板、commands 怎么写、hooks 怎么写、SKILL.md 模板。
---

# example-plugin 技能

本技能为 DriFox 插件开发者提供 **结构与约定** 的检索能力。当用户咨询如何编写插件的某个组件、或希望基于 example-plugin 派生新插件时，注入本技能。

## 核心要点

### 插件目录结构（强制）

```
<plugin-name>/
├── .drifox-plugin/plugin.json
├── __init__.py
├── README.md
├── commands/      # 可选
├── hooks/         # 可选
└── skills/        # 可选
```

### manifest 必填字段

`name`、`description`、`version`、`components`（至少启用一个组件）。

### 各组件的最小写法

| 组件 | 最小要素 |
|------|---------|
| command | `description` + `type` frontmatter + markdown 正文 |
| hook | `hooks/hooks.json` 中的事件 + `hooks/<plugin>_hook.py` 中的处理函数 |
| skill | `name` + `description` frontmatter + markdown 正文 |

详细规范分别见：
- `docs/commands.md`
- `docs/hooks.md`
- `docs/skills.md`

## 派生新插件

```bash
cp -r plugins/example-plugin plugins/your-plugin
```

然后修改：
1. `plugin.json` 的 `name`、`description`、`version`
2. `README.md`
3. 各命令、钩子、技能文件中的占位内容

## 反模式

- 不要把 manifest 命名为 `manifest.json` / `plugin.yaml`，统一用 `.drifox-plugin/plugin.json`
- 不要在命令文件里嵌入可执行 Python 代码（命令是 prompt，不是脚本）
- 不要让钩子做阻塞主流程的 IO 操作（必须 < timeout）
- 不要在 skill 的 description 里堆砌无关关键词
