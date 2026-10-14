# 官方插件索引

本目录收录 DriFox 的官方插件。每个插件是独立的目录，遵循统一的 [plugin manifest 规范](../docs/plugin-manifest.md)。

## 索引

| 插件 | 描述 | 组件 | 版本 |
|------|------|------|------|
| [`autoloop`](autoloop/) | AutoLoop 自动循环模式 — 规划→执行→归档 三阶段长任务自动执行（对话引擎插件化首例） | ui + agents | 1.0.0 |
| [`code-reviewer`](code-reviewer/) | 自动化代码审查 — checklist 审查、质量评分、报告生成 | commands + agents + skills | 1.0.0 |
| [`codegraph-tools`](codegraph-tools/) | CodeGraph 语义级代码智能 — 搜索/调用链/影响分析/索引管理（codegraph_explore） | tools | 1.0.0 |
| [`dsh-router`](dsh-router/) | 任务感知路由 — build/fix 行为带划分、persona 选择、引导注入（源自 dsh-router-standard） | commands + agents + skills | 1.0.0 |
| [`dsh-super-injector`](dsh-super-injector/) | 运行时注入观测 — 会话审计记录 + 插件状态/自检（源自 dsh-super-injector） | hooks + tools | 1.0.0 |
| [`evolver`](evolver/) | Evolver 自进化引擎 — 基于 GEP 协议沉淀 Agent 经验 | commands + hooks + skills | 1.0.0 |
| [`example-plugin`](example-plugin/) | 最小参考实现，定义官方插件结构与全部 9 类组件约定 | 全部 9 类 | 1.0.0 |
| [`frontend-pro`](frontend-pro/) | 前端开发增强 — 组件规范、a11y 检查、性能最佳实践 | commands + skills | 1.0.0 |
| [`git-workflow`](git-workflow/) | Git 工作流增强 — 分支检查、提交规范、PR 模板生成 | commands + hooks + skills | 1.0.0 |
| [`hashline-edit`](hashline-edit/) | pi 式 hashline 锚点编辑 — 覆盖 read/edit/multi_edit（纯锚点模式），行号+上下文哈希定位，链式编辑 | tools | 0.1.0 |
| [`nuwa-skill`](nuwa-skill/) | 女娲·Skill造人术 — 蒸馏任何人思维框架，附 14 个人物视角 Skill | skills | 1.0.0 |
| [`python-pro`](python-pro/) | Python 开发增强 — PEP 8 / 类型标注 / lint 自动检查 | skills + hooks | 1.0.0 |
| [`test-scaffold`](test-scaffold/) | 测试脚手架生成 — 测试骨架、覆盖率分析、边界场景推荐 | commands + skills | 1.0.0 |
| [`ui-motion-skills`](ui-motion-skills/) | UI 动效设计技能集 — 动画构建/评审/审计/词汇 + Apple 设计 + UI 库选型 + 原型对比 + Sonner 指南（源自 emilkowalski/skills） | skills | 1.0.0 |

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

### UI 组件插件

| 插件 | 描述 | 组件 | 版本 | 来源 |
|------|------|------|------|------|
| [`autoloop`](autoloop/) | AutoLoop 自动循环模式 — 规划→执行→归档 三阶段长任务自动执行（从主程序对话引擎整体迁移，对话引擎插件化首例） | ui + agents | 1.0.0 | DriFox 原生 |
| [`calendar`](calendar/) | 日历 tab — 欢迎卡片内嵌月视图，上/下月切换 + 今天高亮 | ui | 1.0.0 | DriFox 原生 |
| [`project-dashboard`](project-dashboard/) | 项目信息看板 — commit 趋势/语言分布/贡献者/文件统计图表 | ui | 0.1.0 | DriFox 原生 |

### 主题插件

