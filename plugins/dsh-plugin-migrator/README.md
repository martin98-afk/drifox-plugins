# dsh-plugin-migrator

把 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（`dsh`）插件迁移成 DriFox 插件。

dsh 是 deepseek-ai 的开源 agent harness，架构口号「一切皆插件」，由 Cordis 驱动。它的插件是 **npm/cordis 包**，不是 Claude 插件——所以迁移是跨范式的语义搬运，不是文件拷贝。

## 为什么需要它

dsh 生态有数千个插件。人工逐个重写成本高，而机械直译会产出「能过校验但行为是假的」插件。本技能把这两件事分开：**能 1:1 映射的自动落盘，不能映射的落为显式报错的 stub 并标 `MIGRATION_TODO`**，不允许静默丢弃，也不允许伪造等价。

## 七条搬运通道

| 源能力 | 产物 | 强度 |
|---|---|---|
| skill bundle / 包根 `SKILL.md` | `skills/<name>/SKILL.md` | port |
| `dsh-agent-preset` | `agents/<id>.md` | port（骨架） |
| `dsh-command-*` | `commands/<name>.md` | stub |
| `dsh-tool-*` | `tools/<name>.py` | stub |
| 观测 / 审计 / 注入类 | `hooks/hooks.json` + `hooks/<id>_hook.py` | stub |
| MCP 客户端 | `.mcp.json` | stub |
| `dsh-client-ui-*` | `ui/__init__.py` | stub（骨架） |

theme、LSP、cordis 宿主服务没有等价载体，不生成组件，一律进报告的未映射段。

## 用法

```bash
# 1. 扫描：产出能力清单（每个 patch 行给出 port/stub/skip 与目标通道）
python plugins/dsh-plugin-migrator/skills/dsh-plugin-migrator/scripts/scan_dsh_plugin.py \
  --source <dsh-pkg-dir> --out .dsh-migration/inventory.json

# 2. 迁移：生成插件目录（冲突时报错不覆盖，除非显式 --overwrite）
python plugins/dsh-plugin-migrator/skills/dsh-plugin-migrator/scripts/migrate_dsh_plugin.py \
  --inventory .dsh-migration/inventory.json --repo <drifox-plugins2 根>

# 3. 校验
python plugins/dsh-plugin-migrator/skills/dsh-plugin-migrator/scripts/check_migration.py \
  plugins/<id> --repo <drifox-plugins2 根>
python tools/validate_plugins.py plugins/<id> --strict
```

## 三层证明

| 层 | 含义 | 怎么拿 |
|---|---|---|
| `structure_status` | 目录与 manifest 通过校验器 | `validate_plugins.py --strict` |
| `runtime_status` | 生成物被真实加载执行过 | hooks 用真实 HookManager 触发；ui 用 UIPluginRegistry 加载 |
| `human_status` | 人工确认语义与源插件对得上 | 比对 `migration-report.md` 的 TODO 清单 |

只要还有 `MIGRATION_TODO` 未处理，`runtime_status` 只能是 `blocked`。这是设计，不是缺陷。

## 已知边界

- 本地 `~/.dsh/profiles/node_modules/@deepseek-ai/` 下约 90 个包里只有 43 个带 `dsh` 声明，且基本是 host/client 内部 leaf。**本地没有可迁移的第三方插件**，源要从 npm / GitHub（`topic:dsh-plugin`）/ 自己装的 profile 拿。
- UI 只搬「注册哪个扩展点 + 挂哪个方位」。实测 32 个 `dsh-client-ui-*` 包里 31 个没有任何 `register` 调用，浏览器那一半经 `package.json` 的 `dsh.client` 声明单独分发——host 包内没有 UI 结构可提取。
- 不写 `marketplace.json`，不 git commit，不碰 `~/.dsh`。产物收录市场需自行跑 `tools/generate_marketplace.py`。

## 许可

MIT。DeepSeek Harness 官方文档与包名仅作事实引用，本插件不含其源码或提示词原文。
