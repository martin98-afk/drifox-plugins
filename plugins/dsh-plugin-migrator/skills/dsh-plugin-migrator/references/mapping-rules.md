# 映射规则

每个能力单元必须被判为三者之一：`port`（可 1:1 或近似搬运）、`stub`（落骨架 + `MIGRATION_TODO`，语义待人工补）、`skip`（不属于可迁移范围，只记进报告）。

判定原则：**能力单元的语义可由声明式材料完整确定 → port；需要读 JS 实现才能确定语义 → stub；能力依赖 dsh 宿主固有服务 → skip。**

## 1. 包级判定

| 源特征 | 判定 | 说明 |
|---|---|---|
| 无 `package.json` / 无 `dsh` 段 | 硬停止 | 不是可迁移插件 |
| `dsh: "<path>"`（字符串，CLI bin） | skip | CLI 入口不是插件 |
| `dsh.client.platform` 存在 | stub | Client React UI，无 DriFox 等价（Qt widget 需人工重写） |
| `dsh.bundle.patch` 存在，且包是 harness 内部 leaf（`dsh-base` / `dsh-llm` / `dsh-session` / `dsh-agent` / `dsh-workspace` / `dsh-attachment` / `dsh-authorization` / `dsh-otel` / `dsh-hmr` / `cordis-plugin-timer`） | skip | 宿主固有服务 |
| `dsh.bundle.patch` 存在，其他 | 继续逐单元判定 | |
| patch 行数 ≥ 20（扫描器会报 `aggregate_bundle`） | 降级为 parcel-unit 迁移 | harness 组合层（如 `dsh-web-app` 声明 94 行、stub 占比 0.83），整包迁移只会产出无语义 stub；从清单里挑单个能力单元做目标 |
| 无 `dshWorkshop` / 无 `engines.dsh` | 继续但记 warn | 第三方插件一般都有；缺了就丧失能力契约与版本依据，判定降级 |
| `permissions: ["filesystem:read"]` | agents 权限依据 | `filesystem:read` → agent 只放开 read/glob/grep，其余 deny |

## 2. 能力单元判定表

| 源形态 | 目标 | 判定 | 落地细节 |
|---|---|---|---|
| skill bundle `<name>/SKILL.md`（`name` + `description` + 正文） | `skills/<name>/SKILL.md` | **port** | 见 §3.1 |
| 包根 `SKILL.md`（第三方插件常见） | `skills/<pkg-id>/SKILL.md` | **port** | 目录名取包名去掉 `dsh-` 前缀，与前一条同规格 |
| skill bundle 的 `references/` `scripts/` `assets/` `examples/` | 同名子目录原样带 | **port** | 脚本若是 `.ts`/`.js` 且依赖 dsh API → 降为 stub |
| 平铺 `<name>.md` | `skills/<name>/SKILL.md` | **port** | 目录化，frontmatter 补 `name` |
| patch 里 `name: '@deepseek-ai/dsh-agent-preset'` 行 | `agents/<preset-id>.md` | **port（骨架）** | 见 §3.2；preset 的 `plugins:` 清单 → 报告，不落组件 |
| patch 里 `name: '@deepseek-ai/dsh-command-*'` 行 | `commands/<cmd>.md` | **stub** | 见 §3.3；只有 `locale/*.json` 的 title/description 可搬，handler 语义不可搬 |
| patch 里 `name: '@deepseek-ai/dsh-tool-*'` 行 | `tools/<tool>.py` | **stub** | 见 §3.4；生成 `register(registry)` 骨架 + `MIGRATION_TODO` |
| `defineTool({ parameters })` 的 schema | tools 的 `_SCHEMA` | **port** | schema 是声明式的，可直搬；`execute` 体不可搬 |
| patch 里 `name: '@deepseek-ai/dsh-skill*'` / `dsh-tool-skill` | 不落组件 | **skip** | 这是 dsh 的 skill 运行时，DriFox 宿主自带 |
| patch 里 `name: '@deepseek-ai/dsh-mcp-client'` | `.mcp.json` | **stub** | 只写 server 骨架，`enabled: false`，命令/凭据待人工填 |
| patch 里 `name: '@deepseek-ai/dsh-client-ui-*'` | 不落组件 | **skip（记报告）** | 无等价 UI 载体 |
| 其他 `@deepseek-ai/dsh-*`（观测/审计/注入类） | `hooks/hooks.json` + `hooks/<id>_hook.py` | **stub** | 见 §3.5；事件集与函数体都是骨架 |
| patch 里 `dsh-mcp-client` 或名含 `mcp` | `.mcp.json` | **stub** | 见 §3.6；`enabled=false`，command 留 TODO，凭据不入库 |
| 名含 theme/brand/style | `themes/` | **无自动路径** | 进报告未映射段；主题 token 无 dsh 对应 |
| 名含 lsp | `.lsp.json` | **无自动路径** | 进报告未映射段 |
| 名含 ui-/panel/render/sidebar | `ui/__init__.py` | **stub（骨架）** | 见 §3.7；只固化扩展点与方位，widget 留空 |
| patch 行 `disabled: true` | 报告单列 | — | 不生成组件，标为「默认关闭的可选能力」 |

