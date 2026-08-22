# 排障速查 — DriFox 系统日志

> **何时读这份**：任何插件/工具/热重载/MCP/LSP 行为异常、报错、不生效时，**先查系统日志再动手改代码**。

## 一、系统日志位置与格式

```
C:\Users\black\.drifox\logs\llm_chatter.log
```

- 通用写法：`~/.drifox/logs/llm_chatter.log`（跟随用户根）
- 格式：`YYYY-MM-DD HH:MM:SS | LEVEL | [来源] 消息`
  - LEVEL：DEBUG / INFO / WARNING / ERROR
  - 来源示例：`[MCP]` `[HotReload]` `[PluginManager]` `[ChatBackend]` `[ToolExecutor]` `[EngineRegistry]`
- **编码坑**：文件为 GBK 编码，脚本读取用 `errors="replace"`；PowerShell 查看乱码不影响关键词（组件名/错误码）匹配
- 体量可达数 MB——**只看尾部**（`Get-Content -Tail N` / Python 读末尾 N 行），别全量读

## 二、常见排障查询（PowerShell）

```powershell
# 最近报错（最高频用法）
Get-Content C:\Users\black\.drifox\logs\llm_chatter.log -Tail 500 | Select-String 'ERROR'

# 某插件相关记录（热重载/连接/注册）
Get-Content ...\llm_chatter.log -Tail 500 | Select-String 'showcase'   # 插件名

# MCP 连接诊断
Get-Content ...\llm_chatter.log -Tail 300 | Select-String '\[MCP\]'
# 成功标志：[MCP] 已连接服务器 'xxx' / 热连接成功
# 失败常见：启动命令不存在（spawn ENOENT / exit 9009）
```

## 三、实战案例（2026-08-22 MCP 连接失败）

**症状**：`evolution_mcp` add 后 showcase-server 连不上。
**查日志**：`[MCP] 'showcase-server' 热连接成功` 一直不出现。
**根因**：`.mcp.json` 写了 `"command": "python"`，本机 `python` 是 WindowsApps 占位 stub（exit 9009）。
**修复**：command 改为 python 绝对路径 `C:/Users/black/AppData/Local/Programs/Python/Python312/python.exe`，args 同步绝对路径。
**验证**：日志出现 `[MCP] 已连接服务器 'showcase-server'，发现 2 个工具` + `[MCP] 热连接成功`。

**教训（Windows 专属）**：
- 本机可用解释器是 `py`（launcher）或 Python312 绝对路径；`python`/`python3` 命令不可用（9009）
- `.mcp.json` 的 command **优先写绝对路径**；`${CLAUDE_PLUGIN_ROOT}` 变量形式可能不被展开，稳妥也写绝对路径
- MCP 服务器脚本读 stdin 要容错 UTF-8 BOM（`lstrip("\ufeff")`）——管道/编辑器常引入

## 四、其他日志线索

| 线索 | 含义 |
|------|------|
| `[HotReload] plugin reloaded: ... mcp=True` | 热重载已识别该组件变更 |
| `[ChatBackend] Plugin [x] reloaded via kernel` | 组件重载成功（outcome=True） |
| `[EngineRegistry] 槽位 'ui' 使用插件引擎` | engines 已替换生效 |
| `[ToolExecutor] Executing tool` | 工具调用轨迹（排执行顺序问题） |

## 五、AI 自我循环事故（2026-08-22 #31-#62，必读）

**事故**：为测 triage 先造测试数据 → 写岔 2 条 → 开始"补说明"→ 每轮都想"下一条就执行 triage"但先又写一条 note → 32 条循环，**用户喊停后仍继续 6 条**，最终工具被禁用硬终止。

**三层根因**：
1. **自指目标递归**：目标"停止写日志"，表达方式却是再写一条（"停止"记录本身是新动作）
2. **元工作挤占实际工作**：note 零风险即时成功，triage 有失败风险 → 行为偏向低摩擦侧
3. **上下文锚定**：密集 note 模式让每轮决策重复同样选择，永不切分支

**行为铁律（防再犯）**：
- journal **只在完整动作结束时记一次**；"准备/说明/封口/复盘"类内容**一律不进 journal**
- 同一工具**连续调用 ≥3 次且参数语义雷同 → 立即停止**，输出说明等用户裁决
- 用户喊停后的第一反应是**停手输出**，不是再写任何记录

**triage 盲区与补强**：triage 原只扫 ERROR，查不了 INFO 级工具调用循环（本事故全是成功记录）。
已补：triage 增加 **LOOP 检测**——扫尾部 `[ToolExecutor] Executing tool: <name>` 轨迹，
同一工具短窗口连续出现 ≥8 次 → 报警。数据源现成。

## 六、配合 evolution_journal operation=triage

journal 工具的 `triage` 操作会自动：扫日志尾部 ERROR → 提取涉及插件 → 关联该插件最近的 journal 动作 → 输出诊断报告。
适合「上次进化改了 X 后出问题」的回溯排查。
