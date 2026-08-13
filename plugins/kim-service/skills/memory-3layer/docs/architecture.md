# 架构

Memory 3-Layer 把平台相关生命周期与平台中立数据核心分开：

```text
Claude Code Hooks ─┐
                   ├─> Python adapters/core ─> .memory-3layer/
Codex Hooks ───────┤                         ├─ MEMORY.md
                   │                         ├─ memory/YYYY-MM-DD.md
Manual workflow ───┘                         └─ areas/topics/*/items.json
```

## 三层职责

| 层 | 格式 | 用途 | 生命周期 |
|---|---|---|---|
| Layer 1 | JSON | 可检索事实、分类、冲突与状态 | active → superseded，保留历史 |
| Layer 2 | Markdown | 每日工作轨迹与时间上下文 | 按日追加，加载近期窗口 |
| Layer 3 | Markdown | 人工确认的长期隐性知识 | 低频维护，完整但保持简短 |

## 默认目录

```text
.memory-3layer/
├── MEMORY.md
├── memory/
│   └── YYYY-MM-DD.md
├── areas/
│   └── topics/
│       └── <topic>/items.json
└── data/
    └── session_state.json
```

`MEMORY_DIR` 可以覆盖根目录。覆盖后，三层数据仍保持同一相对结构。

## 数据流

1. Session start：按 Layer 3 → Layer 2 → Layer 1 加载，并执行条目数/日期预算。
2. Tool completion：适配器只提取白名单字段，核心执行脱敏、分类与去重。
3. Pre-compact：保存最小恢复状态，不保存完整聊天。
4. Review：冲突或过时事实先形成建议，确认后把旧项标为 `superseded`。

Claude Code 和 Codex 的配置不同，但都调用同一核心并写入同一目录。其他平台只有 manual 数据流；没有对应 Hook 适配器时不会自动运行。

## 证明分层

- 文件结构和测试通过：`artifact_status`。
- `.claude/settings.json` 或 `.codex/hooks.json` 安全合并：`adapter_status`。
- 真实宿主事件触发并产生预期读写：`runtime_status`。

三层证据不能互相替代。