**兜底纪律**：任何 stub 行若没被上述通道接走，必须进 `migration-report.md` 的待补段，标 `unmapped:<target>`。静默丢弃是这类迁移最危险的失败模式——它会让「搬完了」看起来成立。

## 3. 各通道的落地规格

### 3.1 skill → skills/

frontmatter 映射：

| dsh | DriFox | 处理 |
|---|---|---|
| `name` | `name` | 必须与目录名一致，否则 `validate_plugins.py` 报错 |
| `description` | `description` | < 20 字符会被 warn；dsh 的 description 通常够长，直接搬 |
| `whenToUse` | 并入 `description` 或正文首节 | DriFox 无此键，不要留在 frontmatter |
| `user-invocable` | — | 无对应。若 `false`，可在正文加一句「不面向用户直接调用」 |
| `disable-model-invocation` | — | 无对应。若 `true`，该 skill 实际不可被 AI 用 → 直接 skip 并记报告 |
| `metadata` | 保留 | 无害 |

正文原样带。`references/` 下的 `.ts` 实现片段不改，作为参考材料保留是合理的；`scripts/` 下的可执行脚本若依赖 dsh API，在报告里标 TODO。

### 3.2 agent preset → agents/

```
---
description: <preset 的一句话定位，自写，不复制 dsh 原文>
mode: all
---
```

- `mode` 默认 `all`。若 preset 的插件清单里没有写类工具（无 `tool-fs` / `tool-fs-search`），可设 `subagent`；不确定就用 `all`。
- `steps` 不猜，省略。
- preset 的 `plugins:` 清单写进 `migration-report.md` 的「未映射能力」段落，逐行说明它在 dsh 里做什么、DriFox 侧是否有对应（多数没有）。
- persona 前缀（如 `config.prefix`）**不复制**。DriFox 的 agent 正文要自己写，可以保留「这是个以行动优先的编码角色」这类抽象定位，但不能照搬提示词原文。

### 3.3 dsh command → commands/

dsh 的 command 是 `ctx.commands.register({ name, description, input, handler })`，handler 是 TS 函数。DriFox 的 `commands/<name>.md` 是提示词。

落地：

```markdown
---
description: <来自 locale/*.json 的 meta.description，或 package.json 的 description>
type: prompt
---

# /<name>

<!-- MIGRATION_TODO: dsh 侧命令由 TypeScript handler 实现：<源包>@<handler 标识>。
     以下为按源材料可确定的行为骨架，真实行为需人工按 handler 语义补全。 -->

## 源行为线索
...
```

- `input.hint` → 可写进 `parameters`（`param_type: positional`）；`description` 取自 `locale`。
- `prompt_sections` / `mutex_groups` **不要凭空生成**。没有多模式分支就不写，写了就要有对应 `<!-- section:xxx -->` 标记，否则校验 warn。
- 若命令的 handler 只做状态切换、无任何提示词语义可抽（例如纯开关），判 `skip` 更诚实。

