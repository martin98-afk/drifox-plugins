---
name: self-evolve
description: DriFox 自进化工作流 — 当用户要求开发新插件、优化/修复现有插件、给 DriFox 接入 MCP 服务器时，按标准自进化循环调用 evolution_* 工具集（scaffold/validate/inspect/mcp/journal）。触发关键词：自进化、开发插件、创建插件、优化插件、修复插件、改进插件、接入 MCP、连接 MCP、写个工具。
---

# self-evolve — DriFox 自进化工作流

DriFox 的工具/插件全部可热重载（user 根 `~/.drifox/plugins/` 保存即生效）。
配合本插件的 5 个 evolution_* 工具，实现「AI 自己给自己开发能力」。

## 工具速查

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `evolution_scaffold` | 需求 → 插件骨架（17 类组件模板） | `name`(kebab-case 必填) `description` `components=[...]` `force`(覆盖) `author` |
| `evolution_validate` | 插件结构校验（准入门槛） | `plugin_name` `deep`(bool，改工具逻辑/发布前 true，隔离实跑) |
| `evolution_inspect` | 扫描已装插件/深查结构/TODO 定位 | `plugin_name` 或 `list_all=true` |
| `evolution_mcp` | 读写 .mcp.json 管理 MCP 服务器 | `operation`(add/remove/enable/disable/list) `plugin_name` `server_name` `command`/`url` `args` `env`/`headers` |
| `evolution_journal` | 进化审计日志（每次动作必记） | `operation`(log/list/stats/triage) `action`(create/optimize/fix/rollback/mcp/note) `plugin_name` `summary` `status`(ok/failed/pending) `limit` `lines` |
| `evolution_publish` | 发布到市场仓库 | `plugin_name` `mode`(local/direct/fork) `fork_remote` `push`(bool) `commit_type` `message` |

## 标准工作流

### ① 开发新插件

```
1. evolution_scaffold name=<kebab> description=<一句话> components=[tools,...]
   → 生成骨架（含 TODO 标记）
2. read/edit 填充 TODO 实现（user 根直接改，热重载生效）
3. evolution_validate plugin_name=<name> → 全部 OK 才算完成
4. evolution_journal operation=log action=create plugin_name=<name> summary=...
```

### ② 优化/修复现有插件

```
1. evolution_inspect plugin_name=<name> → 摸清结构（目录树/组件/TODO）
2. read 目标实现文件 → 分析问题
3. edit 修改（user 根热重载；system 根需同步主程序仓库）
4. evolution_validate plugin_name=<name> → 复验（改了工具逻辑时加 deep=true，隔离进程实跑 impl 确认不崩）
5. evolution_journal operation=log action=optimize|fix plugin_name=<name> summary=...
```

找不到工具实现路径时，用 `find_tool_path` 工具（tool-locator 插件）定位。

### ③ 接入 MCP 服务器

```
1. evolution_mcp operation=add plugin_name=<目标插件> server_name=<名称>
   command=<stdio命令> args=[...] env={...}     # 本地型
   或 url=<https://...> headers={...}           # 远程型
2. evolution_mcp operation=list → 确认配置
3. 配置已自动写入，DriFox 监听并重连（如未生效再重启）
4. evolution_journal operation=log action=mcp plugin_name=<name> summary=...
```

### ⑤ 发布到市场（三模式）

```
自己用：无需发布 — 插件在 ~/.drifox/plugins 热加载即生效

分享给社区（普通用户标准流程，无需官方权限/无需提 PR）：
1. GitHub 上 Fork 官方仓库（github.com/martin98-afk/drifox-plugins 右上角 Fork）
2. evolution_publish plugin_name=<name> mode=fork \
     fork_remote=https://github.com/<你的账号>/drifox-plugins.git
   自动：基于你的 fork main 建分支 → 同步插件 → validate → commit → 推回 fork main → 还原本地
3. 官方 CI（sync-community，每周）扫描你的 fork → 自动收录来源进 community 市场 → 开 PR → 合并即上架
   代码留在你的 fork，作者拥有仓库

有官方仓库写权限（collaborator）：
   evolution_publish plugin_name=<name>              # 本地 commit（默认）
   evolution_publish plugin_name=<name> mode=direct  # 直推官方 main
4. evolution_journal operation=log action=note plugin_name=<name> summary=...
```

### ⑥ 回滚

scaffold 的 force 覆盖会把旧版备份为 `<name>.bak.<ts>`。
回滚 = 把备份目录内容移回原位，然后 journal 记 `action=rollback`。
## storages 开发速记（高频坑，详见 references/storage_engine.md）

