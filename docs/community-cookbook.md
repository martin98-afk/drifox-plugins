# 社区插件开发 Cookbook

> 本文件是 **社区插件分支**（community）的实战手册。
> 本分支只保留 `example-plugin` 作为最小可运行模板；所有「其他插件用到的真实内容与方法」精炼于此，供社区开发者 fork 后参考。
> 各组件的**字段级权威规范**见同目录 `commands.md` / `agents.md` / `skills.md` / `hooks.md` / `themes.md` / `mcp.md` / `lsp.md` / `architecture.md` / `plugin-manifest.md`，本文侧重**实战模式、踩坑、来自 80+ 真实插件的经验**。

---

## 0. 本分支的定位与协作流

```
你 fork community 分支
   └─ 基于 plugins/example-plugin 派生你的插件
   └─ 开发、本地用 DriFox 热重载验证
   └─ push 到你的 fork
        └─ 本仓库的 CI（.github/workflows/sync-community.yml）每周扫描所有 fork
             └─ 只把你的插件「来源」写进 marketplace.json（不复制代码）
                  └─ 开 PR 由维护者审核合并
                       └─ 用户在 plugin-marketplace 看到你的插件 + 来源，去你的 fork 下载
```

**关键约定**：本仓库**不汇聚代码**，只汇聚来源。模板区 `plugins/` 永远只有 `example-plugin`；社区插件的代码留在各 fork，下载从 fork 走。

---

## 1. commands — 斜杠命令

> 实锤纠正：`type` 字段在真实插件里**只有 `prompt` 一种取值**（全仓库 100 个命令 100% 是 `prompt`）。`function` / `agent` 类型在源码中不存在，不要照抄旧文档写它们。

### 1.1 frontmatter 字段全集（按真实使用频率）

| 字段 | 是否常用 | 说明 |
|------|---------|------|
| `description` | ✅ 必填 | 一句话中文用途 |
| `type` | ✅ 必填 | 固定 `prompt`（整段 markdown 作为系统提示注入） |
| `parameters` | ⚠️ 常用 | 列表式参数 schema，每项含 `name` / `description` / `param_type` |
| `mutex_groups` | ⚠️ 常用 | 互斥参数分组 `{组名: [选项...]}` |
| `prompt_sections` | ⚠️ 常用 | 参数值 → `<!-- section:id -->` 正文段绑定 |
| `argument-hint` | 偶用 | YAML 映射式参数提示（键是 `[--xxx]` 字面串） |
| `allowed-tools` | 偶用 | 限制命令内可用工具白名单 |
| `hidden` | 偶用 | `true` 时在 UI 隐藏该命令 |

`parameters[].param_type` 三种：`value`（带 `=` 引值）、`flag`（布尔）、`positional`（占位符）。

### 1.2 三种参数组织模式（直接复用）

**互斥单选 + 段落映射**（最推荐）：
```yaml
parameters:
  - name: "--file="
    description: "审查指定文件"
    param_type: value
  - name: "--staged"
    description: "仅审查暂存区"
    param_type: flag
  - name: "--full"
    description: "全项目审查"
    param_type: flag
mutex_groups:
  scope: ["--file", "--staged", "--full"]
prompt_sections:
  --file: "file_review"
  --staged: "staged_review"
  --full: "full_review"
```

**枚举值限定**：`param_type: value` 配 `value_options: [spec, react, mixed, weak, auto]`。

**无 section 的互斥**：只声明 `mutex_groups`，正文用 markdown 表格描述差异（适合选项含义接近时）。

### 1.3 模板变量（实锤）

命令正文中**真实可用**的只有两个：`$ARGUMENTS`（用户原参数）、`$PLUGIN_NAME`（插件名）。
`$PLUGIN_DIR` / `$PROJECT_ROOT` 仅出现在 AGENTS.md 描述里，命令源码中**不会**被替换——需要项目路径请在命令里让 LLM 自己用 `pwd` / 工具探测。

### 1.4 分段写法

