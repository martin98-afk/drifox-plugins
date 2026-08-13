# Runtime 适配与信任

三层数据与 Python 核心是共享的；平台目录只保存薄适配配置。安装器必须合并配置，不覆盖用户已有 Hooks。

## 安装模式

| 参数 | 行为 |
|---|---|
| `auto` | 默认。检测 Claude Code / Codex；同时存在则安装两端，只有一个则安装对应端，都不存在则转 `manual` |
| `claude` | 初始化核心并合并 Claude Code 项目 Hooks |
| `codex` | 初始化核心并合并 Codex 项目 Hooks |
| `both` | 初始化核心并合并两端项目 Hooks |
| `manual` | 只初始化 `.memory-3layer/` 并打印手动接线说明 |

Windows：

```powershell
$ProjectDir = (Resolve-Path "..\你的目标项目").Path
.\install.ps1 -ProjectDir $ProjectDir -Platform auto
```

macOS / Linux：

```bash
./install.sh --project-dir /你的/目标项目 --platform auto
```

目标项目参数必填。安装器先把它归一到所在 Git 根；若不属于 Git 仓库，则使用给定目录本身。禁止把公开包所在的 Kim Service 克隆目录当作隐式目标。

## Claude Code

- 配置位置：项目根 `.claude/settings.json`。
- 生命周期：`SessionStart` 加载、`PostToolUse` 只跟踪项目内工作文件、`PreCompact` 保存最小恢复状态。
- 普通工具结果中的 `summary`、`fact` 或大段输出不会自动持久化；记录用户确认事实时调用 `scripts/record_memory.py`。
- 安装器只合并本包条目；已存在的无关 Hooks 必须保留。
- 配置完成后启动新会话，观察 loader 输出并检查 `.memory-3layer/`；没有真实事件证据时只报告 `adapter_status=configured`。

## Codex

- 配置位置：项目根 `.codex/hooks.json`。
- 适配器把 Codex 事件转换为同一核心输入，不维护第二套数据目录。
- 项目 Hook 是可执行代码。安装后在 Codex 中运行 `/hooks`，逐项审查命令与路径，再选择信任。
- 未信任、被禁用或宿主未加载时，Hook 不会自动执行；此时只能使用 manual 核心。
- 信任后启动新会话，观察 loader 输出并检查 `.memory-3layer/`，再报告 `runtime_status=observed`。

## 其他平台

Agent Skills 兼容只保证能读取 `SKILL.md`，不保证兼容 Claude Code 或 Codex 的 Hook 配置。默认使用：

1. 会话开始时显式运行 loader 或让 Agent 读取三层文件。
2. 用户确认“记住”时调用 `scripts/record_memory.py`；只有该受管记录器的顶层 `memory_fact` 可写，不接受任意工具原始输出。
3. 会话结束前显式保存最小状态。
4. 定期运行 `memory-review`。

平台没有真实适配器时，不复制 `.claude/settings.json` 或 `.codex/hooks.json` 来冒充支持。

## 安全检查

- Hook 命令必须使用包内相对路径或安装器解析出的安全路径。
- 配置合并前备份目标文件；JSON 无法解析时停止，不重建空文件。
- 不把本机用户名、绝对路径、环境变量值写入公开包。
- 任何平台都不得把完整事件负载直接持久化。
