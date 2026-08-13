# 运行合同

本文件补充 `SKILL.md` 的字段级规则。它定义什么能进入记忆、三层之间如何转移，以及失败时应如何收口。

## 合法输入

| 来源 | 可记录内容 | 必要处理 |
|---|---|---|
| 用户明确指令 | “以后使用 pnpm”“记住部署区是 cn-east” | 检查秘密与冲突；保留来源说明 |
| 项目文件 | 已落盘的架构决策、命令、约束 | 记录文件相对路径；易变事实标日期 |
| Hook 事件 | 标准字段中的工具名、项目内工作文件与会话事件 | 工具响应中的 `summary` / `fact` / `confirmed` 全部不持久化；只接受受管记录器的顶层 `memory_fact`，并忽略 session id、cwd 等元数据噪声 |
| 模型推断 | 候选规律、可能偏好 | 只能进入 review 建议；未经确认不写长期事实 |

禁止输入：认证信息、私钥、Cookie、支付凭证、个人隐私、完整聊天转储、大段工具原始输出、无法追溯来源的断言。

## 三层分配

### Layer 1：结构化事实

适合有明确主语、可验证、未来可能失效的事实。每项至少包含：

- `id`
- `fact`
- `timestamp`
- `status`：`active` 或 `superseded`
- `category`
- `source`

冲突事实不直接覆盖旧值。保留旧项并在确认后改为 `superseded`，新增 active 项引用新来源。

### Layer 2：每日轨迹

适合“今天做了什么、为什么、结果是什么”。采用按日追加，不将工具全量输出抄入文件。每条应能回答：动作、结果、相关主题。

### Layer 3：隐性知识

适合跨项目阶段仍然有效、难以从单条事件自动推断的经验，例如稳定的架构原则或反复验证的避坑规则。只允许用户确认或 review 后提升；保持短小。

## 去重与冲突

1. Python 核心只负责标准化空白与大小写后的完全重复检查。
2. 同一 topic 下的语义近似、含义冲突和过时判断由 `memory-review` 的 Agent 辅助复查完成，不宣称为确定性自动能力。
3. 完全重复时核心跳过并报告 `duplicate`。
4. Agent 发现潜在冲突时只生成建议，不自动决定谁正确。
5. 用户确认新事实后，将旧事实标为 `superseded`，不要删除。

## 上下文预算

加载顺序固定为 Layer 3 → Layer 2 → Layer 1。`MEMORY_DAILY_DAYS` 控制近期天数，`MEMORY_MAX_ITEMS` 控制每个 topic 的 active 数量，`MEMORY_MAX_CONTEXT_CHARS` 控制最终字符预算。超过最终预算时按已组装顺序截断，并附加明确的 truncated 提示；当前核心不声称做语义优先级裁剪。

## 结果报告

每次写入或复查至少返回：

```text
memory_root: <relative-or-resolved-path>
runtime: claude | codex | manual
loaded: <layer counts>
written: <relative paths or none>
skipped: <duplicate/sensitive/untrusted reasons>
runtime_evidence: not-observed
next: <one concrete next action>
```

写入脚本不能鉴权真实宿主，因此自身始终返回 `runtime_evidence: not-observed`。Claude/Codex 的真实 Hook smoke 必须作为外部独立证据报告；在此之前禁止使用“自动记忆已经生效”之类措辞。
