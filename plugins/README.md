# 官方插件索引

本目录收录 DriFox 的官方插件。每个插件是独立的目录，遵循统一的 [plugin manifest 规范](../docs/plugin-manifest.md)。

## 索引

| 插件 | 描述 | 组件 | 版本 |
|------|------|------|------|
| [`code-reviewer`](code-reviewer/) | 自动化代码审查 — checklist 审查、质量评分、报告生成 | commands + agents + skills | 1.0.0 |
| [`evolver`](evolver/) | Evolver 自进化引擎 — 基于 GEP 协议沉淀 Agent 经验 | commands + hooks + skills | 1.0.0 |
| [`example-plugin`](example-plugin/) | 最小参考实现，定义官方插件结构与全部 8 类组件约定 | 全部 8 类 | 1.0.0 |
| [`frontend-pro`](frontend-pro/) | 前端开发增强 — 组件规范、a11y 检查、性能最佳实践 | commands + skills | 1.0.0 |
| [`git-workflow`](git-workflow/) | Git 工作流增强 — 分支检查、提交规范、PR 模板生成 | commands + hooks + skills | 1.0.0 |
| [`nuwa-skill`](nuwa-skill/) | 女娲·Skill造人术 — 蒸馏任何人思维框架，附 14 个人物视角 Skill | skills | 1.0.0 |
| [`python-pro`](python-pro/) | Python 开发增强 — PEP 8 / 类型标注 / lint 自动检查 | skills + hooks | 1.0.0 |
| [`test-scaffold`](test-scaffold/) | 测试脚手架生成 — 测试骨架、覆盖率分析、边界场景推荐 | commands + skills | 1.0.0 |

### Claude Code 市场移植精选

以下插件从 Claude Code 官方/社区市场适配而来（保留上游 `.claude-plugin/plugin.json`，新增 DriFox manifest），带来生态验证过的工程工作流：

| 插件 | 描述 | 组件 | 版本 | 来源 |
|------|------|------|------|------|
| [`superpowers`](superpowers/) | Superpowers 核心技能库 — 14 个工程工作流技能（TDD/调试/头脑风暴/计划/代码审查） | skills + hooks | 6.2.0 | obra/superpowers（123k★） |
| [`ecc`](ecc/) | Everything Claude Code — 67 智能体 + 284 技能 + 94 命令的工程工作流全集 | agents + skills + commands | 2.2.0 | affaan-m/everything-claude-code（25k★） |
| [`skill-creator`](skill-creator/) | 技能创作 — 从零创建/优化/评测 skill 的完整方法论 | skills | 1.0.0 | Anthropic 官方 |
| [`code-simplifier`](code-simplifier/) | 代码简化重构智能体 — 不改功能，提升清晰度与可维护性 | agents | 1.0.0 | Anthropic 官方 |
| [`security-guidance`](security-guidance/) | AI 生成代码安全审查 — 静态模式检查 25+ 类漏洞风险 | hooks | 2.0.6 | Anthropic 官方 |
| [`feature-dev`](feature-dev/) | 功能开发工作流 — 探索→架构→实现→审查，3 个专业智能体 | commands + agents | 1.0.0 | Anthropic 官方 |

### 创意与趣味插件

| 插件 | 描述 | 组件 | 版本 | 来源 |
|------|------|------|------|------|
| [`algorithmic-art`](algorithmic-art/) | 程序化艺术生成 — p5.js 创意编码（流动场/粒子系统） | skills | 1.0.0 | Anthropic 官方 |
| [`canvas-design`](canvas-design/) | 设计海报生成 — 设计哲学变成 PNG/PDF 视觉作品 | skills | 1.0.0 | Anthropic 官方 |
| [`slack-gif-creator`](slack-gif-creator/) | 动画 GIF 生成 — Slack 尺寸约束 + 校验工具 | skills | 1.0.0 | Anthropic 官方 |
| [`theme-factory`](theme-factory/) | 主题换肤工厂 — 10 套预设主题 + 即时造新主题 | skills | 1.0.0 | Anthropic 官方 |
| [`web-artifacts-builder`](web-artifacts-builder/) | 复杂交互式 HTML 构建 — React + Tailwind + shadcn/ui | skills | 1.0.0 | Anthropic 官方 |
| [`playground`](playground/) | 交互式 HTML 练习场 — 控件 + 实时预览 + 提示词输出 | skills | 1.0.0 | Anthropic 官方 |
| [`excalidraw-diagram`](excalidraw-diagram/) | 手绘风格图表 — 流程图/时序图/ER 图/思维导图 + 模板库 | skills | 1.0.0 | github/awesome-copilot |

