# example-plugin

> DriFox 插件的**最小可运行参考实现**，也是社区插件分支（community）的**官方开发模板**。
> 本插件不解决真实问题，专门用来展示官方插件结构与全部 9 类组件的标准写法，并作为 `tools/validate_plugins.py` 的冒烟测试样本。

本分支（community）只保留这一个插件作为模板。社区开发者 fork 后基于它派生自己的插件，
代码留在各自 fork，本仓库的市场清单（marketplace.json）只汇聚**来源**。详见 `docs/community-cookbook.md`。

---

## 目的

- 作为新插件开发的**脚手架起点**：`cp -r plugins/example-plugin plugins/your-plugin`
- 作为官方插件**结构约定**的活文档
- 作为 `tools/validate_plugins.py` 的**冒烟测试用例**

---

## 结构（全部 9 类组件）

```
example-plugin/
├── .drifox-plugin/
│   └── plugin.json          # manifest（启用全部 9 类组件）
├── .mcp.json                # MCP 服务器配置（示例，默认禁用）
├── .lsp.json                # LSP 语言服务器配置（示例）
├── __init__.py              # Python 包标记
├── README.md                # 本文件
├── icon.svg                 # 插件图标（浅色/亮色）
├── icon_dark.svg            # 插件图标（深色）
├── tools/
│   ├── example_tool.py      # example_repeat（含 register(registry) + icon 自包含）
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
│       └── example.yaml      # 浅色主题示例
├── hooks/
│   ├── hooks.json           # SessionStart + PostToolUse
│   └── example-plugin_hook.py
└── ui/
    └── __init__.py          # register_ui(registry) 骨架示例
```

---

## 九类组件对照

| 组件 | 本插件示例 | 进阶实战（来自真实插件） |
|------|----------|------------------------|
| tools | `tools/example_tool.py` | `docs/community-cookbook.md` §5 |
| commands | `commands/hello.md` | `docs/community-cookbook.md` §1 |
| agents | `agents/example.md` | `docs/community-cookbook.md` §2 |
| skills | `skills/example-plugin/SKILL.md` | `docs/community-cookbook.md` §3 |
| themes | `themes/example/example.yaml` | `docs/community-cookbook.md` §7 |
| hooks | `hooks/hooks.json` + `example-plugin_hook.py` | `docs/community-cookbook.md` §4 |
| mcp | `.mcp.json` | `docs/community-cookbook.md` §8.2 |
| lsp | `.lsp.json` | `docs/lsp.md` |
| ui | `ui/__init__.py` | `docs/community-cookbook.md` §6 |

> **另有两类组件**（providers / team_templates）本示例未启用，但主程序支持：
> 服务商插件见 `docs/community-cookbook.md` §8.1；团队模板见 `app/core/team/template_schema.py`。
> 需要时把对应 `components` 字段置 `true` 并加目录即可。

---

## 每个组件「这个示例展示了什么」

### tools — `tools/example_tool.py`
- `register(registry)` 完整字段：`danger` 必填、`icon` 自包含、`cn_name`/`group`/`description` 必填
- 渲染三闭包：`preview` / `render` / `summarize` + `render_mode`
- `make_summarize_from_preview` 复用 preview 生成压缩摘要
- 第二个工具（含 `render` 闭包的 expand 模式）以注释形式给出，取消注释即启用

### commands — `commands/hello.md`
- `type: prompt` 是唯一真实取值（全仓库命令 100% 是 prompt）
- `parameters`（value/flag/positional）+ `mutex_groups` + `prompt_sections` 参数组织
- 模板变量实际只有 `$ARGUMENTS` 与 `$PLUGIN_NAME`（`$PLUGIN_DIR`/`$PROJECT_ROOT` 命令里不替换）
- `<!-- section:id -->` ... `<!-- end -->` 分段写法

### agents — `agents/example.md`
- DriFox 五段式正文：`Role` / `Primary Goal` / `Constraints` / `Output Format` / `Example`
- `permission` 默认 deny-all 再逐项放行（只读智能体禁写）
- `mode` / `steps` / `temperature` 行为控制

### skills — `skills/example-plugin/SKILL.md`
- frontmatter 仅 `name` + `description` 必填
- `description` 写触发词 + 用途，决定何时被 LLM 自动匹配
- 反模式：不要堆无关关键词

### themes — `themes/example/example.yaml`
- `name` / `id` / `window` 渐变 / `background` 背景图 / `colors` token
- `input_glow_preset` 差异化开关
- 复制 `rdr2/` 或 `laputa-fog/`（已删除，仅作思路）改色最快

### hooks — `hooks/hooks.json` + `example-plugin_hook.py`
- 事件声明：`SessionStart` / `PostToolUse`（真实还有 PreToolUse / UserPromptSubmit / Stop / PostAssistantMessage / BuildSystemPrompt）
- `function` = `.模块名:函数名`（点开头、无 .py）
- 实现：观测型落盘 `memory/`、幂等、原子写

### ui — `ui/__init__.py`
- `register_ui(registry)` 唯一入口，四步骨架（清缓存 → 注入 sys.path → 注册 → 错误隔离）
- 三类扩展点：浮动卡片 / 欢迎 tab / 内容渲染器（本示例只演示骨架）

---

## 插件工具的 icon 自包含

`tools/example_tool.py` 演示**插件自带图标**：注册时 `icon="工具"` 对应
`tools/icons/工具.svg`（深色）+ `tools/icons_light/工具.svg`（浅色）。PluginToolLoader 自动从插件目录加载。

**查找顺序**（渲染层）：
1. `<插件>/tools/icons_light/<icon>.svg`（浅色主题）
2. `<插件>/tools/icons/<icon>.svg`（深色 / 浅色缺失回退）
3. 主程序 `qrc:/icons[_light]/<icon>.svg`（兜底）

图标文件名大小写敏感，可中文；浅色缺失自动回退深色版。派生时把需要的 SVG 拷到这两个目录即可。

---

## 使用

1. 复制本目录到 `~/.drifox/plugins/example-plugin/`
2. 启动 DriFox
3. 试 `/hello --name=World`
4. 用 `@example` 触发智能体
5. `/theme example` 切换主题
6. 观察 `PostToolUse` 钩子输出（`./memory/example-plugin.log`）
7. 让 LLM 调用 `example_repeat` 工具验证 tools 组件加载

---

## 派生

```bash
cp -r plugins/example-plugin plugins/your-plugin
```

然后修改：
- `.drifox-plugin/plugin.json` 的 `name`、`description`、`version`
- `README.md`
- 各命令、钩子、技能、智能体、主题文件中的占位内容
- 关闭不用的组件（`components` 字典里设 `false` 并删对应目录）

派生后请把本 README 替换为真实说明。

> 派生时**保留** `tools/icons/` 与 `tools/icons_light/` 作为图标参考样例。

---

## 发布到社区市场

本分支不汇聚代码，只汇聚来源。流程：
1. fork 本 community 分支
2. 在 fork 的 `plugins/` 下开发（保留 example-plugin 作模板）
3. push 到你的 fork
4. 本仓库 CI 每周扫描 fork，把你的插件来源写进 marketplace.json 并开 PR
5. 审核合并后，用户在 plugin-marketplace 看到并去你的 fork 下载

详见 `docs/community-cookbook.md` §10。

---

## 校验

```bash
python tools/validate_plugins.py
```

应输出：

```
OK   example-plugin
✓ 全部 1 个插件通过校验
```

若新增组件类型，记得同步更新 `docs/community-cookbook.md` 与 `plugins/README.md`。
