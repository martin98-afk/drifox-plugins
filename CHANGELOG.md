# Changelog

## 1.1.0 (2026-06-26)

### 🏗️ 基础设施完善

- **marketplace.json 迁移**：从 `.claude-plugin/marketplace.json` 移至仓库根目录 `marketplace.json`
- **自动生成**：新增 `tools/generate_marketplace.py`，从 `plugin.json` 自动汇总生成 `marketplace.json`，支持 `--check` 一致性检查
- **校验增强**：`tools/validate_plugins.py` 新增 `dependencies` 依赖校验 + `marketplace.json` 一致性校验
- **CI**：新增 `.github/workflows/validate.yml`，PR 自动校验（manifest + marketplace 一致性 + ruff lint + 文档链接检查）
- **社区文件**：新增 PR 模板 + Issue 模板（bug 报告 / 插件请求）
- **兼容性声明**：`evolver` 和 `example-plugin` 补充 `drifox.min_version` 声明
- **文档**：新增 `docs/marketplace-improvement-plan.md` 完善方案

## 1.0.0 (2026-06-26)

### ✨ 新增插件

- **git-workflow**：Git 工作流增强插件 — `/commit` 生成 Conventional Commits 消息、`/branch` 分支命名检查、`/pr` PR 模板生成、PreToolUse Hook 提交前自动校验

### ✨ 初始版本

- **插件**：收录 `evolver`（自进化引擎）和 `example-plugin`（最小参考实现）两个官方插件
- **marketplace.json**：插件市场清单，支持 `/plugin --install` 流程
- **JSON Schema**：`schemas/plugin.schema.json` 覆盖全部 7 类组件（commands/agents/skills/themes/hooks/mcp/lsp）
- **校验脚本**：`tools/validate_plugins.py` 自动校验 manifest + 组件完整性
- **文档**：`docs/` 目录包含 11 份组件规范文档