| 插件 | 描述 | 组件 | 版本 | 来源 |
|------|------|------|------|------|
| [`laputa-fog`](laputa-fog/) | 浮岛·雾青主题 — 宫崎骏《天空之城》灵感浅色主题，灰蓝主调 + 琥珀暖金点缀 + 专属背景图 | themes | 1.0.0 | DriFox 原生 |
| [`rdr2`](rdr2/) | 荒野大镖客主题 — Red Dead Redemption 2 灵感深色主题，血红主调 + 荒漠暖金点缀 + 专属背景图 | themes | 1.0.0 | DriFox 原生 |
| [`fe-fw`](fe-fw/) | 银翼圣焰主题 — 火焰纹章 万缕千丝 灵感深色主题，火焰橙红 + 命运女神紫双色组合 + 银白文字 + Leda 立绘背景图 | themes | 1.0.0 | DriFox 原生 |

### 语音与多媒体

| 插件 | 描述 | 组件 | 版本 | 来源 |
|------|------|------|------|------|
| [`voice-clone`](voice-clone/) | MiniMax 语音克隆 — 上传音频样本克隆音色 + 克隆音色 TTS 合成 | commands + skills | 1.0.0 | DriFox 原生 |
| [`minimax-h3`](minimax-h3/) | MiniMax H3 全模态视频生成 — 文本/图片/视频/音频转带立体声音频的视频 + H3 提示词技能 | commands + skills | 1.0.0 | DriFox 原生 |

> **DriFox 运行时内置插件**（`plugin-manager`、`plugin-marketplace`、`context-usage-stats`、`file-tree` 等）随 DriFox 分发，不收录在本仓库市场，避免重复安装造成困惑。

### HanaAgent 连接器迁移

