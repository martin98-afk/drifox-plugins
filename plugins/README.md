# 官方插件索引

本目录收录 DriFox 的官方插件。每个插件是独立的目录，遵循统一的 [plugin manifest 规范](../docs/plugin-manifest.md)。

## 索引

| 插件 | 描述 | 组件 | 版本 |
|------|------|------|------|
| [`code-reviewer`](code-reviewer/) | 自动化代码审查 — checklist 审查、质量评分、报告生成 | commands + agents + skills | 1.0.0 |
| [`evolver`](evolver/) | Evolver 自进化引擎 — 基于 GEP 协议沉淀 Agent 经验 | commands + hooks + skills | 1.0.0 |
| [`example-plugin`](example-plugin/) | 最小参考实现，定义官方插件结构与全部 7 类组件约定 | 全部 7 类 | 1.0.0 |
| [`frontend-pro`](frontend-pro/) | 前端开发增强 — 组件规范、a11y 检查、性能最佳实践 | commands + skills | 1.0.0 |
| [`git-workflow`](git-workflow/) | Git 工作流增强 — 分支检查、提交规范、PR 模板生成 | commands + hooks + skills | 1.0.0 |
| [`python-pro`](python-pro/) | Python 开发增强 — PEP 8 / 类型标注 / lint 自动检查 | skills + hooks | 1.0.0 |
| [`test-scaffold`](test-scaffold/) | 测试脚手架生成 — 测试骨架、覆盖率分析、边界场景推荐 | commands + skills | 1.0.0 |

## 组件覆盖矩阵

| | commands | agents | skills | themes | hooks | mcp | lsp |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| code-reviewer | ✅ | ✅ | ✅ | — | — | — | — |
| evolver | ✅ | — | ✅ | — | ✅ | — | — |
| example-plugin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| frontend-pro | ✅ | — | ✅ | — | — | — | — |
| git-workflow | ✅ | — | ✅ | — | ✅ | — | — |
| python-pro | — | — | ✅ | — | ✅ | — | — |
| test-scaffold | ✅ | — | ✅ | — | — | — | — |

## 添加新插件

1. 在 `plugins/` 下新建一个 kebab-case 目录
2. 在该目录下放置 `.drifox-plugin/plugin.json` 声明 manifest
3. 在 manifest 的 `components` 字典里启用你需要的组件（可启用 1-7 个）
4. 按需实现：
   - `commands/<name>.md`
   - `agents/<name>.md`
   - `skills/<name>/SKILL.md`
   - `themes/<name>/<name>.yaml`
   - `hooks/hooks.json` + `hooks/<plugin>_hook.py`
   - `.mcp.json`（插件根）
   - `.lsp.json`（插件根）
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
