# 插件开发指南

本文介绍从零开发一个 DriFox 插件的完整流程。

## 1. 起步：复制 example-plugin

最快的方式是复制 `plugins/example-plugin/`：

```bash
cp -r plugins/example-plugin plugins/your-plugin
```

然后修改：

- `plugins/your-plugin/.drifox-plugin/plugin.json` — 改 `name`、`description`、`version`、`author`
- `plugins/your-plugin/README.md` — 重写说明
- `plugins/your-plugin/__init__.py` — 通常无需改动

## 2. 决定实现哪些组件

打开 `plugin.json`，把 `components` 里要实现的设为 `true`：

| 组件 | 何时启用 |
|------|---------|
| `commands` | 插件要暴露 `/xx` 斜杠命令给用户 |
| `hooks` | 插件要在特定 DriFox 事件上自动做事 |
| `skills` | 插件要让 AI 在相关任务中拿到领域知识 |
| `ui` | 插件要往 DriFox 主窗口注入浮动卡片 / 自定义渲染器 / 消息元素工厂 |
| `themes` | 插件要贡献一套配色方案 |
| `agents` | 插件要提供 `@xx` 智能体 |
| `mcp` / `lsp` | 插件要注册外部工具服务器 / 语言服务器 |

> **Tip**：常见组合是 `commands + hooks + skills + ui`。`hooks` 采集数据 → `ui` 把数据变成可视面板 → `commands` 让用户操作 → `skills` 让 AI 知道怎么用。

## 3. 实现 components

详见各自文档：

- [commands.md](commands.md)
- [hooks.md](hooks.md)
- [skills.md](skills.md)
- [agents.md](agents.md)
- [themes.md](themes.md)
- [mcp.md](mcp.md)
- [lsp.md](lsp.md)
- ui 组件：见 [architecture.md](architecture.md#ui-组件) 与 [`plugins/git-panel/`](../plugins/git-panel/) 示例

## 4. 本地测试

```bash
# 1. 校验 manifest
python tools/validate_plugins.py

# 2. 复制到 DriFox 插件目录
cp -r plugins/your-plugin ~/.drifox/plugins/  # Linux/macOS
xcopy plugins\your-plugin %USERPROFILE%\.drifox\plugins\your-plugin /E /I /Y  # Windows

# 3. 启动 DriFox，观察加载日志
```

## 5. 调试

### 钩子单独调试

钩子 Python 文件支持 `--event` 参数独立运行：

```bash
python plugins/your-plugin/hooks/your-plugin_hook.py --event=SessionStart < test_input.json
```

`test_input.json` 是模拟的 HookManager 上下文：

```json
{
  "project_root": "D:/work/test",
  "message": "hello"
}
```

### 启用调试日志

在钩子 Python 文件顶部：

```python
import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
```

DriFox 启动时会自动捕获 `logging` 输出到 `~/.drifox/logs/`。

## 6. 提 PR

1. 在 GitHub 上 fork 本仓库
2. 创建分支 `feat/your-plugin`
3. 跑 `python tools/validate_plugins.py`，确保全 OK
4. 提交 commit（`feat(your-plugin): 初始实现`）— **只提交插件本身的文件，不要包含 marketplace.json 改动**
5. push 分支并创建 PR，描述插件功能与使用方式

> ⚠️ **marketplace.json 不要本地改、不要本地 commit。**
> 该文件由 `.github/workflows/validate.yml` 的 `auto-fix-marketplace` job 在 CI 中从 `plugins/*/.drifox-plugin/plugin.json` 自动生成并 commit 到 head。如果你本地也跑并改了 marketplace.json，push 时会和远端 bot 的自动 commit 冲突，且你的本地版本会被覆盖。详见 [CONTRIBUTING.md](../CONTRIBUTING.md#工作流概览)。

PR 模板：

```markdown
## 插件名
your-plugin

## 功能简述
一句话说明插件做什么

## 命令
- `/your-plugin` — 描述

## 钩子事件
- `PostToolUse` — 描述

## 技能
- `your-plugin` — 描述

## 测试
[ ] 通过 `python tools/validate_plugins.py`
[ ] 在本地 DriFox 中验证加载
[ ] 至少 1 个核心场景通过手动测试
```

## 进阶：发布到插件市场

插件合并到本仓库 `plugins/` 目录后，**CI 自动同步** marketplace.json（详见顶部"提 PR"说明）。

`marketplace.json` 是 DriFox 运行时 `drifox plugin install` 命令的数据源。每次 PR 推送或 merge 后，bot 都会跑 `tools/generate_marketplace.py` 并把更新 commit 到 head/main（commit message 含 `[skip ci]` 防止无限循环）。

未来 DriFox 运行时将提供完整的 `drifox plugin` CLI（install / search / list / update / remove），届时用户可直接通过命令行安装本仓库中的插件。