做"存储替换插件 / 会话换格式"时**必记三点**（jsonl-storage 实战踩出的）：

1. **`is_initialized` 必须 `__init__` 末尾立即置 True** — `history_manager._init_storage` 读 `getattr(engine, "is_initialized", False)`，False 会回退 JSON，`save_session` 永远走不到本引擎。`input_history` 走通只是因为 `main_widget.session_store.add_input_history` 是**直接调用**，不经 is_initialized 检查。
2. **必须自激活** — 主程序 `StorageRegistry._active` 默认 `"sqlite"`，全仓库无代码会基于 `config_schema.enabled` 自动 `set_active`。插件须在 `register()` 末尾读 `PluginConfigStore().get(<plugin>, "enabled")` 为 true 时 `registry.set_active(<id>)`。
3. **`config_schema` 字段类型用 `"bool"`**（不是 `"switch"`），否则 settings 面板渲染不出来。

`register(registry)` 收到的 `registry` 是 `_RegistryProxy` 包装，会转发 `set_active` 到底层真 `StorageRegistry`，可直接调用。

## 自进化纪律（防止「脚本验证」绕路）

自进化插件（self-evolver）的验证**必须**走主进程工具闭环，**禁止**绕到独立 bash/python 脚本验证（即使脚本写在 `~/.drifox/plugins/` 外、不污染 sys.modules）：

- 改 `tools/*.py` 的 `impl` 逻辑后 → **必须** `evolution_validate(plugin_name="self-evolver", deep=true)`，等 success=True 才算完成
- `deep=false` 仅适用于**纯脚手架生成**（仍含 TODO）或**纯配置改动**（manifest/frontmatter/无逻辑变更）
- 含 tools 组件且**已有非骨架实现**的插件走 `deep=false` → 工具自提示「未实跑验证，禁止发布」；发布门槛由 `evolution_publish` 内置 deep 强制（待补）
- 自进化语境下，`_run_deep_tools` 内的子进程机制、独立 `bench_verify.py` 等都是**探查辅助**，**不是替代**——最终闭环必须是工具调用结果（success=True 的 content）
- **禁止**用 `bash`/`py -3` 写临时脚本验证自进化插件本身（即便写 `%TEMP%`）：这是绕路，违反自进化闭环纪律

## UI 插件扩展点（必须按需选用）

主程序 `UIPluginRegistry`（`app/plugins/registries/ui_plugin_registry.py`）提供 **8 类扩展点**，建 UI 插件时按需选用，**不要全用**：

| 扩展点 | 用途 | 何时用 |
|--------|------|--------|
| `register_content_renderer`     | 自定义消息流内容块渲染（type_name → html） | 消息里要出现自定义块 |
| `register_welcome_tab`          | 欢迎页加自定义 tab                          | 启动展示自定义页面 |
| `register_floating_card`        | 浮动卡片（自动注册 `/<card_id>` 命令）      | 全屏/侧边/底部的卡片 UI |
| `register_sidebar_item`         | 侧边栏插件项                                | 左/右侧导航新增图标入口 |
| `register_input_button`         | 输入框插件按钮                              | 输入区旁的快捷按钮 |
| `register_context_menu_action`  | 右键菜单项（target ∈ `message_card`/`tab`） | 消息卡片/标签右键加项 |
| `register_settings_card`        | 设置面板卡片                                | 设置界面新增分类卡 |
| `register_message_factory`      | 消息元素工厂（condition 命中 → 生成 widget）| 特定消息结构 → 自定义 QWidget |

**容器方位**（仅 `register_floating_card` 的 `container`）：`top` / `bottom` / `left` / `right` / `full`（`full`=完整覆盖对话区，与系统配置卡片一致）。

**真实案例**（强烈建议参照任一）：
- 浮动卡片：`plugins/context-usage-stats/ui/__init__.py`（`container="full"`、`default_visible=False`）
- 浮动卡片：`plugins/file-tree` / `plugin-marketplace` / `share-history` / `shortcut-manager` / `system-cleaner`

**热重载兼容**（强烈建议照抄下面三行，否则旧 `__pycache__` 会导致 NameError）：

```python
import sys
prefix = "<plugin>."  # 改成你的子模块前缀
stale = [k for k in sys.modules if k.startswith(prefix)]
for k in stale:
    del sys.modules[k]
```

`scaffold_plugin.py` 的 `_UI_INIT` 模板已内置上述纪律与热重载兼容代码，骨架生成后按需选用扩展点。

## 硬约束

