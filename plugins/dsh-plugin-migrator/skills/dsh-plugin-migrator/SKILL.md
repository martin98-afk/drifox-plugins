---
name: dsh-plugin-migrator
description: 将 DeepSeek Harness（dsh）插件迁移成 DriFox 插件。解析 dsh 包的 package.json dsh 声明、cordis patch yml 与 skill bundle，产出能力清单，按七条通道落盘 skills/agents/commands/tools/hooks/mcp/ui；不可映射的运行时服务落盘为带 MIGRATION_TODO 的 stub 并列入报告，不伪造等价。当用户说「把 dsh 插件迁过来」「迁移 dsh-plugin」「dsh 包转成 DriFox 插件」「dsh 的 hook/工具/UI 怎么搬」时使用。
compatibility: Requires Python 3.10+ and PyYAML. Reads ~/.dsh/profiles/ or any dsh plugin checkout; writes into a drifox-plugins plugins/ tree given by --repo.
allowed-tools: Read Glob Grep Write Edit Bash(python:*) Bash(py:*) Bash(python3:*)
license: MIT
---

# dsh 插件迁移器

把 DeepSeek Harness（`dsh`）插件自动转成本仓库的 DriFox 插件。dsh 是 deepseek-ai 开源的 agent harness（「一切皆插件」，Cordis 驱动，MIT，开发者预览期）；它的插件是 **npm/cordis 包**，不是 Claude 插件，因此迁移是跨范式的语义搬运，不是文件拷贝。

## 使用者与压力场景

- 使用者：维护 drifox-plugins2 的 agent，或想把某个 dsh 生态插件搬进来的开发者。
- 压力场景：dsh 生态有数千个插件，人工逐个重写成本高；而机械直译会产出「能过校验但行为是假的」插件。
- 最终产物：`plugins/<id>/` 一个合法 DriFox 插件目录（`plugin.json` + `README.md` + `__init__.py` + 各组件），外加一份 `migration-report.md` 说明哪些搬了、哪些是 stub、哪些被跳过。
- 成功标准：`python tools/validate_plugins.py plugins/<id>` 退出码 0，且报告中每一条 `MIGRATION_TODO` 都有归属与处理方式。

## 第一动作（按顺序，不要跳）

1. **定位源包**。优先用 `--source` 显式路径；否则按序探测：`$DSH_HOME/profiles/node_modules/@deepseek-ai/<name>` → `~/.dsh/profiles/node_modules/@deepseek-ai/<name>` → 任意 dsh 仓库 checkout。找不到就停，不要猜包名。
2. **扫描**（`scripts/scan_dsh_plugin.py`）→ 产出 `capability-inventory.json`：包身份、`dsh` 声明、`dshWorkshop` 元数据、patch 行与目标通道、skill bundle、聚合 bundle 判定。
3. **读映射规则** `references/mapping-rules.md`，判定每个能力单元的处置：`port` / `stub` / `skip`。
4. **迁移**（`scripts/migrate_dsh_plugin.py`）→ 落盘插件目录 + `migration-report.md`。
5. **校验**（`scripts/check_migration.py` + `tools/validate_plugins.py`）→ 退出码必须为 0。

## 渐进加载

| 阶段 | 读什么 |
|---|---|
| 判断源包形态 | `references/dsh-plugin-anatomy.md` |
| 决定映射与降级 | `references/mapping-rules.md` |
| 生成/校验产物 | `references/drifox-target-contract.md` |

只读写当前阶段要用的文件。`scripts/` 只运行，不把内容粘进上下文。

## 命令

```bash
# 扫描：产出能力清单（每个 patch 行给出 port/stub/skip 与目标通道）
python scripts/scan_dsh_plugin.py --source <dsh-pkg-dir> \
                                  --out .dsh-migration/capability-inventory.json

# 迁移：生成插件（默认写 plugins/<id>，冲突时报错不覆盖）
python scripts/migrate_dsh_plugin.py --inventory .dsh-migration/capability-inventory.json \
                                     --repo D:/work/drifox-plugins2

# 校验：结构
python scripts/check_migration.py plugins/<id> --repo D:/work/drifox-plugins2
python tools/validate_plugins.py plugins/<id> --strict

# 校验：hooks 真实执行（产物含 hooks 时必跑）
python tools/validate_hooks.py plugins/<id> --drifox D:/work/DriFox
```

## 六条搬运通道

| 源能力 | 产物 | 强度 |
|---|---|---|
| skill bundle / 包根 `SKILL.md` | `skills/<name>/SKILL.md` | port |
| `dsh-agent-preset` | `agents/<id>.md` | port（骨架） |
| `dsh-command-*` | `commands/<name>.md` | stub |
| `dsh-tool-*` | `tools/<name>.py` | stub |
| 观测/审计/注入类 | `hooks/hooks.json` + `hooks/<id>_hook.py` | stub |
| MCP 客户端 | `.mcp.json` | stub |
| `dsh-client-ui-*` | `ui/__init__.py` | stub（骨架） |