### 3.4 dsh tool → tools/

DriFox 要求 `tools/*.py` 有顶层 `register(registry)`，且 `danger` 必须显式声明。

骨架：

```python
def register(registry):
    registry.register(
        "<tool_name>",
        _SCHEMA,
        impl=_impl,
        danger="safe",   # 不确定时保守用 "safe"，但必须在报告中标为待确认
        cn_name="...",
        group="<plugin-name>",
        description="...",
    )
```

- `_SCHEMA` 从 `defineTool` 的 `parameters` 直搬（声明式，可信）。
- `impl` 体：写 `raise NotImplementedError("MIGRATION_TODO: ...")`，**不要伪造返回值**。一个静默返回假数据的工具比一个显式报错的工具危险得多。
- `danger` 无法从源判定 → 保守取 `safe`，并在报告「待确认」列出。

### 3.5 dsh 运行时服务 → hooks/

`hooks/hooks.json` + `hooks/<plugin-id>_hook.py`（文件名约定：`<plugin-id>_hook.py`）。

骨架生成 5 个事件：`SessionStart` / `PostToolUse` / `PostAssistantMessage` / `Stop` / `BuildSystemPrompt`。选这 5 个是因为它们是白名单里语义最确定的一组；源能力若明显是别的时机（例如只在提交前拦），人工要改事件集。

三条必须守住：

1. **`type` 只能是 `python`**，`function` 必须是 `.<module>:<func>`（带前导点，否则 warn）。
2. **除 `BuildSystemPrompt` 外一律返回空串**。DriFox 的消息级 hook 会把返回值拼进消息流，观测型 hook 返回内容会污染会话。要留痕就写盘（建议 `memory/`）。
3. **`BuildSystemPrompt` 的声明必须静态到头**。它进 system prompt 尾部，动态拼接会话状态会让会话缓存失稳。

骨架自带 CLI 入口（`--event=<Event>` + stdin 传 JSON），可独立调试：

```bash
echo '{}' | python hooks/<id>_hook.py --event=SessionStart
```

验证不能只靠 `validate_plugins.py`（它只做静态检查），要用真实 HookManager 跑一遍：

```bash
python tools/validate_hooks.py plugins/<id> --drifox D:/work/DriFox
```

已知坑：`tools/validate_hooks.py` 找的是 `app/core/hook_manager.py`，实际路径是 `app/core/hooks/hook_manager.py`，当前会报「未找到 DriFox 仓库」。绕过方式是直接用 `HookManager.register_hooks_from_json(skill_name, skill_root, hooks_config, config_file)` 注册后 `trigger_event` 逐事件触发——注意签名是 4 个位置参数，不是 2 个。

### 3.6 dsh MCP → .mcp.json

- 位置在**插件根**，不是 `.drifox-plugin/` 下。
- `enabled: false`。启动命令与凭据都无法从源推导，默认不自动启动。
- `command` 留 `TODO_COMMAND`，`type` 默认 `stdio`。
- **密钥绝对不能入库**：走 `credential` 声明或 `${env.VAR}` 占位符。

### 3.7 dsh Client UI → ui/__init__.py

**能搬的只有两层决定：注册哪个扩展点、挂哪个容器方位。React 组件本体不搬。**

先说清楚为什么只能到这个程度。实测 `~/.dsh/profiles/node_modules/@deepseek-ai/` 下 32 个 `dsh-client-ui-*` 包：

- **31 个在 `lib/index.js` 里没有任何 `register` 调用**。
- `dsh-client-ui-sidebar` 的 `apply()` 是空函数，注释写着 `Provides no host-side behavior`。
- `dsh-client-ui-plan` 的注释更直接：空 `apply` 只是为了「让包出现在 host 的 Loader 里」，浏览器那一半经 `package.json` 的 `dsh.client` 声明**单独分发**。
- `dsh-client-ui-conversation` 的全部内容只是 `ctx.inject(["settings"], ...)` 配一个设置字段——它根本不是 UI 组件。

