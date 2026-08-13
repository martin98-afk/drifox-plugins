# Kim Service

**老金（KimYx0207）AI Hook 与 Agent Skills 合集的 DriFox 插件版。**

包含 9 个组件：HookPrompt（提示词自动优化 Hook）+ 8 个 Skill。
原始项目：[KimYx0207/Kim_Service](https://github.com/KimYx0207/Kim_Service)（MIT License）。

## 组件

| 类型 | 组件 | 作用 |
|---|---|---|
| Hook | **HookPrompt**（`hooks/`） | 把随口说出的需求自动整理成可执行、可验收的专业提示词 |
| Skill | Agent Teams Playbook | 组织多个 Agent 并行工作并按统一规则汇总 |
| Skill | Memory 3-Layer | 三层记忆能力 |
| Skill | Find Skill | 查找和安装合适的 Agent Skills |
| Skill | GoalPro | 生成目标明确、边界清楚、可验收的 Goal 与 Loop Prompt |
| Skill | Kim Decision | 把模糊问题收敛成有证据、能执行的决策 |
| Skill | Meta Skill Creator | 创建、重构和验收真正好用的 Skill |
| Skill | Semgrep Skill | 用 Semgrep 检查代码安全问题 |
| Skill | Xiaohongshu Skill | 生成可直接验收的小红书文案与视觉方案 |

## HookPrompt 工作原理

挂在 `UserPromptSubmit` 事件上。用户输入进入模型前，Hook 先判断：

- **需要优化**（正常需求 / 短诊断输入如「这个不行」「报错了」）→ 注入「强制三段式格式说明 + 优化元模板 + 用户原文」，模型首条回复展示：
  `📝 原始输入 → 🔄 优化后的理解（Context/Task/Format）→ ✅ 优化后的完整提示词`
- **跳过优化**（纯确认 / 斜杠命令 / 系统标签 / 过短无意图）→ 返回空，原输入直接执行

优化方法论（`hooks/prompt_optimizer_meta.md`，可自行编辑）：
role-first、outcome-contract（goal/scope/output_format/success_criteria/verification_plan）、tagged structure、preserve intent、smart ambiguity handling。

> 本实现为原 HookPrompt（Node.js 版）的 **DriFox Python 移植**，行为对齐原版
> `shouldFilter` / `buildFullTemplateInstruction`，仅把 stdin JSON 协议替换为
> DriFox 的 `context["message"]`。原项目：https://github.com/KimYx0207/HookPrompt

## 安装

通过 DriFox 插件市场安装，或将本目录复制到 `~/.drifox/plugins/kim-service/`。

## 测试

```bash
python -m pytest tests/test_kim_service_prompt_optimizer.py -v
```

## 许可

仓库级内容采用 MIT License；各组件目录内的 `LICENSE`、`NOTICE` 或双许可证声明继续独立生效。