正文用 `<!-- section:file_review -->` ... `<!-- end -->` 包裹可选段，由 `prompt_sections` 命中参数时注入。未命中的 section 不出现。

**技巧**：复杂命令把「默认行为」「安静模式」「错误处理」分 section，避免一次性输出过长干扰 LLM。

---

## 2. agents — 智能体

> 生态里有**两种风格并存**，loader 都支持：DriFox 自研风格（中文触发词 + 细粒度权限）与 Claude 原生风格（英文能力描述 + 工具枚举）。

### 2.1 frontmatter 差异

| 字段 | DriFox 风格 | Claude 原生风格 |
|------|------------|----------------|
| `description` | 中文 + `触发词：xxx、yyy` | 英文一句能力 |
| `name` | 可省略（用文件名） | 必填，与文件名同名 |
| `mode` | `subagent` / `all` | 省略 |
| `tools` | 省略 | 精确枚举（`Glob, Grep, Read, ...`） |
| `permission` | 精细化黑白名单 | 省略 |
| `steps` | 推理步数上限（20–30） | 省略 |
| `temperature` | 0.3–0.5 | 省略 |

### 2.2 两种正文结构

- **DriFox 五段式**：`# Role` / `# Primary Goal` / `# Constraints` / `# Output Format` / `# Example`
- **Claude 原生式**：`You are ...` 开头 + `## Core Process` / `## Output Guidance` 清单

### 2.3 真实可复用技巧（来自 code-reviewer / dsh-router / feature-dev）

1. **默认 deny-all 权限**：`permission: { "*": deny, read: allow, grep: allow, glob: allow }` 再逐项放行，防子智能体越权写文件。
2. **计划类 agent 禁写**：`spec` 类 agent 设 `write/edit/multi_edit: deny`，只产出方案不落地。
3. **触发词中文化**：逗号分隔同义词覆盖口语（`修一下、调试、排查`）。
4. **temperature 分级**：计划 0.3（严丝合缝）、执行 0.5（发散）、自主判别 0.4（平衡）。
5. **steps 上限**：计划类 30、混合/自主 25、执行 20，避免长篇推理。
6. **输出格式硬约束**：用 markdown 代码块固定输出结构（`## 审查报告`），便于主 agent 解析。
7. **置信度阈值**：`Only report issues with confidence ≥ 80`，降误报。
8. **不稳定经验写进 description**：如 `⚠️ 过渡带实测不稳定，仅显式选择时启用`，阻止自动落入。

### 2.4 触发方式

- DriFox 风格：靠 `description` 里的触发词 → router 命中激活。
- Claude 风格：无触发词，由父 agent 经 `Task(subagent_type=...)` 显式调用。

---

## 3. skills — AI 技能

### 3.1 frontmatter（必填仅 2 个）

```yaml
---
name: writing-skills          # 强制 kebab-case：^[a-z0-9-]+$，不以 - 开头/结尾、无 --
description: |
  多行描述。第三人称。用途：...
  触发词：写技能、skill 模板、distill [person]...
---
```

`description` 支持 `>` / `|` 块标量；解析时拼接为单字符串。

### 3.2 触发命中率优化（四维）

1. **场景动词 + 用户原话**：`创建、修改、优化` + `「造skill」「蒸馏XX」`。
2. **中英文双触发**：每个 perspective 同时列中文触发词与 `English triggers: "distill [person]"`。
3. **显式 NOT 触发**：`不要在用户只是说「帮我解释一下」时触发`——防误触发。
4. **正则埋点**：路由类技能用关键词正则（`开发|创建|写一个` → build 带；`修复|调试|重构` → fix 带）驱动行为选择。

### 3.3 复杂技能组织

```
skills/skill-name/
├── SKILL.md            # 必填主文档
├── references/         # 重型参考（100+ 行 API/语法）拆这里
├── scripts/            # 可复用 Python 工具
└── agents/             # 盲比较/评分等子智能体
```
**原则**：原则与概念、<50 行代码模式保持内联；重型参考/工具/子 agent 拆文件。

