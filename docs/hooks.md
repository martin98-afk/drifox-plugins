# hooks 组件

hooks 让插件在 DriFox 生命周期的特定事件上自动执行代码。常用于：日志采集、上下文增强、危险操作拦截、自动化工作流触发。

## 文件结构

```
<plugin-name>/
└── hooks/
    ├── hooks.json            # 事件 → 处理器映射
    └── <plugin-name>_hook.py # 处理器实现
```

> 文件名约定：`<plugin-name>_hook.py`。`hooks.json` 固定。

## hooks.json 结构

```json
{
  "description": "插件的一句话描述",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "python",
            "function": ".<plugin>_hook:hook_session_start",
            "timeout": 15,
            "enabled": true,
            "id": "<uuid>"
          }
        ]
      }
    ],
    "PostToolUse": [...],
    "PostAssistantMessage": [...]
  }
}
```

### 字段说明

- **`hooks.<EventName>[]`**：订阅的事件，每个事件可挂多个处理器链
- **`type`**：`python`（唯一支持的语言）
- **`function`**：`<module_name>:<func_name>` 形式
  - module_name 相对于 hooks/ 目录的模块名（**带前导点**）
  - 例如 `evolver_hook.py` 中的 `hook_session_start` ⇒ `".evolver_hook:hook_session_start"`
- **`timeout`**：超时秒数，默认 15，AI 回复类事件建议 ≥ 30
- **`enabled`**：布尔，默认 true
- **`id`**：UUID，每个处理器唯一

## 支持的事件

| 事件 | 触发时机 | 上下文字段 |
|------|---------|-----------|
| `SessionStart` | 会话创建 | `project_root`, `plugin_dir` |
| `SessionEnd` | 会话结束 | `project_root`, `summary` |
| `PreToolUse` | 工具执行前 | `project_root`, `tool_name`, `file`, `message` |
| `PostToolUse` | 工具执行后 | `project_root`, `tool_name`, `file`, `message`, `result` |
| `UserMessageSubmit` | 用户提交消息 | `project_root`, `message` |
| `PostAssistantMessage` | AI 回复后 | `project_root`, `message`, `response`, `error` |

> 详细事件规范将在 DriFox 0.5+ 文档中固化。

## 处理器签名

### Python 入口

DriFox 通过 subprocess 调用钩子，**标准模式**：

```python
def hook_session_start(event: str, context: dict) -> str | dict | None:
    """处理 SessionStart 事件"""
    # context 是 HookManager 注入的 dict
    ...
    return "ok"  # 返回值会作为 stdout 记录
```

### 通过 hooks.json 的 `type=python` 派发

`hooks.json` 中的 `function: ".<mod>:<func>"` 会被 HookManager 解析为：

```python
# HookManager 内部（伪代码）
import importlib
mod = importlib.import_module("evolver_hook")  # 相对于 hooks/
func = getattr(mod, "hook_session_start")
result = func(event_name, context)
```

## 独立调试

钩子 Python 文件支持 CLI 模式独立运行：

```bash
python plugins/your-plugin/hooks/your-plugin_hook.py --event=SessionStart < ctx.json
```

`ctx.json` 是模拟上下文：

```json
{
  "project_root": "D:/work/test",
  "message": "hello world"
}
```

实现要点：

```python
import argparse, json, sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    args = parser.parse_args()
    ctx = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    handler = HANDLER_MAP.get(args.event)
    if handler:
        handler(ctx)

if __name__ == "__main__":
    main()
```

## 最佳实践

- **幂等**：钩子可能被多次触发，所有副作用必须可重入
- **快速失败**：超过 timeout 会被强杀，关键路径代码须在主流程最前面
- **不阻塞主进程**：长任务写到后台（`subprocess.Popen` + detach）
- **写日志到 memory/**：避免污染用户项目
- **错误隔离**：单个钩子异常不能影响其它钩子或主流程

完整示例见 [`plugins/evolver/hooks/evolver_hook.py`](../plugins/evolver/hooks/evolver_hook.py)。
