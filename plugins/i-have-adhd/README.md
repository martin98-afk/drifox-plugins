# ADHD 输出模式

把输出塑造成 ADHD 读者能立刻行动的形状。不是「写短一点」，是改结构。

迁移自 [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd)（62k★，MIT），技能正文译写为中文。

## 用法

```
/adhd              开启，直到本会话结束或你说关闭
/adhd --off        关闭
```

也可以直接说「切到 ADHD 模式」「我注意力差，结论先说」。

## 十条规则

1. 第一行就是下一步动作，不是背景也不是计划。
2. 多步任务编号，每步一段有边界的动作，不出现两次「然后」。
3. 结尾给一个具体的下一步，两分钟内能做完。
4. 压掉跑题：先把第一件事做完，第二件单独提。
5. 每轮复述状态（「5 步里的第 3 步完成」），别指望读者记得。
6. 时间估计给具体单位：15 分钟 / 一个下午，不写「一些工作量」。
7. 已完成的工作要看得见：现在什么能用了，怎么试。
8. 报错不演情绪，直接说原因和修法。
9. 列表每组最多 5 项；相关但不显示的项目内部保留，不丢信息。
10. 不写开场白、不复述、不客套收尾。从答案开始，说完就停。

另有 6 条破例（用户要求讲解、破坏性操作、调试打转、请求有歧义、规则与任务冲突、规则与宿主冲突）与一份发送前检查清单。

## 为什么用命令而不是纯技能

上游用 `disable-model-invocation: true` 锁死自动调用，只允许显式触发。DriFox 的 manifest 没有这个字段，所以本插件把显式入口做成 `/adhd` 命令，技能 description 也写明「仅在明确要求时使用」，避免普通对话被这套规则改写。

规则只有一份，放在 `skills/i-have-adhd/SKILL.md`；命令正文只负责触发与关闭。

## 目录

```
plugins/i-have-adhd/
├── .drifox-plugin/plugin.json
├── commands/adhd.md             /adhd 与 /adhd --off
├── skills/i-have-adhd/SKILL.md  完整规则（中文）
└── LICENSE                      MIT
```

## 许可

MIT，见 `LICENSE`。

## 图标

图标用上游 [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) 的 `logo.png`（256×256）。
