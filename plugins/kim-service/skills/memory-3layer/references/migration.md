# Legacy 迁移规则

旧版数据目录是 `<repo>/.claude/memory/`，新版默认目录是 `<repo>/.memory-3layer/`。迁移把数据从某个宿主目录中解耦；它不是删除旧数据的清理命令。

## 默认行为

```bash
python scripts/migrate_legacy_memory.py --project-dir <目标项目>
```

- source 默认 `.claude/memory/`。
- target 默认 `.memory-3layer/`。
- 只复制识别到的三层数据。
- 目标同名文件已存在时跳过，不覆盖。
- 不删除或改写 source。
- 返回 copied、skipped、conflict 和 invalid 列表。

自定义路径：

```bash
python scripts/migrate_legacy_memory.py --project-dir <目标项目> --source <项目内旧路径> --target <项目内新路径>
```

自定义 source 与 target 仍必须位于 `--project-dir` 内；工具不会跨项目读取或写入。

## 迁移前门禁

1. source 必须位于用户指定项目中，不能从不相关项目猜测。
2. source 与 target 解析后不能相同，也不能互相嵌套形成递归复制。
3. target 若已有数据，必须先生成冲突清单。
4. JSON 文件必须可解析；损坏文件列入 `invalid`，不尝试自动修复。
5. 发现秘密或本机私有路径时停止对应文件复制并报告。

## 迁移后验收

- 运行 `python scripts/check_memory_3layer.py`。
- 比较源和目标的相对文件清单与有效内容计数。
- 用目标平台新会话加载一次，或在 manual 模式直接运行 loader。
- 验证完成前保留 `.claude/memory/`；本工具永不自动删除它。

迁移校验通过只证明数据可读，不证明 Claude Code 或 Codex Hook 已被宿主信任并触发。
