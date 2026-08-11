# Changelog

## 2.4.0 (2026-08-12)

### ✨ 新增 ui-motion-skills 插件（社区生态）

- **`ui-motion-skills`** — UI 动效设计技能集，打包 [emilkowalski/skills](https://github.com/emilkowalski/skills)（MIT，28k★）全部 10 个技能，内容与上游保持一致：
  - 自动触发：`emil-design-eng`（核心哲学）、`animate`（从零构建动画）、`animation-vocabulary`（动效术语反查）、`apple-design`（Apple 设计原则）、`ask-sonner`（Sonner toast 指南）
  - 显式调用：`review-animations`（严格评审）、`improve-animations`（全库审计）、`find-animation-opportunities`（寻找动效机会）、`pick-ui-library`（UI 库选型）、`prototype`（多版本原型对比）
  - 含辅助文档：RECIPES.md / API.md / AUDIT.md / STANDARDS.md / PLAN-TEMPLATE.md / PICKER.md
- **机制**：`marketplace.json` 重新生成（56→57 个插件），`ui-motion-skills` 通过 `validate_plugins.py` 校验（零 error/warning）

## 2.3.0 (2026-08-11)

### ✨ 新增 minimax-h3 插件（DriFox 原生）

- **`minimax-h3`** — MiniMax H3 全模态音视频生成：文本/图片/视频/音频 → 带原生立体声音频的视频（768P/2K，4-15s）
  - `/minimax-h3` 命令引导完整流程（技能写提示词 → 提交任务 → 轮询 → 下载）
  - `scripts/h3_video.py` 三个子命令：create / query / download，支持 t2va / i2va / fl2va / ref2va 全部输入模式
  - `skills/h3-prompt-writing/` 搬运自 MiniMax-AI/MiniMax-H3（SKILL.md + base-en.txt + ref-en.txt），原样保留
  - API Key 从环境变量 `MINIMAX_API_KEY` 或 `~/.minimax/api_key` 读取（与 voice-clone 约定一致）
  - 合规声明：H3 技能内容遵循 MiniMax H3 Community License，生成内容受平台审核约束

## 2.2.0 (2026-08-08)

### ✨ 新增 voice-clone 插件（DriFox 原生）

- **`voice-clone`** — MiniMax 语音克隆：上传 10s+ 音频样本 → 克隆为永久 voice_id → 用克隆音色合成 TTS
  - `/voice-clone` 命令引导完整流程（采集样本 → 克隆 → 合成）
  - `scripts/voice_clone.py` 三个子命令：clone / tts / upload
  - API Key 从环境变量 `MINIMAX_API_KEY` 或 `~/.minimax/api_key` 读取（与 guizang-ppt-skill 约定一致）
  - 实测验证：上传 ✓、TTS 合成 ✓（克隆接口受账号权限限制，需开通 voice clone 权限的 key）
  - 授权提醒：仅克隆用户有权使用的声音，不得用于冒充或欺诈

## 2.1.0 (2026-08-08)

### ✨ 新增创意趣味插件（7 个，Claude 生态）

- **`algorithmic-art`**（Anthropic 官方）— p5.js 程序化艺术生成（流动场/粒子系统/种子随机）
- **`canvas-design`**（Anthropic 官方）— 设计哲学产出 PNG/PDF 海报视觉作品，内置设计字体库
- **`slack-gif-creator`**（Anthropic 官方）— 动画 GIF 生成（Slack 尺寸约束 + 校验工具，依赖 pillow/imageio）
- **`theme-factory`**（Anthropic 官方）— 10 套预设主题 + 即时生成新主题，给 HTML artifact 换肤
- **`web-artifacts-builder`**（Anthropic 官方）— 复杂交互式 HTML 构建（React + Tailwind + shadcn/ui）
- **`playground`**（Anthropic 官方插件）— 交互式 HTML 练习场（控件 + 实时预览 + 提示词复制）
- **`excalidraw-diagram`**（github/awesome-copilot）— 手绘风格图表生成（流程图/时序图/ER 图/思维导图 + 模板库 + Python 工具）

- **机制**：`marketplace.json` 重新生成（34→41 个插件），全部通过 `validate_plugins.py`（新增插件零 error/warning）

## 2.0.0 (2026-08-08)

### ✨ 新增 Claude Code 市场适配插件（6 个）

从 Claude Code 官方/社区市场适配高星插件，新增 DriFox manifest（保留上游 `.claude-plugin/plugin.json` 溯源）：

- **`superpowers`**（obra/superpowers，123k★）— 14 个工程工作流技能（TDD/调试/头脑风暴/写计划/代码审查/子智能体驱动开发），SessionStart 注入技能指引（DriFox 原生 Python hook）
- **`ecc`**（affaan-m/everything-claude-code，25k★）— 67 智能体 + 284 技能 + 94 命令的工程工作流全集
  - 所有命令补齐 DriFox 必需的 `type: prompt` frontmatter
  - 5 个 skill 目录名与 `name` 字段对齐；16 个多行 `>-` description 折叠为单行
  - hooks 未移植（上游为 node 内联脚本，强依赖 Claude 特有运行时）
- **`skill-creator`**（Anthropic 官方）— 技能创作/优化/评测完整流程（含评测脚本与基准测试）
- **`code-simplifier`**（Anthropic 官方）— 代码简化重构智能体（@code-simplifier）
- **`security-guidance`**（Anthropic 官方）— AI 生成代码安全审查；移植静态模式检查层（25 条规则），改写为 DriFox 原生 Python hook（PostToolUse 触发）；LLM diff 审查层未移植
- **`feature-dev`**（Anthropic 官方）— 功能开发工作流（/feature-dev + code-explorer/code-architect/code-reviewer 三智能体）

- **机制**：`marketplace.json` 由 `generate_marketplace.py` 重新生成（34 个插件），`validate_plugins.py` 全部通过（新增插件零 error/warning）

## 0.1.0 (2026-08-04)
### Added
- ip-switcher 插件：免费模型限流自动换 IP（429 检测 + 代理池轮换 + 仪表盘）
  - monkey patch openai SDK：白名单模型请求走本地代理池
  - 429 自动换 IP + 自动重试（默认 3 次，2s 退避）
  - 仪表盘浮动卡片：当前出口 IP、换绑历史、统计、手动换 IP
  - 代理池内置管理（shadow1ng/ProxyPool vendor 打包，sticky 模式）
  - 配置存 user-custom 插件（随云端备份恢复）

## 1.3.0 (2026-08-03)

### 🗑️ 移除 DriFox 运行时内置插件

- **背景**：`plugin-manager`、`plugin-marketplace`、`context-usage-stats`、`file-tree` 等插件已随 DriFox 运行时内置分发（`D:/work/DriFox/plugins/`），继续出现在插件市场中会让用户困惑（误以为需要额外安装 / 重复安装）。
- **移除内容**：
  - 删除 `plugins/plugin-marketplace/`、`plugins/plugin-manager/`、`plugins/context-usage-stats/`、`plugins/file-tree/` 四个插件目录
  - `marketplace.json` 同步重新生成，市场不再收录 DriFox 内置插件
- **机制保护**：
  - `tools/generate_marketplace.py` 新增 `DRIFOX_BUILTIN_PLUGINS` 名单，生成时跳过 DriFox 运行时内置插件
  - `tools/validate_plugins.py` 的 marketplace 一致性检查同步跳过内置插件
- **文档同步**：`README.md`、`plugins/README.md`、`docs/architecture.md`、`docs/plugin-development.md`、`plugins/git-dashboard/README.md` 更新插件索引与 ui 参考实现指引

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
