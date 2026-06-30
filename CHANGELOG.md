# Changelog

## 1.2.0 (2026-07-01)

### ✨ 新增 ui 组件类型（第 8 类）

- **3 个 ui 插件**（官方 UI 三件套）：
  - **`plugin-marketplace`** — 官方插件市场浮动卡片 + 2 个内容块渲染器（`plugin_marketplace_grid` / `plugin_marketplace_card`），覆盖浏览 / 搜索 / 安装
  - **`plugin-manager`** — 插件管理浮动卡片，列出已安装插件并支持启用 / 禁用 / 卸载
  - **`context-usage-stats`** — 对话上下文用量统计浮动卡片，token / 消息量趋势 + 会话活跃度图表
- **Schema**：`schemas/plugin.schema.json` 新增 `components.ui` 字段
- **校验**：`tools/validate_plugins.py` 新增 `check_ui_dir()` — 校验 `ui/__init__.py` 存在 + `register_ui(registry)` 顶层函数
- **marketplace 生成**：`tools/generate_marketplace.py` 新增 `ui` 分类识别 + 统计类关键词（`stats` / `analytics` / `token` / `context` / `dashboard`）
- **文档同步**：
  - 根 `README.md` 与 `plugins/README.md` 7→8 类能力，组件覆盖矩阵新增 `ui` 列
  - `docs/architecture.md` 目录约定新增 `ui/` 段，加入「ui 组件」章节介绍 3 个扩展点 + 3 个官方 UI 插件参考实现
  - `docs/plugin-manifest.md` / `docs/plugin-development.md` / `CONTRIBUTING.md` 同步 7→8
- **CI**：
  - `.github/workflows/validate.yml` 新增 `auto-fix-marketplace` job：当 `generate_marketplace.py --check` 失败时自动修复
  - 触发场景：PR 推送 → push 回 PR head 分支；push main → push 回 main，保证 main 始终 green
  - commit 携带 `[skip ci]` 防止无限循环
  - 非 marketplace 漂移的失败：PR 留 comment，main push 让 job 失败（不污染 main 历史）
  - 加 `concurrency` 防止并发 PR 互相干扰

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
