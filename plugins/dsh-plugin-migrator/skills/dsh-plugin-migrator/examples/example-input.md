# 示例输入：`dsh-guard-plan-qc`

一个第三方 dsh 插件包，形态取自真实生态（bundle patch + `dshWorkshop` 元数据 + `engines.dsh` + 根级 `SKILL.md`），内容换成中性的施工合规校核场景，避免搬运他人材料。

```
dsh-guard-plan-qc/
├─ package.json           # dsh.bundle.patch + engines.dsh + dshWorkshop
├─ cordis.patch.yml       # 1 preset / 1 command / 1 tool / 1 disabled 行
├─ SKILL.md               # 包根 skill（真实生态常见形态）
└─ locale/zh.json         # 命令的显示名与描述
```

`package.json` 关键段：

```json
{
  "name": "dsh-guard-plan-qc",
  "dsh": { "bundle": { "patch": "./cordis.patch.yml" } },
  "engines": { "node": ">=24.0.0", "dsh": ">=0.2.1-0 <0.3.0" },
  "dshWorkshop": {
    "schema": "omdsh-workshop-package/v1",
    "type": "plugin",
    "permissions": ["filesystem:read"],
    "capability": {
      "id": "dsh-guard-plan-qc",
      "kind": "service",
      "invocation": "ctx.skills.get('dsh-guard-plan-qc') resolves a complete SkillDefinition"
    }
  }
}
```

完整文件见 `examples/dsh-fixture-guard-plan/`。
