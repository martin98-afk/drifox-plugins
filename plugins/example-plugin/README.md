# example-plugin

> DriFox 插件的**最小参考实现**。本插件不解决真实问题，专门用来展示官方插件结构与全部 7 类组件的标准写法。

## 目的

- 作为新插件开发的**脚手架起点**（`cp -r plugins/example-plugin plugins/your-plugin`）
- 作为官方插件**结构约定**的活文档
- 作为 `tools/validate_plugins.py` 的**冒烟测试用例**

## 结构（全部 7 类组件）

```
example-plugin/
├── .drifox-plugin/
│   └── plugin.json          # manifest（启用全部 7 类组件）
├── .mcp.json                # MCP 服务器配置
├── .lsp.json                # LSP 语言服务器配置
├── __init__.py              # Python 包标记
├── README.md                # 本文件
├── commands/
│   └── hello.md             # /hello（完整 frontmatter 示例）
├── agents/
│   └── example.md           # @example（只读探索智能体示例）
├── skills/
│   └── example-plugin/
│       └── SKILL.md         # 插件结构与约定检索技能
├── themes/
│   └── example/
│       └── example.yaml     # 浅色主题示例
└── hooks/
    ├── hooks.json           # SessionStart + PostToolUse
    └── example-plugin_hook.py
```

## 七类组件对照

| 组件 | 本插件示例 | 权威参考 |
|------|----------|---------|
| commands | `commands/hello.md` | `plugins/system/commands/`（12 个） |
| agents | `agents/example.md` | `plugins/system/agents/`（10 个） |
| skills | `skills/example-plugin/SKILL.md` | `plugins/system/skills/`（25+ 个） |
| themes | `themes/example/example.yaml` | `plugins/system/themes/`（11 个） |
| hooks | `hooks/hooks.json` + `example-plugin_hook.py` | `plugins/system/hooks/hooks.json` |
| mcp | `.mcp.json` | `plugins/system/.mcp.json` |
| lsp | `.lsp.json` | `plugins/system/.lsp.json` |

## 组件文档

每个组件的完整规范在 `docs/` 下：

- 命令：[`docs/commands.md`](../../docs/commands.md)
- 智能体：[`docs/agents.md`](../../docs/agents.md)
- 技能：[`docs/skills.md`](../../docs/skills.md)
- 主题：[`docs/themes.md`](../../docs/themes.md)
- 钩子：[`docs/hooks.md`](../../docs/hooks.md)
- MCP：[`docs/mcp.md`](../../docs/mcp.md)
- LSP：[`docs/lsp.md`](../../docs/lsp.md)

## 使用

1. 复制本目录到 `~/.drifox/plugins/example-plugin/`
2. 启动 DriFox
3. 试 `/hello --name=World`
4. 用 `@example` 触发智能体
5. `/theme example` 切换主题
6. 观察 `PostToolUse` 钩子输出（`./memory/example-plugin.log`）

## 派生

派生一个新插件时：

```bash
cp -r plugins/example-plugin plugins/your-plugin
```

然后修改：

- `.drifox-plugin/plugin.json` 的 `name`、`description`、`version`
- `README.md`
- 各命令、钩子、技能、智能体、主题文件中的占位内容
- 关闭不用的组件（`components` 字典里把 `false`）

派生后请把本 README 替换为真实说明。

## 校验

```bash
python tools/validate_plugins.py
```

应输出：

```
OK   example-plugin
✓ 全部 1 个插件通过校验
```