theme、LSP、cordis 宿主服务没有等价载体，不生成组件，一律进报告的未映射段。任何 stub 若没被上述通道接走，必须显式进报告，不允许静默丢弃。

UI 通道的诚实边界：只固化「注册哪个扩展点 + 挂哪个方位」，React 组件本体不搬。实测 32 个 `dsh-client-ui-*` 包里 31 个没有任何 `register` 调用——浏览器那一半通过 `package.json` 的 `dsh.client` 声明单独分发，host 包内没有 UI 结构可提取。任何「React 翻译成 Qt」的承诺都是编造。

## 硬停止

- 源包里没有 `package.json`，或 `package.json` 中没有 `dsh` 声明 → 停。它可能不是 dsh 插件（普通 npm 包、纯 skill 目录、或 cordis 内部包）。
- `dsh.bundle.patch` 指向的 patch 文件不存在 → 停，不猜路径。
- 目标 `plugins/<id>` 已存在且未带 `--overwrite` → 停，不覆盖。
- 无法从源材料判定某个能力单元的语义（只有编译后的 `lib/*.js`，没有 `README` / `src` / `locale`）→ 判为 `stub`，不伪造行为。
- 源包整体只有编译产物、没有任何可读的能力声明 → 停，报 `research-needed`，说明缺哪份材料。

## 边界

**非目标**：不迁移 dsh 宿主固有服务（llm / session / persistence / authorization / workspace / otel / hmr / timer）；不生成等价的 TS→Python 运行时逻辑；不负责插件发布、marketplace 同步、版本号决策。

**事实来源**：包身份与能力声明以源 `package.json` 的 `dsh` 段和 patch 文件为准；DriFox 侧格式以 `docs/`（`architecture.md` / `plugin-manifest.md` / `commands.md` / `agents.md` / `skills.md` / `hooks.md` / `mcp.md`）为准。任何人说的「大概这样」不能覆盖这两处。

**权限/副作用**：只在显式指定的仓库 `plugins/` 下写文件；不写 `marketplace.json`、不 git commit、不碰 `~/.dsh`。覆盖已有目录必须显式 `--overwrite`。

**已知坑（实测）**：

- `~/.dsh/profiles/node_modules/@deepseek-ai/` 下约 90 个包里只有 43 个带 `dsh` 声明，且基本是 host/client 内部 leaf（`dsh-skill`、`dsh-command-compact` 都没有 `dsh` 段）。**本地 profile 里没有可迁移的第三方插件**，别在这里翻找当源材料，去 npm / GitHub（`topic:dsh-plugin`）/ 用户自己装的 profile。
- 整包行数 ≥ 20 的是 harness 组合层（`dsh-web-app` 94 行、stub 占比 0.83），扫描器会 warn。此时应挑单个能力单元做迁移目标，不要整包搬。
- `validate_plugins.py` 会额外跑全仓 marketplace 一致性检查，新插件必然在那一栏 FAIL。这是仓库规则（需跑 `generate_marketplace.py`），`check_migration.py` 已把它排除在本产物结构判定之外。
- hooks 产物不要只跑 `validate_plugins.py`（它只做静态检查）。`tools/validate_hooks.py` 当前会报「未找到 DriFox 仓库」——它找 `app/core/hook_manager.py`，实际在 `app/core/hooks/hook_manager.py`。绕过方式：直接用 `HookManager.register_hooks_from_json(skill_name, skill_root, hooks_config, config_file)`（4 个位置参数）注册后 `trigger_event` 逐事件触发。
- UI 产物同理要真加载一次（`UIPluginRegistry` + `register_ui`）。**Qt 绑定不能写死**：主线是 PyQt5，pyside6 分支另有一套，硬编码任一侧会让插件在另一条线上 ImportError。另外在 `drifox-plugins2` 目录里跑这段会撞 `plugins/calendar/` 遮蔽标准库 `calendar`，换个目录跑。

**停止与降级**：材料不足时，可交付的是「能力清单 + 映射报告 + 骨架」，但必须撤回「可直接使用」的结论，并在报告里把缺失材料列成待补清单。stub 组件不算完成。

## 验证口径

三层，任何一层都不能替代另一层：

- `structure_status=artifact_consistent` — 目录与 manifest 通过 `validate_plugins.py`，frontmatter 与目录名一致。
- `runtime_status=verified` — 生成物被真实加载/执行过（hooks 用 `tools/validate_hooks.py`；tools 用 `register()` 真实调用）。
- `human_status=verified` — 用户看过产物并确认语义对得上源插件。

只要出现任意 `MIGRATION_TODO` 未处理，`runtime_status` 只能是 `blocked`。

## 闭环

每次迁移结束，在报告末尾写明：本次运行证据（命令与退出码）、发现的问题、以及写回决策（`writeback` 补充映射规则 / `proposal` 提给用户 / `none-with-reason` / `blocked`）。只有能防止下次再犯的规律才写回 `references/mapping-rules.md`，不要把单次聊天的结论当规则写进去。
