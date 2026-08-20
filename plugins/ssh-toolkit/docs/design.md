# ssh-toolkit 设计文档

> 状态：待用户评审（brainstorming 流程第 8 步）
> 日期：2026-08-19
> 作者：马丁

## 1. 目标与边界

**做什麼**：一个 DriFox 插件，注册一组 AI 可调用的 SSH 工具，让 AI 自动连接远程主机、执行命令、传输文件、做端口转发、浏览目录。

**不做什麼**：
- 不做专属 UI 面板（纯 AI 工具包，无浮动卡片 / 无斜杠命令）
- 不管理本地 `~/.ssh/config`（独立管理自己的连接配置）
- 不做交互式 shell 接管（AI 每次调用无状态，靠连接池复用）

## 2. 已确认的核心决策

| 维度 | 决策 |
|------|------|
| 形态 | 纯 AI 工具包（`components.tools: true`），无 UI、无 commands |
| 连接配置存储 | `~/.drifox/cache/ssh/connections.json` |
| 功能范围 | 连接管理 + 命令执行 + 文件传输 + 长连接池 + 端口转发 + 目录浏览 |
| 认证方式 | 混合：按每个连接的 `auth_type` 选择（publickey / password / keyboard-interactive / agent） |
| 实现库 | `paramiko`（纯 Python，跨平台） |
| 凭据落盘 | 明文写入 `connections.json`，文件权限 600，文档标注风险 |
| 开发目录 | `D:\work\drifox-plugins2\plugins\ssh-toolkit\`（市场仓库即工作目录） |

## 3. 插件结构

```
ssh-toolkit/
├── .drifox-plugin/
│   └── plugin.json              # 插件 manifest（仅 tools:true）
├── tools/
│   ├── __init__.py              # 可选，空
│   ├── store.py                 # 连接配置读写（connections.json，chmod 600）
│   ├── pool.py                  # 进程内连接池（dict by handle）
│   ├── auth.py                  # 按 auth_type 建立 paramiko 连接
│   ├── conn_mgmt.py             # ssh_add/list/remove_connection（register）
│   ├── exec_tool.py             # ssh_connect / ssh_exec / ssh_disconnect（register）
│   ├── transfer.py              # ssh_upload / ssh_download / ssh_list_dir（register）
│   ├── forward.py               # ssh_forward（register）
│   ├── icons/
│   │   └── ssh.svg              # 深色图标
│   └── icons_light/
│       └── ssh.svg              # 浅色图标
├── docs/
│   └── design.md                # 本文档
└── README.md
```

## 4. manifest（plugin.json）

```json
{
  "name": "ssh-toolkit",
  "description": "SSH 远程工具包：连接管理、命令执行、文件传输(SFTP)、端口转发、目录浏览，基于 paramiko 实现，AI 自动调用。",
  "version": "0.1.0",
  "author": "马丁",
  "components": { "tools": true },
  "min_drifox_version": "0.0.0"
}
```

> 实现时对齐 `schemas/plugin.schema.json`，缺失字段（如 `license` / `homepage`）按 example-plugin 补齐。

## 5. 连接存储格式

路径：`~/.drifox/cache/ssh/connections.json`

```json
{
  "version": 1,
  "connections": [
    {
      "name": "web-prod",
      "host": "192.168.1.10",
      "port": 22,
      "user": "deploy",
      "auth_type": "publickey",
      "key_path": "~/.ssh/id_rsa",
      "password": "",
      "key_passphrase": "",
      "timeout": 10,
      "note": "生产 Web 机"
    }
  ]
}
```

- 写入后 `os.chmod(path, 0o600)`。
- `password` / `key_passphrase` 明文存储（已确认），README 警告风险。
- `auth_type` 枚举：`publickey` / `password` / `keyboard-interactive` / `agent`。

## 6. 连接池

`tools/pool.py`：模块级 `_POOL: Dict[str, paramiko.SSHClient]`。

- `ssh_connect` 成功后将 client 以 `handle = f"{name}:{uuid4().hex[:8]}"` 存入池。
- 后续 `ssh_exec` / `ssh_upload` 等用 `handle`（或 `name`，自动取该 name 首个活跃连接）定位 client。
- `ssh_disconnect` 关闭 client 并从池移除。
- 进程退出时由 atexit 兜底关闭全部。

### 6.1 懒连接（Lazy Connect）

`pool.ensure_client(ref)` 统一解析客户端：

- 若 `ref` 命中**活跃连接**（handle 或 name），直接返回复用。
- 若未命中活跃连接，但 `ref` 是**已保存连接名**（`store.get_connection` 命中），则自动按配置 `auth.connect` 建连并入池后返回——**无需先调用 `ssh_connect`**。
- 若两者皆未命中，返回 `(None, "未找到活跃连接：{ref}（先 ssh_connect）")`。

> `ssh_list_dir` / `ssh_exec` / `ssh_upload` / `ssh_download` / `ssh_forward` 均经 `ensure_client` 解析；`ssh_connect` 仍是显式建连入口（返回 handle 供复用）。错误信息走 `ToolResult.error`（非 `content`），否则 UI 显示 `[Error] None`。

## 7. 认证处理（auth.py）

`connect(conn) -> paramiko.SSHClient`，按 `auth_type` 分支：

- `publickey`：`SSHClient.connect(host, port, username, key_filename=expand(key_path), passphrase=key_passphrase or None)`
- `password`：`...connect(..., password=password)`
- `agent`：`...connect(..., allow_agent=True, look_for_keys=False)`（或显式 `AgentAuthenticator`）
- `keyboard-interactive`：`...connect(..., auth_interactive_callback=handler)`，handler 按提示返回密码/口令列表

统一：`set_missing_host_key_policy(AutoAddPolicy())`（首次连接免手动确认）；`timeout=conn.timeout`。

## 8. 工具清单（10 个）

统一：`group="SSH 远程"`；`icon="ssh"`；`source` 由 loader 注入。

| # | 工具名 | 参数 | 返回 | danger |
|---|--------|------|------|--------|
| 1 | `ssh_add_connection` | name, host, port=22, user, auth_type, key_path?, password?, key_passphrase?, timeout=10, note? | 保存成功提示 | safe |
| 2 | `ssh_list_connections` | （无） | 连接列表（密码掩码 `****`） | safe |
| 3 | `ssh_remove_connection` | name | 删除提示 | safe |
| 4 | `ssh_connect` | name（或运行时 host/user/auth_* 覆盖） | handle 字符串 | dangerous |
| 5 | `ssh_exec` | handle/name, command, timeout?, cwd?, env? | stdout+stderr+exit_code | dangerous |
| 6 | `ssh_upload` | handle/name, local_path, remote_path | 传输结果 | dangerous |
| 7 | `ssh_download` | handle/name, remote_path, local_path | 传输结果 | dangerous |
| 8 | `ssh_list_dir` | handle/name, remote_path, recursive? | 文件列表(权限/大小/mtime) | safe |
| 9 | `ssh_forward` | handle/name, type(local/remote), bind_addr, bind_port, remote_addr, remote_port | forward id | dangerous |
| 10 | `ssh_disconnect` | handle/name（或 forward_id） | 关闭提示 | safe |

### impl 行为要点

> 解析客户端统一经 `pool.ensure_client(ref)`（见 §6.1）：未建连时按已保存配置自动建连，无需先 `ssh_connect`。

- **ssh_exec**：`client.exec_command(command, timeout=timeout)` → 读 stdout/stderr → `recv_exit_status()`。返回 `ToolResult(True, content=f"$ {command}\n{out}{err}\nexit={code}")`。
- **ssh_upload/download**：`client.open_sftp().put/get`。路径做归一化与越界检查（remote_path 不以 `/` 开头时相对 home）。
- **ssh_list_dir**：`sftp.listdir_attr(remote_path)` + `sftp.stat`，输出表格式列表。
- **ssh_forward**：`Transport.open_channel`（`direct-tcpip` 本地转发 / `forwarded-tcpip` 远程转发），在后台线程双向拷贝字节流；forward id 记录到 `_FORWARDS` 供 `ssh_disconnect` 关闭。
- **ssh_connect**：先查池，同名已活跃则复用并返回原 handle；否则建立新连接入池。

## 9. 依赖与导入

- 运行时 `try: import paramiko except ImportError`，缺失时工具返回清晰错误：`"缺少依赖 paramiko，请运行：pip install paramiko"`。
- 不修改主程序；纯标准库 + paramiko 自包含实现。

## 10. 安全说明

- `connections.json` 明文存密码/私钥口令，文件权限 600；同机有读权限的进程/用户可见。
- README 明确建议：生产环境优先 `publickey` + `ssh-agent`，避免存储密码。
- 所有执行/传输/转发工具 `danger="dangerous"`，经权限卡片授权后 AI 方可调用。

## 11. 验证计划

1. `python -m py_compile tools/*.py` 全通过。
2. `cp -r ssh-toolkit /tmp/dfp/plugins/ && cd /tmp/dfp && python tools/validate_plugins.py` 全 OK。
3. `python tools/generate_marketplace.py` 正常更新。
4. 手动冒烟（本地或测试机）：
   - `ssh_add_connection` → `ssh_list_connections` 确认掩码
   - `ssh_connect` → `ssh_exec("uname -a")` 返回正确
   - `ssh_upload` / `ssh_download` 往返一致
   - `ssh_list_dir("/tmp")` 返回列表
   - `ssh_forward` 建隧道 + `ssh_disconnect` 关闭
5. `ssh_disconnect` 后池清理、进程退出 atexit 兜底关闭。

## 12. 发布

验证通过后，按 plugin-creator §7 从 `drifox-plugins2` 仓库提 PR 到 `martin98-afk/drifox-plugins` main。
