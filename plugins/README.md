# 官方插件索引

本目录收录 DriFox 的官方插件。每个插件是独立的目录，遵循统一的 [plugin manifest 规范](../docs/plugin-manifest.md)。

## 索引

| 插件 | 描述 | 组件 | 版本 |
|------|------|------|------|
| [`code-reviewer`](code-reviewer/) | 自动化代码审查 — checklist 审查、质量评分、报告生成 | commands + agents + skills | 1.0.0 |
| [`context-usage-stats`](context-usage-stats/) | 对话上下文用量统计 — token/消息量趋势、会话活跃度图表 | ui | 0.1.0 |
| [`evolver`](evolver/) | Evolver 自进化引擎 — 基于 GEP 协议沉淀 Agent 经验 | commands + hooks + skills | 1.0.0 |
| [`example-plugin`](example-plugin/) | 最小参考实现，定义官方插件结构与全部 8 类组件约定 | 全部 8 类 | 1.0.0 |
| [`frontend-pro`](frontend-pro/) | 前端开发增强 — 组件规范、a11y 检查、性能最佳实践 | commands + skills | 1.0.0 |
| [`git-workflow`](git-workflow/) | Git 工作流增强 — 分支检查、提交规范、PR 模板生成 | commands + hooks + skills | 1.0.0 |
| [`plugin-manager`](plugin-manager/) | 插件管理面板 — 在 DriFox 窗口内启 / 禁 / 卸已安装插件 | ui | 0.1.0 |
| [`plugin-marketplace`](plugin-marketplace/) | 官方插件市场 — 浏览 / 安装 / 管理 drifox-plugins 全部插件 | ui | 0.1.0 |
| [`python-pro`](python-pro/) | Python 开发增强 — PEP 8 / 类型标注 / lint 自动检查 | skills + hooks | 1.0.0 |
| [`test-scaffold`](test-scaffold/) | 测试脚手架生成 — 测试骨架、覆盖率分析、边界场景推荐 | commands + skills | 1.0.0 |

## 组件覆盖矩阵

| | commands | agents | skills | themes | hooks | mcp | lsp | ui |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| code-reviewer | ✅ | ✅ | ✅ | — | — | — | — | — |
| context-usage-stats | — | — | — | — | — | — | — | ✅ |
| evolver | ✅ | — | ✅ | — | ✅ | — | — | — |
| example-plugin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| frontend-pro | ✅ | — | ✅ | — | — | — | — | — |
| git-workflow | ✅ | — | ✅ | — | ✅ | — | — | — |
| plugin-manager | — | — | — | — | — | — | — | ✅ |
| plugin-marketplace | — | — | — | — | — | — | — | ✅ |
| python-pro | — | — | ✅ | — | ✅ | — | — | — |
| test-scaffold | ✅ | — | ✅ | — | — | — | — | — |

> **ui 组件说明**：ui 插件通过 `ui/__init__.py` 中的 `register_ui(registry)` 函数注册可视化组件（浮动卡片 / 内容块渲染器 / 消息元素工厂），由 DriFox 启动时 `UIPluginRegistry.load_plugin` 加载。详见 [docs/architecture.md](../docs/architecture.md#ui-组件)。
>
> **官方 UI 三件套**：`plugin-marketplace`（找 / 装）+ `plugin-manager`（启 / 禁 / 卸）+ `context-usage-stats`（看用量），覆盖完整的插件生命周期。

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
