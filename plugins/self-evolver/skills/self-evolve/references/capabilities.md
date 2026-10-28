# 宿主能力清单（capabilities）

> **何时读这份**：给插件声明 `capabilities` 时；或代码里要用宿主受保护 API（通知、模型配置、对话引擎、数据目录等）时。
>
> **来源**：主程序 `app/plugins/capabilities/catalog.py` 的 `CATALOG`，共 **61 个**能力。catalog.py 自述「能力池的唯一真相，新增能力必须在此登记」，所以这是权威全集，不是抽样。

## 三条纪律

1. **不要发明能力名**。未登记的能力只有在注册时传 `experimental=True` 才可能生效，且每次建池都会记 warning。名字写错的后果是拿不到对象、插件运行期静默降级。
2. **看 surface**。`ui` = 浮动卡/工作台页，`tool` = 工具插件。`ui` 专用能力在 hook 或工具里拿不到，必须显式传 `surface="ui"`。
3. **能力是功能池，不是纯权限**。`caps_for(...)` 拿不到时返回 `None`，代码必须有降级分支。范本见 `plugins/token-usage/ui/data.py:186` 的三级兜底。

级别的含义（`CapabilityLevel`）：**高** = 触及明文密钥、会话破坏性操作、数据外发、任意工具执行这类高敏能力，声明它需要更严格的审核；低 = 只读元数据；中 = 有副作用但可控；— = 无级别。

## 建插件时先看这张表

**只声明真正用到的**。空数组 = 不申请任何能力。整表复制会让插件在审核时被当成高敏。

### model（4）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `model.config` | **高** | ui+tool | 完整模型配置（含已解密明文 API key） | `get_model_config` / `get_provider_config` |
| `model.enumerate` | 低 | ui+tool | 指定服务商的可选模型列表（含视觉/思考能力标记） |  |
| `model.metadata` | 低 | ui+tool | 当前模型的 provider/名称/上下文长度/能力元数据 |  |
| `model.schema` | 低 | ui+tool | 指定 agent 视角的工具 schema | `get_tools_schema` |

### provider（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `provider.list` | 低 | ui+tool | 已配置服务商清单（id/名称/模型数，不含密钥与 URL） |  |

### session（8）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `session.interrupt` | 中 | ui+tool | 停止当前流式输出（入队，本轮结束后执行） |  |
| `session.invalidate` | 中 | ui | 失效所有窗口的会话 system_prompt 缓存（跨窗口副作用） |  |
| `session.list` | 中 | ui | 历史会话列表与元数据 |  |
| `session.manage` | **高** | ui | 新建/切换/删除会话（破坏性） |  |
| `session.new` | 中 | ui+tool | 新建会话（入队，停流后执行） |  |
| `session.read` | 中 | ui+tool | 当前 session_id 与消息列表 |  |
| `session.send` | 中 | ui+tool | 发消息驱动一轮对话（入队；ephemeral 不写会话不渲染） |  |
| `session.write` | 中 | ui+tool | 消息写回当前会话（入库 + 刷 UI + 发事件） | `save_messages_to_session` |

### input（2）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `input.read` | 中 | ui | 输入框文本与附件列表 |  |
| `input.write` | 中 | ui | 写入输入框文本 |  |

### agent（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `agent.read` | 低 | ui+tool | agent 列表/提示词/管理器 | `get_agent_manager` / `get_agent_prompt` |

### subagent（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `subagent.run` | **高** | tool | 派生子智能体 | `subagent` |

### workdir（2）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `workdir.read` | 低 | ui+tool | 当前工作目录 | `get_workdir` |
| `workdir.write` | 中 | ui | 切换工作目录（缓存 + executor + 团队广播 + 事件） | `set_workdir` / `sync_working_directory` |

### theme（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `theme.read` | 低 | ui | 主题 id/名称/配色/字体/字号 |  |

### context（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `context.compact` | 中 | ui+tool | 上下文压缩器 | `get_compactor` |

### tool（3）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `tool.execute` | **高** | ui+tool | 执行任意工具 | `get_tool_executor` |
| `tool.inject` | **高** | ui | 向 LLM 注入工具（改变模型可见行为） |  |
| `tool.read` | 低 | ui+tool | 工具注册表元数据查询 |  |

### engine（2）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `engine.session` | **高** | ui | 创建对话引擎会话（消耗 token） | `create_engine_session` |
| `engine.stack` | **高** | ui | 对话执行栈工厂 | `conversation_stack` |

### platform（2）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `platform.read` | 中 | ui | 平台与会话列表 | `list_platform_sessions` / `list_platforms` |
| `platform.send` | **高** | ui | 向通讯平台发送消息（数据外发） | `send_to_platform` |

### mcp（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `mcp.call` | **高** | tool | MCP 工具调用 | `mcp` |

### lsp（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `lsp.query` | 中 | tool | LSP 查询 | `lsp` |

### net（3）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `net.avatar` | 低 | ui | Gitee 账户头像（fetch 确保已缓存并返回路径，须后台线程；cached_path 纯本地查，主线程安全） |  |
| `net.download` | 中 | ui+tool | 从 Gitee 绑定仓库下载文件到本地路径 |  |
| `net.upload` | **高** | tool | Gitee 上传（数据外发） | `gitee` |