**TDD 造技能法**：先观察 agent 不带 skill 怎么失败（基线）→ 写 skill → 再观察它变乖。

---

## 4. hooks — 事件钩子

### 4.1 hooks.json 格式

```json
{
  "description": "简述",
  "hooks": {
    "PostToolUse": [
      { "hooks": [ { "type": "python", "function": ".<module>:<func>",
                     "timeout": 5, "enabled": true, "id": "<uuid>" } ] }
    ]
  }
}
```
`function` = 点开头 + 文件名（无 `.py`）+ 冒号 + 函数名。

### 4.2 事件类型（真实存在）

| 事件 | 时机 | 用途类型 |
|------|------|---------|
| `SessionStart` | 会话开始 | 观测（初始化） |
| `PostToolUse` | 工具执行后 | 观测（审计/检查） |
| `PostAssistantMessage` | 模型回复后 | 观测（记录） |
| `Stop` | 会话结束 | 观测（收尾） |
| `PreToolUse` | 工具执行前 | **干预（拦截/校验）** |
| `UserPromptSubmit` | 用户消息提交 | 干预（注入/校验） |
| `BuildSystemPrompt` | 构建 system prompt | 增强（注入声明） |

**观测型**通常返回空串、只落盘；**干预型**返回值进入 LLM 上下文或拦截调用。

### 4.3 四大实现模式

1. **准入/拦截（PreToolUse）**：不匹配 → `return {"continue": True}`；命中违规 → `return {"decision": "block", "reason": "..."}`。永远不抛异常，用 `finally: sys.exit(0)` 兜底。
2. **拦截+阻止（hookify）**：`{"decision": "block", ...}` 触发 DriFox 阻断；普通警告返回纯文本注入上下文。
3. **记录/审计（Post*）**：全部状态落盘 `memory/`（subprocess 无内存共享）；JSONL 单行追加天然原子；读-改-写用 `tmp + rename` 原子写。
4. **增强/注入（BuildSystemPrompt）**：静态文本追加到 system prompt 尾部。

**踩坑**：钩子 Python 必须 `python -m py_compile` 通过；不要做阻塞主流程的 IO（受 `timeout` 限制）。

---

## 5. tools — 内置工具

### 5.1 register 完整字段

```python
registry.register(
    "my_tool", _SCHEMA, impl=_impl,
    danger="safe",            # 必填：safe | dangerous（未声明 registry 拒绝）
    icon="工具",              # 必填：对应 tools/icons/<icon>.svg
    cn_name="我的工具",        # 必填
    group="示例",             # 必填：分组 + 能力分组判定
    description="描述",        # 必填
    aliases=["MyTool"],        # 可选
    render_mode="inline",     # ""折叠 / expand展开 / inline单行 / none不渲染
    preview=_preview,         # (tool_args)->str 卡片标题
    render=_render_body,      # (result,name,args,success)->str|None body
    summarize=make_summarize_from_preview(_preview),  # 历史压缩摘要
    metadata={"permission_arg": "path"},  # 扩展协议
)
```

`make_summarize_from_preview(preview_fn)` 用同一 preview 生成压缩摘要，减样板。

### 5.2 impl 与 tool_ctx

```python
def _impl(tool_ctx, **kwargs) -> ToolResult:
    raw = tool_ctx.get("workdir")
    workdir = Path(str(raw)).resolve() if raw else Path.cwd()  # 兜底 cwd
    # tool_ctx["env"]["app_data_dir"] / ["desktop_automation_enabled"]
    # tool_ctx["services"]["window_state"] 提供 get(k) / set(k, v) KV 接口（跨调用共享）
    return ToolResult(True, content="...")
```

### 5.3 自包含 vs 平台 services

