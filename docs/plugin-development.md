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

> **Tip**：建议三个组件都实现。`hooks` 采集数据 → `commands` 让用户操作 → `skills` 让 AI 知道怎么用。

## 3. 实现 components

详见各自文档：

- [commands.md](commands.md)
- [hooks.md](hooks.md)
- [skills.md](skills.md)

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
4. 提交 commit（`feat(your-plugin): 初始实现`）
5. 创建 PR，描述插件功能与使用方式

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

## 进阶：发布到 EvoMap Hub（可选）

DriFox 插件生态未来会支持远程市场。当前阶段建议先在本地仓库迭代，待 `drifox-plugin` CLI 上线后接入远程注册。