### 语音与多媒体

| 插件 | 描述 | 组件 | 版本 | 来源 |
|------|------|------|------|------|
| [`voice-clone`](voice-clone/) | MiniMax 语音克隆 — 上传音频样本克隆音色 + 克隆音色 TTS 合成 | commands + skills | 1.0.0 | DriFox 原生 |

> **DriFox 运行时内置插件**（`plugin-manager`、`plugin-marketplace`、`context-usage-stats`、`file-tree` 等）随 DriFox 分发，不收录在本仓库市场，避免重复安装造成困惑。

## 组件覆盖矩阵

| | commands | agents | skills | themes | hooks | mcp | lsp | ui |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| code-reviewer | ✅ | ✅ | ✅ | — | — | — | — | — |
| evolver | ✅ | — | ✅ | — | ✅ | — | — | — |
| example-plugin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| frontend-pro | ✅ | — | ✅ | — | — | — | — | — |
| git-workflow | ✅ | — | ✅ | — | ✅ | — | — | — |
| nuwa-skill | — | — | ✅ | — | — | — | — | — |
| python-pro | — | — | ✅ | — | ✅ | — | — | — |
| test-scaffold | ✅ | — | ✅ | — | — | — | — | — |
| superpowers | — | — | ✅ | — | ✅ | — | — | — |
| ecc | ✅ | ✅ | ✅ | — | — | — | — | — |
| skill-creator | — | — | ✅ | — | — | — | — | — |
| code-simplifier | — | ✅ | — | — | — | — | — | — |
| security-guidance | — | — | — | — | ✅ | — | — | — |
| feature-dev | ✅ | ✅ | — | — | — | — | — | — |
| algorithmic-art | — | — | ✅ | — | — | — | — | — |
| canvas-design | — | — | ✅ | — | — | — | — | — |
| slack-gif-creator | — | — | ✅ | — | — | — | — | — |
| theme-factory | — | — | ✅ | — | — | — | — | — |
| web-artifacts-builder | — | — | ✅ | — | — | — | — | — |
| playground | — | — | ✅ | — | — | — | — | — |
| excalidraw-diagram | — | — | ✅ | — | — | — | — | — |
| voice-clone | ✅ | — | ✅ | — | — | — | — | — |

> **ui 组件说明**：ui 插件通过 `ui/__init__.py` 中的 `register_ui(registry)` 函数注册可视化组件（浮动卡片 / 内容块渲染器 / 消息元素工厂），由 DriFox 启动时 `UIPluginRegistry.load_plugin` 加载。详见 [docs/architecture.md](../docs/architecture.md#ui-组件)。
>
> **ui 插件参考**：ui 组件的真实示例（浮动卡片、渲染器、工厂）见 DriFox 运行时内置插件（`plugin-marketplace` / `plugin-manager` / `context-usage-stats` 等），它们随 DriFox 分发，不在本仓库市场内。

## 添加新插件

1. 在 `plugins/` 下新建一个 kebab-case 目录
2. 在该目录下放置 `.drifox-plugin/plugin.json` 声明 manifest
3. 在 manifest 的 `components` 字典里启用你需要的组件（可启用 1-8 个）
4. 按需实现：
   - `commands/<name>.md`
   - `agents/<name>.md`
   - `skills/<name>/SKILL.md`
   - `themes/<name>/<name>.yaml`
   - `hooks/hooks.json` + `hooks/<plugin>_hook.py`
   - `.mcp.json`（插件根）
   - `.lsp.json`（插件根）
   - `ui/__init__.py`（含 `register_ui(registry)`）+ 自定义 widget 模块
5. 跑 `python tools/validate_plugins.py` 确保通过
6. 跑 `python tools/generate_marketplace.py` 更新市场清单
7. 在本 README 的「索引」表格中追加一行
8. 提交 PR

## 安装到 DriFox

```bash
# 复制整个插件目录到 DriFox 插件目录
xcopy plugins\evolver %USERPROFILE%\.drifox\plugins\evolver /E /I /Y
# 或
cp -r plugins/evolver ~/.drifox/plugins/
```

启动 DriFox，插件会被自动发现。