### ui（7）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `ui.artifacts.show` | 中 | ui+tool | 向消息卡片成果栏推送成果条目（图片/视频/HTML/文本/文件，跨窗口副作用） |  |
| `ui.card.hide` | 低 | ui | 隐藏浮动卡 | `hide_card` |
| `ui.card.show` | 低 | ui | 显示浮动卡 |  |
| `ui.dialog` | 低 | ui | 文件/目录选择、确认框、单行输入（跟随主题） |  |
| `ui.events` | 低 | ui | 订阅/发布 UI 事件总线（主题切换/欢迎页刷新等） |  |
| `ui.exclusive` | 中 | ui | 独占 UI 模式 | `enter_exclusive_ui_mode` / `exit_exclusive_ui_mode` |
| `ui.notify` | 低 | ui | 弹 InfoBar 通知 | `notify` |

### stream（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `stream.subscribe` | 中 | ui | 订阅对话流事件（工具/流/错误/上下文/会话切换） |  |

### window（6）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `window.active` | 低 | ui | 当前活跃聊天窗口 |  |
| `window.current` | 低 | ui | 当前窗口的语义快照（backend/session/project/workdir） |  |
| `window.events` | 中 | ui | 订阅 tab 切换等窗口级事件 |  |
| `window.host` | 低 | ui | 宿主顶层窗口（弹窗/InfoBar 的合适 parent） |  |
| `window.list` | 低 | ui | 存活窗口 id 集合 |  |
| `window.workbench` | 中 | ui | 打开/刷新右侧工作台页 |  |

### plugin（3）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `plugin.control` | **高** | ui | 重载/启停其他插件 |  |
| `plugin.log` | — | ui+tool | 带 plugin=<name> 前缀的 logger |  |
| `plugin.read` | 低 | ui | 已安装插件列表/元数据 |  |

### command（2）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `command.read` | 低 | ui | 命令列表 |  |
| `command.reload` | 中 | ui | 命令热重载 |  |

### sync（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `sync.register` | **高** | ui | 注册本地目录进入云同步监控（目录内容将打包备份到云端，数据外发） |  |

### team（2）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `team.read` | 低 | ui+tool | 团队成员/角色/运行状态 |  |
| `team.send` | 中 | tool | 向团队成员派发任务邮件（写对方邮箱） |  |

### storage（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `storage.data_dir` | 低 | ui+tool | 插件持久化数据根目录（插件自拼 plugin_data/<name>/） |  |

### state（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `state.kv` | — | ui+tool | 窗口级 KV 存储（无系统权限） | `window_state` |

### cache（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `cache.purge` | 低 | ui | 清理主程序进程内 LRU 缓存（内存释放） |  |

### process（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `process.start` | **高** | ui+tool | 启动后台进程（argv 数组、无 shell；独立于宿主生命周期） |  |

### config（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `config.read` | 中 | ui | 按 key 读主程序配置项（非敏感标量；不含密钥，密钥走 model.config） | `get_setting` |

### host（1）

| 能力 | 级别 | 作用域 | 说明 | 别名 |
|---|---|---|---|---|
| `host.raw` | **高** | ui | 裸 main_widget / backend 对象引用 |  |

## 怎么取用

两种调用形态（`app.plugins.capabilities.resolve.caps_for`）：

```python
# A. 显式指定插件与 surface（ui/ 组件里常用）
from app.plugins.capabilities.resolve import caps_for
notify = caps_for("ui.notify", plugin=PLUGIN_NAME, surface="ui")

# B. 按调用方路径推断（后台线程也能用）
base = Path(caps_for("storage.data_dir"))
```

拿不到时返回 `None`，**必须**有降级分支。

## 声明位置

写进 `.drifox-plugin/plugin.json` 的 `capabilities` 数组，且 `api_version` 必须是 2 才参与裁剪：

```json
{
  "api_version": 2,
  "capabilities": ["ui.notify", "workdir.read"]
}
```

声明了 `api_version: 2` 却没写 `capabilities`，等于空清单。

## 怎么重新生成这份清单（宿主升级后）

catalog.py 在主程序源码里，打包版取不到。宿主新增能力后，在 DriFox 源码仓库根跑：

```bash
python3 - <<'PY'
import ast, collections
src = open('app/plugins/capabilities/catalog.py', encoding='utf-8').read()
LV = {'_L':'low','_M':'medium','_H':'high','_N':'none'}
SV = {'_UI':'ui','_TOOL':'tool','_BOTH':'ui+tool'}
rows = []
for n in ast.walk(ast.parse(src)):
    if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == '_spec':
        a = n.args
        legacy = [e.value for e in a[4].elts] if len(a) > 4 and isinstance(a[4], (ast.List, ast.Tuple)) else []
        rows.append((a[0].value, LV.get(getattr(a[1],'id',''),'?'),
                     SV.get(getattr(a[3],'id',''),'?'), a[2].value, legacy))
print(len(rows), '个能力')
for r in sorted(rows):
    print('|', r[0], '|', r[1], '|', r[2], '|', r[3], '|', ' / '.join(r[4]), '|')
PY
```
