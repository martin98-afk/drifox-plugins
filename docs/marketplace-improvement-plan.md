# 插件市场完善方案

> 日期：2026-06-26
> 状态：已批准，实施中

## 1. 背景与问题

当前 drifox-plugins 仓库作为 DriFox 官方插件市场，存在以下问题：

| # | 问题 | 严重度 |
|---|------|--------|
| 1 | CHANGELOG 声称有 CI 但 `.github/` 目录不存在 | P0 |
| 2 | marketplace.json 手动维护，与 plugin.json 容易脱节 | P0 |
| 3 | 实际可用插件仅 1 个（evolver），市场内容不足 | P1 |
| 4 | 没有 plugin CLI，安装靠手动 cp | P1 |
| 5 | marketplace.json 在 `.claude-plugin/` 下，命名不一致 | P2 |
| 6 | 插件缺少 drifox 兼容性声明，无安全审查指引 | P2 |

## 2. 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| marketplace.json 位置 | 仓库根目录 | 市场级清单不属于某个插件 |
| marketplace.json 维护 | 生成脚本 + validator 双重保障 | 自动生成消除双写，validator 拦截不一致 PR |
| CI 范围 | 全面（校验 + marketplace 一致性 + lint + 文档链接） | 保障质量 |
| 新插件类型 | 工作流类 + 语言/框架增强类 | 覆盖高频开发场景 |
| CLI 实现位置 | DriFox 运行时（D:/work/DriFox） | CLI 是运行时能力，本仓库只提供数据源 |

## 3. 阶段一：补齐基础设施

### 3.1 CI 工作流

文件：`.github/workflows/validate.yml`

- 触发：PR 到 main + push 到 main
- 步骤：
  1. `python tools/validate_plugins.py --strict` — manifest + 组件校验
  2. `python tools/generate_marketplace.py --check` — marketplace.json 一致性
  3. `ruff check tools/ plugins/*/hooks/` — Python lint
  4. 文档链接检查（docs/ 内的相对链接有效性）
- 环境：Python 3.10+，依赖 jsonschema + ruff

### 3.2 marketplace.json 自动生成

文件：`tools/generate_marketplace.py`

- 扫描 `plugins/*/.drifox-plugin/plugin.json`
- 汇总字段：name, description, version, author, license, components, keywords
- 生成 `source` 字段：`{type: "git-subdir", url, path: "plugins/<name>", ref: "main"}`
- 输出：仓库根目录 `marketplace.json`
- `--check` 模式：不写文件，比对当前 marketplace.json 是否一致，不一致返回非零退出码

### 3.3 validator 增强

文件：`tools/validate_plugins.py`

新增两个检查函数：
- `check_dependencies()` — 校验 `dependencies` 中引用的插件名是否存在于 plugins/
- `check_marketplace_consistency()` — 比对 marketplace.json 与各 plugin.json 的关键字段（name, version, description, components）

### 3.4 marketplace.json 迁移与文档修正

- 删除 `.claude-plugin/marketplace.json`
- 在根目录生成新的 `marketplace.json`
- 更新所有引用旧路径的文档（README.md, CHANGELOG.md, docs/）

### 3.5 兼容性声明

给 `evolver` 和 `example-plugin` 的 plugin.json 补充：
```json
"drifox": {
  "min_version": "0.5.0"
}
```

### 3.6 社区文件

- `.github/pull_request_template.md` — PR 模板（含插件信息 checklist）
- `.github/ISSUE_TEMPLATE/bug_report.md` — Bug 报告模板
- `.github/ISSUE_TEMPLATE/plugin_request.md` — 插件请求模板

## 4. 阶段二：丰富插件生态

### 工作流类

| 插件 | 组件 | 功能 |
|------|------|------|
| `git-workflow` | commands + hooks | 分支管理、提交规范检查、PR 模板生成 |
| `code-reviewer` | commands + agents + skills | 自动 PR 审查、代码质量评分 |
| `test-scaffold` | commands + skills | 测试骨架生成、覆盖率建议 |

### 语言/框架增强类

| 插件 | 组件 | 功能 |
|------|------|------|
| `python-pro` | skills + hooks | Python 最佳实践、lint 集成 |
| `frontend-pro` | skills + commands | 前端组件规范、a11y 辅助 |

每个插件遵循现有架构约定，通过 `validate_plugins.py` 校验。

## 5. 阶段三：建设分发能力

### 5.1 CLI（在 DriFox 运行时实现）

| 命令 | 功能 |
|------|------|
| `drifox plugin list` | 列出已安装插件 |
| `drifox plugin search <keyword>` | 搜索 marketplace.json |
| `drifox plugin install <name>` | 从 git-subdir 拉取安装 |
| `drifox plugin update [name]` | 更新已安装插件 |
| `drifox plugin remove <name>` | 卸载插件 |

### 5.2 安全审查指引

文件：`docs/plugin-security.md`
- hooks Python 代码安全 checklist
- 权限声明模型
- 插件沙箱限制说明

### 5.3 marketplace.json 格式优化

新增字段：
- `categories` — 插件分类（workflow/language/theme/agent/mcp/lsp）
- `drifox_compatibility` — 兼容性汇总
- `updated_at` — 最后更新时间戳

## 6. 验证标准

- [ ] `python tools/validate_plugins.py --strict` 全部通过
- [ ] `python tools/generate_marketplace.py --check` 通过
- [ ] CI 在 PR 上自动运行且通过
- [ ] 每个新插件通过 validator + 在本地 DriFox 中可加载
- [ ] 所有文档引用路径正确
