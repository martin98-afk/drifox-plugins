# j-space

> J-Space 认知推理控制套件（V3.6）的 DriFox 技能插件版本。将语言模型可访问的工作表征组织为一个可主动管理的工作空间。

## 它是什么

J-Space 是一层**推理时认知控制层**：文本建立运行框架，模块负责计算路由，可选本地控制器在任务接缝之间保存状态。它不修改模型权重、不要求微调、也不依赖隐藏服务，模型不可知（已在 DeepSeek / Qwen / GLM / GPT / Claude 上复现）。

本插件只含 `skills` 组件：把上游 `J-Space-Cognition-Suite-V3.6` 的 `j-space/` 套件作为 DriFox 技能封装进来，含：

- `skills/j-space/SKILL.md` — 唯一注册入口：前提、任务分类门控（fast / full / loop）、路由与不变式
- `skills/j-space/modules/` — 九个按需加载的协议（broadcast / capacity / deep-reasoning / directed-focus / empirics / introspection / markers / self-monitoring / shorthand）
- `skills/j-space/references/` — 证据、归纳与范例（j-space-science / induction-playbook / exemplars）
- `skills/j-space/scripts/` — 可选本地控制器 `jspace.py`、账本模板与编写期验证器 `verify_suite.py`

## 核心机制

1. **选择性工作集加载** — 活动舞台只保留一到两个连贯项目
2. **广播枢纽** — 共享名/值/约束只推导一次，所有依赖分支从同一枢纽读取
3. **稠密轨** — 长链用紧凑私有寄存器（`✓ ? ✗ ?? ?!`），每行可无损展开为自然语言
4. **结论前桥接推理** — 中间概念先于消费它的结论进入活动状态
5. **元认知控制** — 监控信号必须选择动作，否则只算评论
6. **经验逃逸与验证** — 推导枯竭时转为有限候选集、建立独立参照、差分测试、记录验证覆盖

## 使用

安装后由 DriFox 按上下文自动匹配 `j-space` 技能；复杂/长程/多步任务会进入 `full` 或 `loop` 模式。也可显式要求智能体使用 `j-space` 处理需要更深入推理的任务。

可选控制器（标准库，无第三方依赖）：

```bash
python <插件根>/skills/j-space/scripts/jspace.py note --goal "done 的含义" --next "第一步"
python <插件根>/skills/j-space/scripts/jspace.py seam
python <插件根>/skills/j-space/scripts/jspace.py ship OUTPUT_FILE
```

## 来源与许可

- 上游仓库：[Tiger3807861189/J-Space-Cognition-Suite-V3.6](https://github.com/Tiger3807861189/J-Space-Cognition-Suite-V3.6)
- 许可：Apache License 2.0（与上游一致）