54 个远程 MCP 连接器，从 [HanaAgent 官方市场](https://github.com/liliMozi/hana-connectors)（official-global，批次 v2026.10.10）整体迁移而来。每个连接器指向服务方自营的远程 MCP 端点，不含服务端代码，也不托管凭据。统一命名为 `hana-conn-<id>`，工具名前缀 `mcp__hana-<id>__`。

| 插件 | 描述 | 组件 | 版本 |
|------|------|------|------|
| [`hana-conn-github`](hana-conn-github/) | GitHub — 仓库、Issue、PR 与 Actions 管理（Bearer Token） | mcp | 1.0.0 |
| [`hana-conn-gitlab`](hana-conn-gitlab/) | GitLab — 仓库、Issue、MR 管理（OAuth） | mcp | 1.0.0 |
| [`hana-conn-gitee`](hana-conn-gitee/) | Gitee — 仓库、文件、Issue 与 PR（Bearer Token） | mcp | 1.0.0 |
| [`hana-conn-context7`](hana-conn-context7/) | Context7 — 开源库最新文档与代码示例 | mcp | 1.0.0 |
| [`hana-conn-notion`](hana-conn-notion/) | Notion — 页面与数据库搜索、读写（OAuth） | mcp | 1.0.0 |
| [`hana-conn-linear`](hana-conn-linear/) | Linear — 任务与项目管理（OAuth） | mcp | 1.0.0 |
| [`hana-conn-sentry`](hana-conn-sentry/) | Sentry — 错误与性能监控（OAuth） | mcp | 1.0.0 |
| [`hana-conn-stripe`](hana-conn-stripe/) | Stripe — 支付与订阅管理（OAuth） | mcp | 1.0.0 |
| [`hana-conn-figma`](hana-conn-figma/) | Figma — 设计文件读取与评论（OAuth） | mcp | 1.0.0 |
| [`hana-conn-supabase`](hana-conn-supabase/) | Supabase — 数据库与后端服务（OAuth） | mcp | 1.0.0 |
| [`hana-conn-cloudflare-bindings`](hana-conn-cloudflare-bindings/) | Cloudflare Workers 与 KV/R2/D1 管理（OAuth） | mcp | 1.0.0 |
| [`hana-conn-vercel`](hana-conn-vercel/) | Vercel — 项目与部署管理（OAuth） | mcp | 1.0.0 |
| [`hana-conn-amap`](hana-conn-amap/) | 高德地图 — 地点、路线、天气与周边（Query Key） | mcp | 1.0.0 |
| [`hana-conn-baidu-map`](hana-conn-baidu-map/) | 百度地图 — 地点、路线、路况与天气（Query AK） | mcp | 1.0.0 |
| [`hana-conn-tencent-map`](hana-conn-tencent-map/) | 腾讯位置服务 — 地点、周边与天气（Query Key） | mcp | 1.0.0 |
| [`hana-conn-dingtalk-contacts`](hana-conn-dingtalk-contacts/) | 钉钉通讯录 — 组织成员与部门查询（专属链接） | mcp | 1.0.0 |
| [`hana-conn-zhipu-websearch`](hana-conn-zhipu-websearch/) | 智谱联网搜索（Bearer Key） | mcp | 1.0.0 |

> 上表列常用 17 个。全部 54 个见 `plugins/hana-conn-*` 目录，安装后在设置 → MCP 连接器中逐个启用。
>
> 认证方式分四类：**OAuth**（29 个，装后在设置里点授权，走动态注册 + PKCE，token 自动刷新）；**Bearer**（7 个，填环境变量如 `GITHUB_TOKEN`）；**Query Key**（4 个，需按各插件 README 把 key 拼进 `url`）；**专属链接**（6 个，需按 README 替换为账号签发的链接）。后两类是 DriFox 的 MCP 配置只支持 HTTP 头与环境变量注入所致，无法自动完成。
>
> `hana-conn-context7` 与既有 [`context7`](context7/) 功能重复：前者连官方远程端点，后者走本地 npx。两者 server 名已用前缀区分，可共存，按需启用其一。

## 组件覆盖矩阵

| | commands | agents | skills | themes | hooks | mcp | lsp | ui | tools |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| autoloop | — | ✅ | — | — | — | — | — | ✅ | — |
| code-reviewer | ✅ | ✅ | ✅ | — | — | — | — | — | — |
| codegraph-tools | — | — | — | — | — | — | — | — | ✅ |
| dsh-router | ✅ | ✅ | ✅ | — | — | — | — | — | — |
| dsh-super-injector | — | — | — | — | ✅ | — | — | — | ✅ |
| evolver | ✅ | — | ✅ | — | ✅ | — | — | — |
| example-plugin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| frontend-pro | ✅ | — | ✅ | — | — | — | — | — |
| git-workflow | ✅ | — | ✅ | — | ✅ | — | — | — |
| hashline-edit | — | — | — | — | — | — | — | — | ✅ |
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
| minimax-h3 | ✅ | — | ✅ | — | — | — | — | — |
| calendar | — | — | — | — | — | — | — | ✅ |
| project-dashboard | — | — | — | — | — | — | — | ✅ |
| laputa-fog | — | — | — | ✅ | — | — | — | — |
| rdr2 | — | — | — | ✅ | — | — | — | — |
| fe-fw | — | — | — | ✅ | — | — | — | — |
| ui-motion-skills | — | — | ✅ | — | — | — | — | — |

> **tools 组件说明**：tools 插件通过 `tools/*.py` 中的 `register(registry)` 函数注册内置工具，由 DriFox 启动时 `PluginToolLoader` 加载（危险级别强制声明）。真实示例见 DriFox 运行时内置插件（`plugins/system/tools/`：file/web/automation/codegraph/terminal/diagnostics 等）。
>
> **ui 组件说明**：ui 插件通过 `ui/__init__.py` 中的 `register_ui(registry)` 函数注册可视化组件（浮动卡片 / 内容块渲染器 / 消息元素工厂），由 DriFox 启动时 `UIPluginRegistry.load_plugin` 加载。详见 [docs/architecture.md](../docs/architecture.md#ui-组件)。
>
> **ui 插件参考**：ui 组件的真实示例（浮动卡片、渲染器、工厂）见 DriFox 运行时内置插件（`plugin-marketplace` / `plugin-manager` / `context-usage-stats` 等），它们随 DriFox 分发，不在本仓库市场内。

## 添加新插件

1. 在 `plugins/` 下新建一个 kebab-case 目录
2. 在该目录下放置 `.drifox-plugin/plugin.json` 声明 manifest
3. 在 manifest 的 `components` 字典里启用你需要的组件（可启用 1-8 个）
4. 按需实现：
   - `tools/<name>.py`（含 `register(registry)`）
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