结论：**host 侧包里没有 UI 结构可提取**，浏览器那一半不在这个包里。所以任何「把 React 翻译成 Qt」的承诺都是编造。

因此骨架做三件事：

1. 按包名/id 推测扩展点（`floating_card` / `settings_card` / `content_renderer` / `message_factory`）与 `container` 方位（`top`/`bottom`/`left`/`right`/`full`），置信度标 `low`。
2. 生成**可实例化**的占位 `QWidget`，保证 `register_ui` 真能跑通（不是只过 `ast.parse`）。
3. 同类扩展点的多行聚合为一个骨架，避免重复注册。

#### 硬约束

- `ui/__init__.py` 必须有顶层 `def register_ui(registry)`。
- **Qt 绑定不能写死**。仓库主线是 PyQt5（82 处引用），pyside6 分支另有一套。骨架用运行时探测：先 `PySide6` 后 `PyQt5`，都没有就 `ImportError`。硬编码任一侧会让插件在另一条线上直接炸。
- `register_floating_card` 的 `container` 只能是 `top`/`bottom`/`left`/`right`/`full`，否则 `ValueError`。
- 浮动卡注册会**自动派生 `/<card_id>` 命令**（用户插件带命名空间前缀），不需要手写命令。
- `register_ui` 里记得清 `sys.modules` 里的旧子模块（热重载兼容），否则重复加载会拿到旧类。

#### 验证

```python
# 不要只跑 validate_plugins.py（它只做 ast.parse）
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from app.plugins.registries.ui_plugin_registry import UIPluginRegistry
reg = UIPluginRegistry()
mod.register_ui(reg)   # 不抛异常才算骨架成立
```

坑：在 `drifox-plugins2` 目录下跑这段会撞 `plugins/calendar/` 遮蔽标准库 `calendar`，导致 `loguru` 导入失败。**换个目录跑**。

## 4. manifest 合成规则

- `name`：kebab-case，`^[a-z][a-z0-9-]{1,63}$`。默认取源包名去掉 scope 与 `dsh-` 前缀；与已有插件重名则加后缀。
- `description`：1–200 字符。**自写**，不得复制源包 description 原文（那是他人材料）。
- `version`：`1.0.0`。不要搬 dsh 的 `0.2.1-rc.2` 之类 prerelease 号。
- `license`：源包是 MIT 时写 `MIT`；否则写源 license，不确定就省略该键（schema 默认 GPL-3.0-or-later，会与源不符 → 此时必须在报告中标出）。
- `type`：`user`。
- `min_host_version`：`0.5.0`。
- `components`：只把**实际生成了目录/文件**的 flag 置 `true`。勾了没目录会直接 error。

## 5. 必须落盘的三个文件

无论搬出多少组件，这三个必须有，否则不是合法插件：

- `.drifox-plugin/plugin.json`
- `README.md`
- `__init__.py`

## 6. 通道覆盖的自检

新增或修改映射规则后，用这条命令自检：**扫描器给出的每个 stub 都必须有一个通道接走它，否则必须进报告的未映射段**。

```bash
python scripts/scan_dsh_plugin.py --source <pkg> | python -c "
import json,sys; inv=json.load(sys.stdin)
for r in inv['patch_rows']:
    if r['verdict']=='stub': print(r['target'], r['name'])
" | sort | uniq -c
```

如果某个 target 没有对应产物也没进报告，说明通道漏了。静默吞掉 stub 会让「搬完了」看起来成立，这是这类迁移最危险的失败模式。

## 7. 写回纪律

只有符合下面任一条才允许写回本文件：

- 判定规则被真实迁移证明是错的（例如某类包其实可 port）。
- 某个 `MIGRATION_TODO` 在人工补全后暴露出稳定的转换模式。

单次迁移的个别现象、某次对话的结论、对某个包的临时处理 → 不写回。写回时改的是规则，不是例子。
