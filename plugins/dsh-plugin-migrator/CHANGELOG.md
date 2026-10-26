# 更新日志

## 1.0.0

首次发布。把 DeepSeek Harness（`dsh`）插件迁移成 DriFox 插件。

### 能力

- **扫描**：解析 `package.json` 的 `dsh` 声明（bundle.patch / client.inject / CLI bin）、`cordis.patch.yml` 的 insert 行（含 `cordis:group` 递归展开、`!!js` 标签容错、`@scope/pkg/subpath` 子导出识别）、`dshWorkshop` 元数据与 `engines.dsh`、包内 skill bundle（含包根 `SKILL.md`）。
- **七条搬运通道**：`skills`（port）、`agents`（port 骨架）、`commands`（stub）、`tools`（stub）、`hooks`（stub）、`mcp`（stub）、`ui`（stub 骨架）。
- **降级政策**：可 1:1 映射的自动落盘；不可映射的落为显式报错的 stub 并标 `MIGRATION_TODO`；无等价载体的进报告未映射段。任何未被通道接走的 stub 强制进报告，不允许静默丢弃。
- **聚合 bundle 拒识**：patch 行数 ≥ 20 判定为 harness 组合层，提示改为按能力单元迁移。
- **三层证明**：结构一致性 / 真实运行 / 人工语义比对，互不替代。

### 验证

- `validate_plugins.py --strict` 零 error 零 warn。
- hooks 骨架经 DriFox 真实 `HookManager` 注册并逐事件触发，5/5 成功。
- ui 骨架经真实 `UIPluginRegistry` 加载成功，浮动卡自动派生命令。
