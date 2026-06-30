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
5. 提交 commit（遵循 Conventional Commits）
   ↓
6. 创建 Pull Request
   ↓
7. CI 校验：失败时 marketplace.json 由 drifox-bot 自动 commit 修复
   ↓
8. Maintainer 评审 & merge
```

> **marketplace.json 自动同步**：当你修改 `plugin.json` 后忘记跑 `generate_marketplace.py` 时，CI 会自动跑生成并把修复 commit：
> - PR 场景 → commit 到 PR head 分支
> - push main 场景 → commit 到 main（保证 main 始终 green）
>
> bot commit 含 `[skip ci]`，GitHub Actions 原生跳过整个 workflow，不会无限循环。详见 `.github/workflows/validate.yml` 的 `auto-fix-marketplace` job。

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
| 启用的组件必须有对应目录与文件 | `components.commands=true` ⇒ 至少 1 个 `commands/*.md`；`components.ui=true` ⇒ `ui/__init__.py` + widget 模块 |
| 钩子 Python 文件必须能 `python -m py_compile` 通过 | 语法层面不能有错 |
| 每个 `commands/*.md` 顶部必须有 frontmatter | 至少包含 `description` 和 `type` |
| 每个 `skills/<name>/SKILL.md` 顶部必须有 frontmatter | 至少包含 `name` 和 `description` |
| ui 插件的 `ui/__init__.py` 必须定义 `register_ui(registry)` 顶层函数 | 由 DriFox 启动时 `UIPluginRegistry.load_plugin` 调用 |

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

# 2. 确保 marketplace.json 已更新
python tools/generate_marketplace.py
```

输出应全部为 `OK`。如果失败，PR 不会被合入。

## 插件维护

- 旧插件不再维护时，把 `plugin.json` 的 `components` 全部设为 `false`，但**不要删除插件**。
- 破坏性变更必须升级 `version` 主版本号，并在 PR 描述里写迁移指南。
- 新增事件或字段时同步更新 `schemas/plugin.schema.json`、`tools/generate_marketplace.py` 和 `docs/`。

## 行为准则

请友好、专业、有建设性地讨论。所有参与者应遵守 [Contributor Covenant](https://www.contributor-covenant.org/)。