- 插件名 kebab-case：`^[a-z][a-z0-9-]{1,63}$`
- 工具必须显式声明 `danger`（safe/dangerous），否则 registry 拒绝注册
- `tools/*.py` 必须暴露顶层 `register(registry)`
- impl 签名：`impl(tool_ctx, **kwargs) -> ToolResult`
- 每次进化动作结束**必须**记 journal（可追溯性是自进化的底线）
- 校验分两层：`evolution_validate`（默认静态，毫秒级）与 `deep=true`（隔离进程实跑 tools 的 register+impl，Harbor 等价物）。改了工具逻辑 / 发布前用 `deep=true`；纯脚手架或配置改动用默认静态即可
- 修改 `plugins/system/` 禁止——那是主程序内置
- 团队模板（`team_templates`）直接引用系统内置 `leader`，**禁止**在插件 `agents/` 自建 `leader.md`（重复定义、易混淆）；成员 agent 仅当团队需专属角色时才新增，其余引用全局已注册 agent
- hooks/mcp/lsp 变更通常自动热重载；如未生效再重启 DriFox

## 安全护栏（防运行时污染，2026-08-22 事故复盘）

> **事故**：自进化测试脚本 `test_scaffold_storage.py`（无 `register`、含 `sys.modules.update({"app.tools": ModuleType(...)})`）被写入 `self-evolver/tools/`，热重载时被 loader 当工具文件 `exec`，用空模块**覆盖运行时 `app.tools`**，导致全程序 `from app.tools import X` 全部 `(unknown location)` 崩溃，权限面板与发送前 schema 失效约 3.5 分钟。

- **`tools/` 只放工具入口**：`tools/*.py` 必须是暴露 `register(registry)` 的工具文件。**禁止**把测试脚本 / 临时验证文件（如 `test_*.py`、`*_verify.py`）写入任何插件的 `tools/` 目录——它们会被热重载 loader 当工具文件 `exec`，其模块级代码会污染运行时 `sys.modules`。
- **禁止 `sys.modules.update` 覆盖核心模块**：自进化测试 / 验证**不得**在插件代码或临时脚本里执行 `sys.modules.update({"app":..., "app.tools":...})` 或 `sys.modules["app.tools"] = ...`。这会用空模块覆盖真模块（`__file__=None` → `(unknown location)`）。
- **测试用隔离环境**：验证生成的插件 / 模板时，在**独立 Python 进程 + 临时目录**中跑（如 `py -c "..." 2>&1` 另起进程），**绝不**把验证脚本写入当前 DriFox 进程的 `tools/` 目录、绝不改动主程序运行时 `sys.modules`。
- **loader 侧已加安全网**：`plugin_tool_loader._is_tool_entry_module` 会拒绝无 `register` 入口或含 `sys.modules` 变异的文件（不 exec）。但**源头纪律仍是根本**——不要制造会被误加载的危险文件。

## 何时用哪个工具（决策表）

| 用户说 | 动作 |
|--------|------|
| 「做个插件」「帮我开发 xx 功能」 | workflow ① |
| 「xx 插件坏了/慢了/要加功能」 | workflow ② |
| 「接个 MCP」「连 xx 服务」 | workflow ③ |
| 「看看装了哪些插件」 | evolution_inspect list_all=true |
| 「上次进化改了啥」 | evolution_journal operation=list |

## 版本纪律

- 新插件从 0.1.0 起
- 优化/修复后 bump：修 bug → patch；加功能 → minor
- scaffold 覆盖前强制用户确认（force 参数就是确认开关）

## 按需加载 references（沉淀经验）

复杂组件开发时按需读 references 目录的实战笔记，**不要每次都从零踩坑**：

| 参考文件 | 何时读 |
|----------|--------|
| `references/runtime_components.md` | scaffold 选了 `storages/serializers/gateways/model_adapters/loop_policies/engines`，或用户提到"系统配置卡片/注册一个 X 引擎" |
| `references/storage_engine.md` | 用户要做"存储替换插件/会话换格式/xlsx/jsonl/csv 存会话"等；接口对齐 `system/storages/sqlite.py` |
| `references/troubleshooting.md` | **任何报错/异常/不生效时**：日志拆分（`all.log` 兜底 + `llm`/`mcp`/`lsp`/`plugins`/`gateway`/`tools`/`team`/`store`/`ui` 分文件）的位置与按场景查询命令、Windows python 命令 9009 坑、MCP 排障实例 |

> 排障第一反射：`evolution_journal operation=triage`（扫日志 ERROR + 关联进化动作），细节见 troubleshooting.md。

> 经验沉淀原则：每完成一个 runtime 组件或踩到一个反复出现的坑，把"症状+根因+正确写法"补到对应 reference，并 journal 记录"优化自进化系统"。
