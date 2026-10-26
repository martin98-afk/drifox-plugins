# 示例输出：`plugins/guard-plan-qc`

由 `examples/dsh-fixture-guard-plan` 实跑生成。真实运行记录见本文件末尾的三条命令。

## 命令与结果

```bash
python scripts/scan_dsh_plugin.py \
  --source examples/dsh-fixture-guard-plan \
  --out .dsh-migration/fixture-inventory.json
# -> patch 行: port=1 stub=3 skip=1；skill bundle=1    (exit 0)

python scripts/migrate_dsh_plugin.py \
  --inventory .dsh-migration/fixture-inventory.json --repo D:/work/drifox-plugins2
# -> 已生成 plugins/guard-plan-qc
#    skills:1  agents:1  commands:1  tools:1  MIGRATION_TODO:3  skip:1   (exit 0)

python scripts/check_migration.py plugins/guard-plan-qc --repo D:/work/drifox-plugins2
# -> structure_status = artifact_consistent
#    runtime_status   = blocked   # 未处理 TODO 数：17
#    human_status     = unverified                                        (exit 0)

python tools/validate_plugins.py plugins/guard-plan-qc --strict
# -> OK guard-plan-qc（零 error 零 warn）
#    FAIL marketplace.json（外部项：新插件需跑 generate_marketplace.py）

# hooks 的真实执行证据（用 DriFox 真实 HookManager，非静态检查）
# -> REGISTERED: 5
#    SessionStart/PostToolUse/PostAssistantMessage/Stop/BuildSystemPrompt -> 全部 success
#    TOTAL_SUCCESS: 5 / 5
```

## 产物结构

```
plugins/guard-plan-qc/
├─ .drifox-plugin/plugin.json    # components: agents/commands/skills/tools/hooks/mcp
├─ README.md
├─ __init__.py
├─ migration-report.md           # 已生成 / 待补 / 未映射 三段
├─ agents/guard-plan-qc.md       # preset → agent 骨架（persona 待人工写）
├─ commands/guard-plan-check.md  # TS handler → prompt 骨架（语义待补）
├─ skills/guard-plan-qc/SKILL.md # 完整搬运（frontmatter + 正文）
├─ tools/guard_plan_lookup.py    # register() 骨架，_impl 显式抛 NotImplementedError
├─ hooks/hooks.json              # 5 个事件，function 均带前导点
├─ hooks/guard_plan_qc_hook.py   # 合法签名 + CLI 入口，函数体留空
└─ .mcp.json                     # enabled=false，command 留 TODO_COMMAND
```

## 六类处置的实际分派

| 源能力 | 处置 | 产物 |
|---|---|---|
| 包根 `SKILL.md` | **port** | `skills/guard-plan-qc/SKILL.md`，frontmatter 合规、正文完整 |
| `dsh-agent-preset` 行（id=guard-plan-qc） | **port（骨架）** | `agents/guard-plan-qc.md`，preset 的 3 个插件行列进报告 |
| `dsh-command-guard-plan-check` | **stub → commands** | `commands/guard-plan-check.md`，description 取自 `locale/zh.json` |
| `dsh-tool-guard-plan-lookup` | **stub → tools** | `tools/guard_plan_lookup.py`，`_impl` 抛错不伪造返回 |
| `dsh-guard-plan-qc/audit` | **stub → hooks** | `hooks/hooks.json` + `guard_plan_qc_hook.py`，5 事件真实触发成功 |
| `dsh-mcp-client` | **stub → mcp** | `.mcp.json`，`enabled=false`，凭据不入库 |
| `dsh-guard-plan-qc/telemetry`（disabled） | **skip** | 进报告未映射段，标为默认关闭的可选能力 |

## 证明层级

- `structure_status = artifact_consistent` — `validate_plugins.py --strict` 判定本插件 OK 且零 warn。
- `runtime_status = blocked` — 17 条 `MIGRATION_TODO` 未处理。其中 hooks 骨架本身**能真实跑通 5/5 事件**（这是骨架契约正确，不是行为等价）；tool 的 `_impl` 会显式抛错。
- `human_status = unverified` — 需人工比对源插件语义。

这个组合是正确的终态，不是失败：能自动搬的已经搬完，不能搬的被显式标出并阻止「看起来能用」的假象。
