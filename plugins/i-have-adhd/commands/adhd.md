---
description: 开启 ADHD 输出模式 — 结论先行、多步编号、每轮复述进度、压掉跑题
type: prompt
parameters:
  - name: "--off"
    description: "关闭 ADHD 模式，恢复正常输出风格"
    param_type: flag
prompt_sections:
  --off: "off"
---

# /adhd 命令

用户要求进入 ADHD 输出模式。参数：`$ARGUMENTS`

## 行为

1. 先用 `skill` 工具加载 `i-have-adhd` 技能；工具不可用时直接读 `$PLUGIN_DIR/skills/i-have-adhd/SKILL.md`。
2. 从本条回复起严格执行该技能的 10 条规则，直到用户说关闭或再次执行 `/adhd --off`。
3. 用一行确认已开启，不要复述规则，不要解释这个模式是干什么的。

<!-- section:off -->
## 关闭模式

用户要求退出 ADHD 输出模式。

1. 用一行确认已恢复正常风格。
2. 从本条回复起回到默认输出方式，不再套用该技能的规则。
<!-- end -->