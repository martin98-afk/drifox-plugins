# 贡献指南

感谢你愿意为 DriFox 插件生态贡献力量。本文档说明如何提交一个新插件或改进现有插件。

## 工作流概览

```
1. Fork 仓库
   ↓
2. 基于 main 创建特性分支: feat/<plugin-name>
   ↓
3. 在 plugins/<your-plugin>/ 开发
   ↓
4. 本地运行 python tools/validate_plugins.py
   ↓
5. 提交 commit（**不要**手动改 marketplace.json；不需要本地跑 generate_marketplace.py）
   ↓
6. 创建 Pull Request
   ↓
7. CI 自动跑 generate_marketplace.py + validate_plugins.py，失败时 drifox-bot 自动 commit 修复
   ↓
8. Maintainer 评审 & merge
```

> **marketplace.json 由 CI 自动同步 — 不要本地手动改！**
>
> `marketplace.json` 是机器生成的清单（`drifox plugin install` 的数据源）。**开发者不需要、也不应该本地修改它**，原因：
> - 任何本地生成的版本与远端不一致，push 时必然冲突（marketplace.json 是 CI bot 频繁 commit 的热点文件）
> - 即使本地成功生成并合并，bot 下一次 commit 也会把它覆盖回去
> - 真正的权威源是 `plugins/<name>/.drifox-plugin/plugin.json`，CI 会从中读出字段并生成
>
> 何时跑 `generate_marketplace.py`？
> - **本地排查**：仅当你想看新增插件在 marketplace.json 里渲染成什么格式、方便对照 schema
> - **CI 修复路径**：`auto-fix-marketplace` job（`.github/workflows/validate.yml`）是唯一权威入口
>
> 工作机制：
> - PR 场景 → 校验失败时 bot 把修复 commit 到 PR head 分支
> - push main 场景 → bot 把修复 commit 到 main（保证 main 始终 green）
> - bot commit 含 `[skip ci]`，GitHub Actions 原生跳过整个 workflow，不会无限循环

## 插件开发

### 起步

最快的方式是复制 `plugins/example-plugin/`，再按需改造：

```bash
cp -r plugins/example-plugin plugins/your-plugin
```

然后修改：

1. `plugins/your-plugin/.drifox-plugin/plugin.json` — 改 `name`、`description`、`author`、`components`
2. `plugins/your-plugin/README.md` — 重写插件说明
3. 各组件目录里的占位文件

### 必须遵守的约束

| 约束 | 说明 |
|------|------|
| 插件根目录必须有 `.drifox-plugin/plugin.json` | manifest 是 DriFox 识别插件的唯一依据 |
| `plugin.json` 必须能被 `schemas/plugin.schema.json` 校验通过 | 跑 `python tools/validate_plugins.py` 验证 |
| 启用的组件必须有对应目录与文件 | `components.commands=true` ⇒ 至少 1 个 `commands/*.md`；`components.ui=true` ⇒ `ui/__init__.py` + widget 模块；`components.tools=true` ⇒ 至少 1 个 `tools/*.py`；`components.providers=true` ⇒ 至少 1 个 `providers/*.py` |
| 钩子 Python 文件必须能 `python -m py_compile` 通过 | 语法层面不能有错 |
| 每个 `commands/*.md` 顶部必须有 frontmatter | 至少包含 `description` 和 `type` |
| 每个 `skills/<name>/SKILL.md` 顶部必须有 frontmatter | 至少包含 `name` 和 `description` |
| ui 插件的 `ui/__init__.py` 必须定义 `register_ui(registry)` 顶层函数 | 由 DriFox 启动时 `UIPluginRegistry.load_plugin` 调用 |
| tools 插件的 `tools/*.py` 必须定义 `register(registry)` 顶层函数 | 由 DriFox 启动时 `PluginToolLoader` 调用 |
| providers 插件的 `providers/*.py` 必须定义 `register(registry)` 顶层函数 | 由 DriFox 启动时 `ProviderWatcher` 调用 |

详细字段定义见 [docs/plugin-manifest.md](docs/plugin-manifest.md)。

### 命名约定

| 资产 | 约定 | 示例 |
|------|------|------|
| 插件目录 | `kebab-case` | `evolver`, `code-review` |
| 命令文件 | `kebab-case.md` | `commit.md`, `evolver.md` |
| 技能目录 | `kebab-case/` | `evolver/`, `feature-dev/` |
| 钩子 Python 文件 | `<plugin_name>_hook.py` | `evolver_hook.py` |
| manifest | 固定路径 | `.drifox-plugin/plugin.json` |

### Commit 规范

遵循简化 Conventional Commits：

```
feat(<plugin-name>): 添加新命令 /xx
fix(<plugin-name>): 修复 xx 场景下的 yy
docs(plugins/<plugin-name>): 补充 xx 用法说明
refactor(<plugin-name>): 拆分 xx 模块
chore: 升级 schema 到 v2
```

### 提 PR 前

跑一遍校验：

```bash
# 1. 校验插件 manifest + 组件完整性 + marketplace 一致性
python tools/validate_plugins.py
```

输出应全部为 `OK`。如果失败，PR 不会被合入。

> ⚠️ **不要**跑 `python tools/generate_marketplace.py` 并把 marketplace.json 改动一起 commit —— CI 会自动同步。如果你本地改了 marketplace.json，push 时会和远端 bot 的自动 commit 冲突，且你的本地版本会被覆盖（详见顶部"工作流概览"）。

## 插件维护

- 旧插件不再维护时，把 `plugin.json` 的 `components` 全部设为 `false`，但**不要删除插件**。
- 破坏性变更必须升级 `version` 主版本号，并在 PR 描述里写迁移指南。
- 新增事件或字段时同步更新 `schemas/plugin.schema.json`、`tools/generate_marketplace.py` 和 `docs/`。

## 行为准则

请友好、专业、有建设性地讨论。所有参与者应遵守 [Contributor Covenant](https://www.contributor-covenant.org/)。
