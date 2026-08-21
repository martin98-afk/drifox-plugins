# evolver_scaffold — DriFox 自进化工具集

让 DriFox **自己给自己开发插件**：AI 可调用的 5 个工具 + 1 个技能引导。

## 设计理念

借鉴 [dsh-self-evolving](https://github.com/timwhitez/dsh-self-evolving)（DeepSeek Harness 自进化引擎）的
证据优先思想，落到 DriFox 插件化架构上：

```
需求 → evolution_scaffold（生成骨架） → 人工/AI 填充实现
  → evolution_validate（结构校验，准入门槛）
  → evolution_journal（记录进化日志，append-only 可审计）
  → DriFox watchfiles 热重载 → 新能力立即生效
```

修复闭环：`evolution_inspect`（找到目标插件）→ read/edit 修改 → `evolution_validate` 复验 → 热重载生效。

scaffold 支持 DriFox 全部 **17 类组件**（对齐主程序 `kernel.KNOWN_COMPONENTS`）：
tools / commands / agents / skills / hooks / mcp / lsp / themes / ui / providers /
team_templates / model_adapters / loop_policies / storages / serializers / gateways / engines。

MCP 闭环：`evolution_mcp` 读写任意插件的 `.mcp.json`，为 DriFox 连接新 MCP 服务器。

## 工具清单（6 个）

| 工具 | 功能 | danger |
|------|------|--------|
| `evolution_scaffold` | 按需求生成插件骨架（17 类组件模板，manifest/README） | safe |
| `evolution_validate` | 校验插件结构合规（manifest/组件/py_compile/frontmatter） | safe |
| `evolution_inspect` | 扫描已装插件，返回结构摘要与文件清单 | safe |
| `evolution_mcp` | 增/删/列/读 MCP 服务器配置（.mcp.json） | safe |
| `evolution_journal` | 记录/查询进化审计日志（append-only） | safe |
| `evolution_publish` | 发布插件到市场仓库（同步+marketplace+校验+commit，push 可选） | dangerous |

写入操作（scaffold/mcp 写入）默认落在 **user 根**（`~/.drifox/plugins/`），热重载即时生效。

## 技能

`skills/self-evolve/SKILL.md` — 引导 AI 在「用户要求开发/优化/修复插件、连接 MCP」时
按标准自进化工作流调用上述工具。

## 目录结构

```
self-evolver/
├── .drifox-plugin/plugin.json
├── skills/self-evolve/SKILL.md
└── tools/
    ├── scaffold_plugin.py
    ├── validate_plugin.py
    ├── inspect_plugin.py
    ├── mcp_manager.py
    ├── evolution_journal.py
    └── icons(±_light)/*.svg
```

## 快速验证

```
evolution_inspect plugin_name=self-evolver   → 应看到本插件结构
evolution_scaffold name=demo-plugin components=tools,skills → 生成 demo 骨架
evolution_validate plugin_name=demo-plugin   → 应全部 OK
```