- **自包含**（标准库 + `deps/`）：`win-powershell` 用 subprocess + base64（UTF-16LE 避 Windows 乱码）；`tool-locator` 用 `ast`+`glob` 扫描 `~/.drifox/plugins/*/tools/*.py`。
- **deps 注入**：`_deps = abspath(join(dirname(__file__), "..", "deps")); sys.path.insert(0, _deps)`。
- **兄弟模块导入**：PluginToolLoader 用 importlib 加载，模块名带连字符前缀，兄弟模块不能相对导入——必须 `sys.path.insert(0, _TOOLS_DIR)` 再 `from file_io import ...`。
- **services 调用**：需要平台能力（子智能体/LSP/MCP/todo）时走 `tool_ctx["services"]`，不访问主程序内部。

### 5.4 图标自包含

`tools/icons/<icon>.svg`（深色）+ `tools/icons_light/<icon>.svg`（浅色）。`icon` 字段值 = 文件名（大小写敏感，可中文）。浅色缺失自动回退深色。

### 5.5 渲染三闭包

`preview`（inline 卡/折叠头）→ `render`（body HTML，返回 None 回退默认）→ `summarize`（历史压缩 1 行）。`render_mode` 控制完成框形态。

---

## 6. ui — 浮动卡片 / 渲染器

### 6.1 register_ui 四步骨架（必抄）

```python
def register_ui(registry):
    prefix = "ui_plugin_<plugin>."
    for k in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[k]                       # ① 清旧缓存（热重载）
    ui_dir = str(Path(__file__).resolve().parent)
    if ui_dir not in sys.path:
        sys.path.insert(0, ui_dir)               # ② 注入插件根（子模块跨导）
    try:
        registry.register_floating_card(...)     # ③ 注册扩展点
    except Exception:
        logger.exception(...)                    # ④ 错误隔离
```

`sys.path.insert` 必需——否则 `from _state import ...` 失败。

### 6.2 三类扩展点（真实落地情况）

| 扩展点 | 真实使用 | 说明 |
|------|---------|------|
| `register_welcome_tab` | ✅ calendar/context-stats/project-dashboard | `render_func(ctx)->str(md/html)`，新增欢迎 tab |
| `register_floating_card` | ✅ workbuddy/browser | `card_id` 自动注册 `/<card_id>` 命令（toggle） |
| `register_content_renderer` / `register_message_factory` | ❌ 本仓库未落地 | 需在 UIPluginRegistry 源码确认是否存在 |

### 6.3 Widget 与跨线程

- 基类：`QWidget`（复合窗口）或 `QFrame`（内嵌卡片），命名 `xxxCard`。
- 类级单例 `_instance` 供 `/cmd` handler 引用；`set_context_provider` 拉模型注入；`refresh_theme` 主题刷新入口。
- **跨线程最大坑**：所有后台线程 + Qt 操作必须经 `pyqtSignal` + `QueuedConnection` 桥（`_PopupBridge` 模式），否则崩溃。
- `render_func` 返回 HTML 时：`<script>` 在 `innerHTML` 注入下**不执行**——交互走内联 `onclick` 立即执行函数；图表用 ```` ```echarts ```` 代码块 + JSON。

---

## 7. themes — 主题

### 7.1 yaml 结构

```yaml
name: 示例主题
id: example
window:
  gradient_start: rgba(245,245,250,255)
  gradient_end:   rgba(220,222,230,255)
background:
  chat_list: { image: ":/icons/fox_bg.png", opacity: 0.05, enabled: true }
colors:
  card_bg: rgba(255,255,255,232)
  text_primary: '#1a1a1a'
  accent: '#5b8def'
  input_glow_preset: subtle      # 关键差异化开关
