# example-plugin

> DriFox 插件的**最小参考实现**。本插件不解决真实问题，专门用来展示官方插件结构与全部 9 类组件的标准写法。

## 目的

- 作为新插件开发的**脚手架起点**（`cp -r plugins/example-plugin plugins/your-plugin`）
- 作为官方插件**结构约定**的活文档
- 作为 `tools/validate_plugins.py` 的**冒烟测试用例**

## 结构（全部 9 类组件）

```
example-plugin/
├── .drifox-plugin/
│   └── plugin.json          # manifest（启用全部 9 类组件）
├── .mcp.json                # MCP 服务器配置
├── .lsp.json                # LSP 语言服务器配置
├── __init__.py              # Python 包标记
├── README.md                # 本文件
├── tools/
│   ├── example_tool.py      # example_repeat（含 register(registry)）
│   ├── icons/               # 深色主题图标（SVG，文件名 = icon 字段值）
│   │   └── 工具.svg
│   └── icons_light/         # 浅色主题图标（缺省回退 icons/）
│       └── 工具.svg
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
├── hooks/
│   ├── hooks.json           # SessionStart + PostToolUse
│   └── example-plugin_hook.py
└── ui/
    └── __init__.py          # register_ui(registry) 骨架示例
```

## 九类组件对照

| 组件 | 本插件示例 | 权威参考 |
|------|----------|---------|
| tools | `tools/example_tool.py`（含 icon 自包含示例） | `plugins/system/tools/`（file/web/automation/codegraph 等） |
| commands | `commands/hello.md` | `plugins/system/commands/`（12 个） |
| agents | `agents/example.md` | `plugins/system/agents/`（10 个） |
| skills | `skills/example-plugin/SKILL.md` | `plugins/system/skills/`（25+ 个） |
| themes | `themes/example/example.yaml` | `plugins/system/themes/`（11 个） |
| hooks | `hooks/hooks.json` + `example-plugin_hook.py` | `plugins/system/hooks/hooks.json` |
| mcp | `.mcp.json` | `plugins/system/.mcp.json` |
| lsp | `.lsp.json` | `plugins/system/.lsp.json` |
| ui | `ui/__init__.py` | `plugins/system/ui/`（UIPluginRegistry 加载） |

## 组件文档

每个组件的完整规范在 `docs/` 下：

- 命令：[`docs/commands.md`](../../docs/commands.md)
- 智能体：[`docs/agents.md`](../../docs/agents.md)
- 技能：[`docs/skills.md`](../../docs/skills.md)
- 主题：[`docs/themes.md`](../../docs/themes.md)
- 钩子：[`docs/hooks.md`](../../docs/hooks.md)
- MCP：[`docs/mcp.md`](../../docs/mcp.md)
- LSP：[`docs/lsp.md`](../../docs/lsp.md)
- 工具：[`docs/architecture.md`](../../docs/architecture.md#工具组件)

## 插件工具的 icon 自包含

`tools/example_tool.py` 演示了**插件自带图标**的标准做法：每个工具在 `register(...)` 时
通过 `icon="<name>"` 指定图标文件名，PluginToolLoader 自动从插件自带目录加载（无需主程序
资源）。

### 目录约定

```
tools/
├── icons/         # 深色主题图标（主程序默认深色主题时优先用）
│   └── 工具.svg   # icon="工具" → 渲染层找 工具.svg
└── icons_light/   # 浅色主题图标（缺省时自动回退 icons/）
    └── 工具.svg
```

### 查找顺序（渲染层 `render_helpers._get_tool_icon_html`）

1. `<插件根>/tools/icons_light/<icon>.svg`（浅色主题）
2. `<插件根>/tools/icons/<icon>.svg`（深色主题 / 浅色缺失回退）
3. 主程序 `qrc:/icons[_light]/<icon>.svg`（主题感知，兜底）

### 文件名约束

- 大小写**敏感**（`Search` 与 `search` 是两个不同图标）
- 支持中文 / 数字开头 / `-` / `_`（参考 `DriFox/plugins/system/tools/icons/` 下的真实样例）
- 必须是合法 SVG（推荐 `viewBox` + 单 `<path>`）

### 代码示例

```python
registry.register(
    "example_repeat", _REPEAT_SCHEMA, impl=_repeat_impl,
    danger="safe", icon="工具", cn_name="示例重复",   # ← icon="工具"
    group="示例", description="把输入文本重复 N 次",
    render_mode="inline",
    preview=_preview_repeat,
    summarize=make_summarize_from_preview(_preview_repeat),
)
```

> 💡 派生新插件时，把需要的 SVG 拷到 `tools/icons/` + `tools/icons_light/` 即可。
> 同一份图标可在多个插件之间复制：图标库自带、自包含、无主程序耦合。

## 使用

1. 复制本目录到 `~/.drifox/plugins/example-plugin/`
2. 启动 DriFox
3. 试 `/hello --name=World`
4. 用 `@example` 触发智能体
5. `/theme example` 切换主题
6. 观察 `PostToolUse` 钩子输出（`./memory/example-plugin.log`）
7. 让 LLM 调用 `example_repeat` 工具验证 tools 组件加载

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

> 派生时**保留** `tools/icons/` 与 `tools/icons_light/` 作为图标的参考样例，
> 替换为你自己的图标即可。

## 校验

```bash
python tools/validate_plugins.py
```

应输出：

```
OK   example-plugin
✓ 全部 1 个插件通过校验
```
