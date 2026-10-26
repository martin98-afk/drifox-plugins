# DriFox 目标契约

生成物的格式真源是 `drifox-plugins2/docs/` 与 `tools/validate_plugins.py`。本文件只列迁移时最容易踩错的约束，完整字段定义以 `docs/` 为准。

权威文档：`docs/architecture.md`（目录约定）、`docs/plugin-manifest.md`（manifest）、`docs/commands.md`、`docs/agents.md`、`docs/skills.md`、`docs/hooks.md`、`docs/mcp.md`。

## 1. 目录骨架（强制）

```
plugins/<plugin-name>/
├── .drifox-plugin/plugin.json     # 必需
├── README.md                      # 必需
├── __init__.py                    # 必需
├── commands/<name>.md             # components.commands
├── agents/<name>.md               # components.agents
├── skills/<name>/SKILL.md         # components.skills
├── hooks/hooks.json + <plugin>_hook.py   # components.hooks
├── tools/<tool>.py                # components.tools（必须含 register(registry)）
├── ui/__init__.py                 # components.ui（必须含 register_ui(registry)）
└── .mcp.json / .lsp.json          # 插件根，不是 .drifox-plugin/ 下
```

## 2. manifest 硬约束（`validate_plugins.py` 会直接 error）

| 约束 | 说明 |
|---|---|
| `name` | `^[a-z][a-z0-9-]{1,63}$`，且必须与目录名一致 |
| `version` | 必须 SemVer（不接受 `0.2.1-rc.2` 以外的畸形串；rc 本身合法但不要用） |
| `description` | 长度 1–200 |
| `components` | 至少启用一个；未知键直接 error |
| components flag ↔ 目录 | 置 `true` 却没有对应目录 → error；`commands=true` 但目录下没有 `.md` → error |

合法的 components 键：`commands` `agents` `skills` `themes` `hooks` `mcp` `lsp` `ui` `tools` `providers` `storages` `serializers` `engines` `gateways` `loop_policies` `model_adapters` `team_templates`。

## 3. commands

- 文件名 `^[a-z][a-z0-9-]*\.md$`，文件名即命令名。
- frontmatter 必填 `description` + `type`，`type ∈ {prompt, function, agent}`。
- 缺 frontmatter 或 frontmatter 未闭合 → error。
- `parameters` 必须是 list of dict；`param_type ∈ {flag, value, positional}`。
- `value_options` 必须是 list 且仅对 `value` 有效（否则 warn）。
- `mutex_groups` 的每项必须在 `prompt_sections` 里能找到，否则 error。
- `prompt_sections` 引用的每个段必须在正文里有 `<!-- section:<id> -->` 标记，否则 **warn**（`--strict` 下即失败）。

**最常见的翻车点**：凭空给 `prompt_sections` 写了映射但正文没打标记。没有真实的多分支就不要写这两个字段。

## 4. agents

- frontmatter 必填 `description`。
- `mode ∈ {all, subagent, primary}`，写错 → error。
- `steps` 必须是 int。

## 5. skills

- `skills/<name>/SKILL.md`，frontmatter 必填 `name` + `description`。
- **`name` 必须与目录名一致**，不一致 → error。
- `description` < 20 字符 → warn「AI 可能无法识别触发场景」。
- 目录下没有 `SKILL.md` → error。

## 6. hooks

- `hooks/hooks.json` 必须有 `hooks` 字典。
- 每个 hook `type` 必须 `python`。
- `function` 必须 `<module>:<func>`，module 建议以 `.` 开头（不带点会 warn）。
- 被引用的 `hooks/<module>.py` 必须存在且能被 `ast.parse`。
- 支持的事件白名单：`BuildSystemPrompt` `SessionStart` `Stop` `UserPromptSubmit` `PreUserMessage` `PostUserMessage` `PreAssistantMessage` `PostAssistantMessage` `PreToolUse` `PostToolUse`。用了白名单外的事件 → warn。
- 处理器签名 `hook_xxx(event: str, context: dict) -> str`。**除 `BuildSystemPrompt` 外返回空串**，否则返回值会被拼进消息流污染会话。
- 静态校验只到 `ast.parse`。要证明真能跑，用 `tools/validate_hooks.py`（注意它找 `app/core/hook_manager.py`，实际在 `app/core/hooks/hook_manager.py`，会误报「未找到 DriFox 仓库」）。

## 7. tools

- `tools/*.py`（下划线开头的文件被忽略）。
- 必须能 `ast.parse` 通过。
- 必须有顶层 `def register(registry)`。
- 运行时要求：`registry.register(...)` 必须显式传 `danger`。

## 8. ui

- `ui/__init__.py` 存在 + 可 parse + 有顶层 `def register_ui(registry)`。
- 三个扩展点签名：
  - `register_floating_card(plugin_name, card_id, widget_class, container, title, default_visible, metadata, context_provider)`，`container ∈ {top,bottom,left,right,full}`，越界抛 `ValueError`。注册后**自动派生 `/<card_id>` 命令**。
  - `register_content_renderer(plugin_name, type_name, render_func, priority, metadata)`，`render_func(data, context) -> str`（HTML）。
  - `register_message_factory(plugin_name, name, condition_func, factory_func, priority)`。
  - 另有 `register_settings_card(plugin_name, card_id, title, widget_class, priority)`。
- **Qt 绑定是双栈**：主线 PyQt5，pyside6 分支另有一套。代码不要硬编码 `PySide6` 或 `PyQt5`，运行时探测。

## 9. mcp

- `.mcp.json` 在插件根，顶层必须 `mcpServers` 字典。
- 每个 server 缺 `command` 且缺 `url` → warn。
- 密钥不得入库；默认 `enabled: false` + 占位符。

## 10. 校验命令

```bash
python tools/validate_plugins.py plugins/<id>            # 退出码 0 = 通过
python tools/validate_plugins.py plugins/<id> --strict   # warn 也当 error
python tools/validate_hooks.py plugins/<id>              # 用真实 HookManager 跑一遍
```

`--strict` 是提交前的口径；迁移产出的第一版通常先过非 strict，再看 warn 是否都能消掉。

## 11. 与 marketplace 的一致性

`validate_plugins.py` 会做全仓 marketplace 一致性检查。新增插件后如果要把条目写进 `marketplace.json`，必须重跑 `tools/generate_marketplace.py`，否则一致性检查 FAIL。本技能**不自动改 `marketplace.json`**。
