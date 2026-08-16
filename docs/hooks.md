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
| `BuildSystemPrompt` | 构建 system prompt 时（会话首次构建 / 切换 agent 后） | `agent_name`, `is_subagent_call`, `current_role`, `agent_identity_content`, `enabled_skills_content`, `available_subagents_content`, `extra_context`（由 context_builder 传入 project_root/project_name） |

> `BuildSystemPrompt` 注入语义：hook 的返回字符串会拼接进 system prompt 尾部（agent.py 触发，
> 会话首次构建/切 agent 时）。建议返回**静态文本**（能力声明类），保证会话缓存稳定；不要动态拼接会话状态。
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

## 批量验证：validate_hooks.py

仓库提供 `tools/validate_hooks.py`，用 **DriFox 真实 HookManager** 加载并执行
所有插件的 hooks，验证插件 hooks 能否被 DriFox 实际使用（比静态校验更接近真实）：

```bash
# 校验所有带 hooks 的插件（需能定位 DriFox 仓库）
python tools/validate_hooks.py

# 指定 DriFox 仓库路径
python tools/validate_hooks.py --drifox D:/work/DriFox

# 只校验单个插件
python tools/validate_hooks.py plugins/ponytail
```

校验内容：

1. `hooks.json` 是合法 JSON，`hooks` 字典结构正确
2. 每个 hook 用 `HookManager.register_hooks_from_json()` 注册（相对导入 `.module:func`）
3. 对每个订阅事件触发最小上下文，确认 hook **真实执行成功**（success=True）

行为约定：

- 注册在临时目录副本上进行，**不会写回**源 `hooks.json`（避免 id 补写污染）
- 每个插件验证后注销，避免 HookManager 类级共享状态串扰
- 退出码：0=全部通过，1=存在失败，2=无法定位 DriFox / 缺依赖

> DriFox 仓库定位优先级：`--drifox` 参数 > 环境变量 `DRIFOX_ROOT` > 常见路径。

### 支持 command 类型（Claude Code 插件兼容）

`hooks.json` 的 `type=command` 也可用：执行任意 shell 命令（含 `node`），
stdin 传 JSON context，支持 `${CLAUDE_PLUGIN_ROOT}` 变量替换与
`CLAUDE_PLUGIN_ROOT`/`CLAUDE_PROJECT` 等环境变量注入（专为第三方 Claude
插件设计）。exit code 2 按 Claude Code 约定视为 BLOCK（阻断工具执行）。

> 社区插件（如 ecc/upstream hooks）的 22 个 node command hook 理论上可直接
> 接入。本仓库 `plugins/ecc/hooks/` 采用**精选 Python 重写**方案（5 个核心
> hook：git push 提醒 / 预提交质量检查 / 临时文档警告 / 编辑后质量门 /
> console.log 检查），不必依赖 node 运行时，见 `plugins/ecc/hooks/ecc_hook.py`。

## 最佳实践

- **幂等**：钩子可能被多次触发，所有副作用必须可重入
- **快速失败**：超过 timeout 会被强杀，关键路径代码须在主流程最前面
- **不阻塞主进程**：长任务写到后台（`subprocess.Popen` + detach）
- **写日志到 memory/**：避免污染用户项目
- **错误隔离**：单个钩子异常不能影响其它钩子或主流程

完整示例见 [`plugins/evolver/hooks/evolver_hook.py`](../plugins/evolver/hooks/evolver_hook.py)。
