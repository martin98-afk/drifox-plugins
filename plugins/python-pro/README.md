# python-pro — Python 开发增强插件

为 DriFox 注入 Python 最佳实践，提供智能的代码质量保障能力。

## 功能

| 功能 | 说明 |
|------|------|
| 🧠 **最佳实践注入** | 技能自动加载 PEP 8 / 类型标注 / async 规范 |
| 🔍 **自动 lint 检查** | 钩子在 write/edit .py 文件后自动运行 ruff |
| 🏷️ **类型检查辅助** | 注入 mypy 最佳实践和类型标注规范 |
| ⚡ **异步开发支持** | async/await 模式与陷阱提示 |

## 安装

无需额外安装。插件位于 `~/.drifox/plugins/python-pro/`，DriFox 启动时自动发现。

### 前置依赖（可选）

为获得最佳体验，建议安装：

```bash
# ruff（推荐，已自动集成到钩子中）
pip install ruff

# mypy（类型检查辅助）
pip install mypy
```

## 工作原理

```
write/edit .py 文件
    │
    │  (Hook: PostToolUse)
    ▼
ruff check <file>        ← 自动执行
    │
    ├─► 无问题 → 静默通过
    └─► 有问题 → 记录到 memory/python-pro.log
```

## 技能注入场景

当你在会话中涉及以下话题时，技能自动注入：

- Python 代码编写与重构
- PEP 8 / 代码风格规范
- 类型标注（type hints）与 mypy
- 异步编程（async / await）
- ruff / flake8 / pylint lint 配置
- 虚拟环境与依赖管理（pip / poetry / uv）

## 组件覆盖

| 组件 | 状态 | 说明 |
|------|------|------|
| skills | ✅ | python-pro 技能（最佳实践知识库） |
| hooks | ✅ | PostToolUse 自动 lint 检查 |
| commands | — | 暂不提供（纯后台增强） |
| agents | — | 暂不提供 |
| themes | — | 暂不提供 |
| mcp | — | 暂不提供 |
| lsp | — | 暂不提供 |