```

### 7.2 真实技巧

- `input_glow_preset`（`subtle`/`platinum`/...）是关键差异开关，新主题必选并匹配主调色。
- 同色系主题需在 `accent_warm` / `hover_bg` / `selected_bg` / `input_focus_border` / `ring_normal` 中至少一项明显不同。
- 最快路径：复制 `rdr2/` 或 `laputa-fog/` 整目录，改 `name` / `id` / 颜色 token / 背景图。
- 校验：目录名正则合法、必有 yaml、必有 `id`（见 `docs/themes.md` 末段）。

---

## 8. providers + mcp

### 8.1 ProviderDef（必填字段）

```python
registry.register(ProviderDef(
    name="DeepSeek",                       # 唯一
    icon="deepseek",                       # 图标 key
    api_url="https://api.deepseek.com",
    auth_type="bearer",                    # bearer/bce/none/anthropic
    default_model="deepseek-chat",
    models=["deepseek-v4-flash"],
    models_dev_id="deepseek",              # models.dev slug（必填）
    family="deepseek",
    capabilities={"context_limit": 320000, "supports_thinking": True},  # 不可省
    balance_fetcher=make_bearer_balance_fetcher(url=..., balance_key=..., currency="¥"),
))
```

`icon_dir` / `icon_dir_light` 由 loader 自动注入；`capabilities` 缺省 UI 无法判断模型特性。`fetcher` 内部所有异常统一 `return None`，绝不上抛。

### 8.2 MCP 配置（`.mcp.json`）

```json
{ "mcpServers": { "srv": {
    "type": "stdio", "command": "uvx", "args": ["x", "-y"],
    "env": {}, "enabled": true } } }
```
Python 服务用 `py -3`、npm 服务用 `npx -y`；即使无 `env` 也写 `"env": {}`。

---

## 9. 跨组件方法论

### 9.1 派生工作流

```bash
cp -r plugins/example-plugin plugins/your-plugin
# 改 .drifox-plugin/plugin.json 的 name/description/version/components
# 改 README.md 与各组件占位内容；不用组件设 false 并删目录
python tools/validate_plugins.py
```

### 9.2 权限与安全三层

| 层 | 机制 | 文件 |
|----|------|------|
| 工具 | `danger="safe|dangerous"` 强制声明 | `tools/*.py` |
| 智能体 | `permission` 黑白名单（默认 deny-all） | `agents/*.md` |
| 钩子 | `PreToolUse` 拦截/block | `hooks/*.py` |

### 9.3 图标自包含约定（通用）

工具、服务商图标都自带 `icons/`（深）+ `icons_light/`（浅），渲染按主题加载，浅色缺失回退深色。图标库自包含、无主程序耦合，可在插件间复制。

### 9.4 热重载与调试

- commands / skills 改完立即生效；hooks / mcp / lsp 可能需重启 DriFox；ui 卡片自动重载。
- 钩子 Python 改完跑 `python -m py_compile` 自查。
- ui 插件热重载需清 `sys.modules` 缓存（见 §6.1）。

---

## 10. 发布到社区市场

1. fork 本 community 分支。
2. 在 fork 里 `plugins/` 下开发你的插件（**不要删除 example-plugin**，它是模板）。
3. push 到你的 fork。
4. 本仓库 CI 每周扫描所有 fork，把你的插件**来源**（name + fork URL + 下载地址）写进 `marketplace.json`，开 PR。
5. 维护者审核合并后，用户在 plugin-marketplace 看到你的插件，去你的 fork 下载。

**不汇聚代码**的原因：保持模板分支纯净、避免版权/安全耦合；下载直达 fork，作者拥有自己的仓库。

---

## 11. 反模式清单

- ❌ commands 写 `type: function` / `agent`——真实只支持 `prompt`。
- ❌ 命令正文用 `$PROJECT_ROOT` / `$PLUGIN_DIR` 期望被替换——不会生效。
- ❌ 工具 `register` 漏 `danger`——registry 拒绝注册。
- ❌ ui 子模块用相对导入——必须 `sys.path.insert` 后用绝对导入。
- ❌ 钩子做阻塞 IO / 抛异常——受 timeout 限制，需原子落盘 + 不抛。
- ❌ skill 的 `description` 堆无关关键词——降命中率，写显式 NOT 触发更好。
- ❌ agent 不设权限边界——默认 deny-all 再逐项放行。
- ❌ 把 manifest 命名为 `plugin.yaml`——统一 `.drifox-plugin/plugin.json`。
- ❌ 图标文件名大小写不一致——大小写敏感，`Search` ≠ `search`。
