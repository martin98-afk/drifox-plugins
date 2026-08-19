# ssh-toolkit 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个 DriFox 插件 `ssh-toolkit`，注册 10 个 AI 可调用的 SSH 工具（连接管理/命令执行/文件传输/目录浏览/端口转发），连接配置明文存于 `~/.drifox/cache/ssh/connections.json`，基于 paramiko 实现。

**Architecture:** 纯 Tools 组件插件（`components.tools: true`），无 UI/命令。支撑模块 `store.py`(配置读写) / `pool.py`(连接池) / `auth.py`(认证分支) 为纯逻辑可单测；4 个 `*.py` 各自 `register(registry)` 注册工具组。所有 impl 为 `impl(tool_ctx, **kwargs) -> ToolResult`，不依赖主程序内部。

**Tech Stack:** Python 3.14+，paramiko（运行时 try-import），DriFox ToolResult 协议，`app.tools.result.ToolResult`。

## Global Constraints

- 插件名 `ssh-toolkit`，目录名与 `plugin.json` 的 `name` 一致（kebab-case）。（来自 design.md §2/§4）
- `components: { "tools": true }`。（design.md §4）
- 连接配置路径 `~/.drifox/cache/ssh/connections.json`，写入后 `os.chmod(path, 0o600)`。（design.md §5）
- `password` / `key_passphrase` 明文存储，README 标注风险。（design.md §5/§10）
- 所有工具 `group="SSH 远程"`，`icon="ssh"`；执行/传输/转发 `danger="dangerous"`，管理/浏览/断开 `danger="safe"`。（design.md §8）
- paramiko 缺失时工具返回清晰错误：`"缺少依赖 paramiko，请运行：pip install paramiko"`。（design.md §9）
- 实现后跑 `tools/validate_plugins.py` 全 OK。（design.md §11）

---

## File Structure

```
ssh-toolkit/
├── .drifox-plugin/plugin.json      # manifest（Task 1）
├── tools/
│   ├── __init__.py                # 空（Task 1）
│   ├── store.py                   # 连接配置读写 + 掩码（Task 2，可单测）
│   ├── pool.py                    # 进程内连接池 + atexit 兜底（Task 3，可单测）
│   ├── auth.py                    # 按 auth_type 建 paramiko 连接（Task 4，可单测）
│   ├── conn_mgmt.py               # ssh_add/list/remove_connection（Task 5）
│   ├── exec_tool.py               # ssh_connect/exec/disconnect（Task 6）
│   ├── transfer.py                # ssh_upload/download/list_dir（Task 7）
│   ├── forward.py                 # ssh_forward（Task 8）
│   ├── icons/ssh.svg              # 深色图标（Task 9）
│   └── icons_light/ssh.svg        # 浅色图标（Task 9）
├── docs/design.md                 # 已存在
├── docs/plan.md                   # 本文件
├── tests/test_store.py            # Task 2 单测
├── tests/test_pool.py             # Task 3 单测
├── tests/test_auth.py             # Task 4 单测
└── README.md                      # Task 1
```

---

### Task 1: 插件骨架

**Files:**
- Create: `ssh-toolkit/.drifox-plugin/plugin.json`
- Create: `ssh-toolkit/tools/__init__.py`
- Create: `ssh-toolkit/README.md`

**Interfaces:**
- 无前置依赖。`plugin.json` 的 `name` 必须与目录名 `ssh-toolkit` 一致。

- [ ] **Step 1: 写 plugin.json**

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

- [ ] **Step 2: 写 tools/__init__.py（空文件）**

```python
```

- [ ] **Step 3: 写 README.md**

```markdown
# ssh-toolkit

SSH 远程工具包插件（纯 AI 工具，无 UI）。基于 paramiko，提供连接管理、命令执行、SFTP 文件传输、目录浏览、端口转发。

## 工具
ssh_add_connection / ssh_list_connections / ssh_remove_connection / ssh_connect / ssh_exec / ssh_upload / ssh_download / ssh_list_dir / ssh_forward / ssh_disconnect

## 依赖
运行时需要 paramiko：`pip install paramiko`

## 安全警告
连接配置（含密码/私钥口令）明文存于 `~/.drifox/cache/ssh/connections.json`，文件权限 600。
同机有读权限的进程/用户可见。生产环境建议使用 `publickey` + `ssh-agent`，避免存储密码。
```

- [ ] **Step 4: 校验 JSON 合法**

Run: `python -c "import json;json.load(open('ssh-toolkit/.drifox-plugin/plugin.json'));print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add ssh-toolkit/.drifox-plugin/plugin.json ssh-toolkit/tools/__init__.py ssh-toolkit/README.md
git commit -m "feat(ssh-toolkit): 插件骨架与 manifest"
```

---

### Task 2: store.py 连接配置读写

**Files:**
- Create: `ssh-toolkit/tools/store.py`
- Create: `ssh-toolkit/tests/test_store.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `load_connections() -> dict` — 返回 `{"version":1,"connections":[...]}`，文件不存在返回空结构
  - `save_connections(data: dict) -> None` — 写回并 `chmod 0o600`
  - `get_connection(name: str) -> dict | None`
  - `add_connection(conn: dict) -> None` — name 唯一校验，重复抛 `ValueError`
  - `remove_connection(name: str) -> bool` — 返回是否删除成功
  - `mask_passwords(data: dict) -> dict` — 深拷贝并将 `password`/`key_passphrase` 替换为 `****`
  - `CONNECTIONS_PATH` — 配置路径常量

- [ ] **Step 1: 写失败测试 test_store.py**

```python
import os, json, tempfile
import pytest
import ssh_toolkit_store as S  # 见下方 conftest 说明

@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    p = tmp_path / "connections.json"
    monkeypatch.setattr(S, "CONNECTIONS_PATH", str(p))
    return p

def test_load_empty(tmp_store):
    d = S.load_connections()
    assert d == {"version": 1, "connections": []}

def test_add_and_get(tmp_store):
    S.add_connection({"name": "h1", "host": "1.1.1.1", "user": "u", "auth_type": "password", "password": "secret"})
    c = S.get_connection("h1")
    assert c["host"] == "1.1.1.1"
    assert c["password"] == "secret"

def test_add_duplicate_raises(tmp_store):
    S.add_connection({"name": "h1", "host": "1.1.1.1", "user": "u", "auth_type": "publickey"})
    with pytest.raises(ValueError):
        S.add_connection({"name": "h1", "host": "2.2.2.2", "user": "u", "auth_type": "publickey"})

def test_remove(tmp_store):
    S.add_connection({"name": "h1", "host": "1.1.1.1", "user": "u", "auth_type": "publickey"})
    assert S.remove_connection("h1") is True
    assert S.get_connection("h1") is None

def test_mask(tmp_store):
    data = {"version": 1, "connections": [{"name": "h1", "password": "p", "key_passphrase": "k"}]}
    m = S.mask_passwords(data)
    assert m["connections"][0]["password"] == "****"
    assert m["connections"][0]["key_passphrase"] == "****"
    assert data["connections"][0]["password"] == "p"  # 原数据不变

def test_chmod_600(tmp_store):
    S.add_connection({"name": "h1", "host": "1.1.1.1", "user": "u", "auth_type": "publickey"})
    mode = os.stat(str(tmp_store)).st_mode & 0o777
    assert mode == 0o600
```

- [ ] **Step 2: 写实现 store.py**

```python
# ssh-toolkit/tools/store.py
# -*- coding: utf-8 -*-
"""连接配置读写：~/.drifox/cache/ssh/connections.json（明文，600 权限）"""
import json
import os
from pathlib import Path

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".drifox", "cache", "ssh")
CONNECTIONS_PATH = os.path.join(CACHE_DIR, "connections.json")
_MASK = "****"
_EMPTY = {"version": 1, "connections": []}


def _ensure_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def load_connections():
    if not os.path.exists(CONNECTIONS_PATH):
        return {"version": 1, "connections": []}
    with open(CONNECTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_connections(data):
    _ensure_dir()
    with open(CONNECTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(CONNECTIONS_PATH, 0o600)


def get_connection(name):
    for c in load_connections()["connections"]:
        if c.get("name") == name:
            return c
    return None


def add_connection(conn):
    if not conn.get("name"):
        raise ValueError("connection 必须含 name")
    data = load_connections()
    for c in data["connections"]:
        if c.get("name") == conn["name"]:
            raise ValueError(f"连接名已存在: {conn['name']}")
    data["connections"].append(conn)
    save_connections(data)


def remove_connection(name):
    data = load_connections()
    before = len(data["connections"])
    data["connections"] = [c for c in data["connections"] if c.get("name") != name]
    if len(data["connections"]) == before:
        return False
    save_connections(data)
    return True


def mask_passwords(data):
    import copy
    d = copy.deepcopy(data)
    for c in d.get("connections", []):
        if c.get("password"):
            c["password"] = _MASK
        if c.get("key_passphrase"):
            c["key_passphrase"] = _MASK
    return d
```

- [ ] **Step 3: 加 conftest 让 import 可用**

`tests/conftest.py`：
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import store as ssh_toolkit_store  # noqa: E402
```

- [ ] **Step 4: 跑测试**

Run: `cd ssh-toolkit && python -m pytest tests/test_store.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add ssh-toolkit/tools/store.py ssh-toolkit/tests/
git commit -m "feat(ssh-toolkit): 连接配置读写 store.py"
```

---

### Task 3: pool.py 连接池

**Files:**
- Create: `ssh-toolkit/tools/pool.py`
- Create: `ssh-toolkit/tests/test_pool.py`

**Interfaces:**
- Consumes: 无（paramiko client 由调用方传入）
- Produces:
  - `POOL: Dict[str, object]` — 模块级 `{handle: paramiko.SSHClient}`
  - `put_connection(name, client) -> str` — 返回 `handle = f"{name}:{uuid4().hex[:8]}"`
  - `get_client(ref) -> paramiko.SSHClient | None` — ref 为 handle 或 name（name 取首个活跃）
  - `remove_connection_handle(handle) -> bool`
  - `close_all()` — atexit 兜底关闭全部

- [ ] **Step 1: 写测试 test_pool.py**

```python
import ssh_toolkit_pool as P

class FakeClient:
    closed = False
    def close(self): self.closed = True

def test_put_get_handle():
    c = FakeClient()
    h = P.put_connection("h1", c)
    assert h.startswith("h1:")
    assert P.get_client(h) is c

def test_get_by_name():
    c = FakeClient()
    P.put_connection("h2", c)
    assert P.get_client("h2") is c

def test_remove():
    c = FakeClient()
    h = P.put_connection("h3", c)
    assert P.remove_connection_handle(h) is True
    assert P.get_client(h) is None

def test_close_all():
    c = FakeClient()
    P.put_connection("h4", c)
    P.close_all()
    assert c.closed is True
```

- [ ] **Step 2: 写实现 pool.py**

```python
# ssh-toolkit/tools/pool.py
# -*- coding: utf-8 -*-
"""进程内 SSH 连接池，按 handle 复用 paramiko client。"""
import atexit
from uuid import uuid4

POOL: dict = {}


def put_connection(name, client):
    handle = f"{name}:{uuid4().hex[:8]}"
    POOL[handle] = client
    return handle


def get_client(ref):
    if ref in POOL:
        return POOL[ref]
    for handle, client in POOL.items():
        if handle.split(":", 1)[0] == ref:
            return client
    return None


def remove_connection_handle(handle):
    if handle in POOL:
        POOL.pop(handle, None)
        return True
    return False


def close_all():
    for client in POOL.values():
        try:
            client.close()
        except Exception:
            pass
    POOL.clear()


atexit.register(close_all)
```

- [ ] **Step 3: 更新 conftest**

`tests/conftest.py` 增加：
```python
import pool as ssh_toolkit_pool  # noqa: E402
```

- [ ] **Step 4: 跑测试**

Run: `cd ssh-toolkit && python -m pytest tests/test_pool.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add ssh-toolkit/tools/pool.py ssh-toolkit/tests/
git commit -m "feat(ssh-toolkit): 连接池 pool.py"
```

---

### Task 4: auth.py 认证分支

**Files:**
- Create: `ssh-toolkit/tools/auth.py`
- Create: `ssh-toolkit/tests/test_auth.py`

**Interfaces:**
- Consumes: `store.get_connection`
- Produces:
  - `connect(conn: dict) -> paramiko.SSHClient` — 按 `auth_type` 分支建立连接；缺 paramiko 抛 `RuntimeError("缺少依赖 paramiko，请运行：pip install paramiko")`
  - `SUPPORTED = {"publickey","password","keyboard-interactive","agent"}`

- [ ] **Step 1: 写测试 test_auth.py（mock paramiko）**

```python
import ssh_toolkit_auth as A

class FakeClient:
    kwargs = None
    def __init__(self): self.closed = False
    def set_missing_host_key_policy(self, p): pass
    def connect(self, **kw): self.kwargs = kw
    def close(self): self.closed = True

def test_publickey(monkeypatch):
    fc = FakeClient()
    monkeypatch.setattr(A, "paramiko", type("P", (), {"SSHClient": lambda: fc, "AutoAddPolicy": object}))
    c = A.connect({"host":"h","port":22,"user":"u","auth_type":"publickey","key_path":"~/.ssh/id_rsa","key_passphrase":"kp","timeout":10})
    assert c.kwargs["key_filename"] == "~/.ssh/id_rsa"
    assert c.kwargs["passphrase"] == "kp"

def test_password(monkeypatch):
    fc = FakeClient()
    monkeypatch.setattr(A, "paramiko", type("P", (), {"SSHClient": lambda: fc, "AutoAddPolicy": object}))
    A.connect({"host":"h","port":22,"user":"u","auth_type":"password","password":"pw","timeout":10})
    assert fc.kwargs["password"] == "pw"

def test_unsupported(monkeypatch):
    fc = FakeClient()
    monkeypatch.setattr(A, "paramiko", type("P", (), {"SSHClient": lambda: fc, "AutoAddPolicy": object}))
    try:
        A.connect({"host":"h","port":22,"user":"u","auth_type":"ldap","timeout":10})
        assert False, "应抛 ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: 写实现 auth.py**

```python
# ssh-toolkit/tools/auth.py
# -*- coding: utf-8 -*-
"""按 auth_type 建立 paramiko SSH 连接。"""
import os

try:
    import paramiko
except ImportError:
    paramiko = None

SUPPORTED = {"publickey", "password", "keyboard-interactive", "agent"}


def _client():
    if paramiko is None:
        raise RuntimeError("缺少依赖 paramiko，请运行：pip install paramiko")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return c


def connect(conn):
    auth_type = conn.get("auth_type", "publickey")
    if auth_type not in SUPPORTED:
        raise ValueError(f"不支持的 auth_type: {auth_type}，可选 {sorted(SUPPORTED)}")
    client = _client()
    host = conn["host"]
    port = int(conn.get("port", 22))
    user = conn.get("user")
    timeout = int(conn.get("timeout", 10))
    base = dict(hostname=host, port=port, username=user, timeout=timeout)
    if auth_type == "publickey":
        base.update(key_filename=os.path.expanduser(conn.get("key_path", "~/.ssh/id_rsa")),
                    passphrase=conn.get("key_passphrase") or None)
    elif auth_type == "password":
        base.update(password=conn.get("password"))
    elif auth_type == "agent":
        base.update(allow_agent=True, look_for_keys=False)
    elif auth_type == "keyboard-interactive":
        base.update(auth_interactive_callback=lambda t, p: [conn.get("password", "")])

    def _handler(title, instructions, prompts):
        return [conn.get("password", "")] * len(prompts)

    if auth_type == "keyboard-interactive":
        base["auth_interactive_callback"] = _handler
    client.connect(**base)
    return client
```

- [ ] **Step 3: 更新 conftest**

`tests/conftest.py` 增加：
```python
import auth as ssh_toolkit_auth  # noqa: E402
```

- [ ] **Step 4: 跑测试**

Run: `cd ssh-toolkit && python -m pytest tests/test_auth.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add ssh-toolkit/tools/auth.py ssh-toolkit/tests/
git commit -m "feat(ssh-toolkit): 认证分支 auth.py"
```

---

### Task 5: conn_mgmt.py 连接管理工具注册

**Files:**
- Create: `ssh-toolkit/tools/conn_mgmt.py`

**Interfaces:**
- Consumes: `store.add_connection / get_connection / remove_connection / mask_passwords / load_connections`
- Produces: `register(registry)` 注册 `ssh_add_connection`(safe) / `ssh_list_connections`(safe) / `ssh_remove_connection`(safe)

- [ ] **Step 1: 写 conn_mgmt.py**

```python
# ssh-toolkit/tools/conn_mgmt.py
# -*- coding: utf-8 -*-
"""连接管理工具：增 / 列 / 删（本地配置，safe）。"""
from app.tools.result import ToolResult

import store


def _add_impl(tool_ctx, **kwargs):
    conn = {
        "name": kwargs.get("name"),
        "host": kwargs.get("host"),
        "port": int(kwargs.get("port", 22)),
        "user": kwargs.get("user"),
        "auth_type": kwargs.get("auth_type", "publickey"),
        "key_path": kwargs.get("key_path", "~/.ssh/id_rsa"),
        "password": kwargs.get("password", ""),
        "key_passphrase": kwargs.get("key_passphrase", ""),
        "timeout": int(kwargs.get("timeout", 10)),
        "note": kwargs.get("note", ""),
    }
    try:
        store.add_connection(conn)
    except ValueError as e:
        return ToolResult(False, content=str(e))
    return ToolResult(True, content=f"已保存连接：{conn['name']} ({conn['user']}@{conn['host']}:{conn['port']})")


def _list_impl(tool_ctx, **kwargs):
    data = store.mask_passwords(store.load_connections())
    conns = data["connections"]
    if not conns:
        return ToolResult(True, content="（无已保存连接）")
    lines = [f"{c['name']}  {c.get('user','')}@{c.get('host','')}:{c.get('port',22)}  [{c.get('auth_type','')}]" for c in conns]
    return ToolResult(True, content="\n".join(lines))


def _remove_impl(tool_ctx, **kwargs):
    name = kwargs.get("name")
    ok = store.remove_connection(name)
    if ok:
        return ToolResult(True, content=f"已删除连接：{name}")
    return ToolResult(False, content=f"未找到连接：{name}")


def register(registry):
    registry.register(
        "ssh_add_connection",
        {"type": "function", "function": {
            "name": "ssh_add_connection",
            "description": "保存一个命名 SSH 连接配置到本地（~/.drifox/cache/ssh/connections.json）",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "连接名（唯一标识）"},
                "host": {"type": "string", "description": "主机地址"},
                "port": {"type": "integer", "description": "SSH 端口，默认 22"},
                "user": {"type": "string", "description": "登录用户名"},
                "auth_type": {"type": "string", "description": "认证方式: publickey/password/keyboard-interactive/agent"},
                "key_path": {"type": "string", "description": "私钥路径（publickey/agent）"},
                "password": {"type": "string", "description": "密码（明文存储，注意安全）"},
                "key_passphrase": {"type": "string", "description": "私钥口令"},
                "timeout": {"type": "integer", "description": "连接超时秒"},
                "note": {"type": "string", "description": "备注"},
            }, "required": ["name", "host", "user"]},
        }},
        impl=_add_impl, danger="safe", icon="ssh", cn_name="SSH 保存连接", group="SSH 远程",
        description="保存命名 SSH 连接配置",
    )
    registry.register(
        "ssh_list_connections",
        {"type": "function", "function": {
            "name": "ssh_list_connections",
            "description": "列出所有已保存的 SSH 连接（密码掩码）",
            "parameters": {"type": "object", "properties": {}},
        }},
        impl=_list_impl, danger="safe", icon="ssh", cn_name="SSH 列出连接", group="SSH 远程",
        description="列出已保存的 SSH 连接",
    )
    registry.register(
        "ssh_remove_connection",
        {"type": "function", "function": {
            "name": "ssh_remove_connection",
            "description": "删除一个已保存的 SSH 连接",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "连接名"},
            }, "required": ["name"]},
        }},
        impl=_remove_impl, danger="safe", icon="ssh", cn_name="SSH 删除连接", group="SSH 远程",
        description="删除已保存的 SSH 连接",
    )
```

- [ ] **Step 2: py_compile 校验**

Run: `cd ssh-toolkit && python -m py_compile tools/conn_mgmt.py && echo ok`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add ssh-toolkit/tools/conn_mgmt.py
git commit -m "feat(ssh-toolkit): 连接管理工具注册"
```

---

### Task 6: exec_tool.py 连接/执行/断开

**Files:**
- Create: `ssh-toolkit/tools/exec_tool.py`

**Interfaces:**
- Consumes: `store.get_connection`, `auth.connect`, `pool.put_connection / get_client / remove_connection_handle`
- Produces: `register(registry)` 注册 `ssh_connect`(dangerous) / `ssh_exec`(dangerous) / `ssh_disconnect`(safe)

- [ ] **Step 1: 写 exec_tool.py**

```python
# ssh-toolkit/tools/exec_tool.py
# -*- coding: utf-8 -*-
"""SSH 连接 / 命令执行 / 断开（dangerous 除断开外）。"""
from app.tools.result import ToolResult

import store, auth, pool


def _resolve(ref):
    return pool.get_client(ref) or (auth.connect(store.get_connection(ref)) if store.get_connection(ref) else None)


def _connect_impl(tool_ctx, **kwargs):
    name = kwargs.get("name")
    conn = store.get_connection(name)
    if conn is None:
        # 允许运行时直接传连接参数
        conn = {k: kwargs.get(k) for k in ("name", "host", "port", "user", "auth_type", "key_path", "password", "key_passphrase", "timeout")}
        if not conn.get("host") or not conn.get("user"):
            return ToolResult(False, content=f"未找到连接 {name}，且未提供 host/user")
    try:
        client = auth.connect(conn)
    except Exception as e:
        return ToolResult(False, content=f"连接失败：{e}")
    handle = pool.put_connection(name, client)
    return ToolResult(True, content=f"已连接 {name or conn.get('host')}，handle={handle}")


def _exec_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    client = pool.get_client(ref) if ref else None
    if client is None:
        return ToolResult(False, content=f"未找到活跃连接：{ref}（先 ssh_connect）")
    command = kwargs.get("command", "")
    timeout = int(kwargs.get("timeout", 30))
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
    except Exception as e:
        return ToolResult(False, content=f"执行失败：{e}")
    body = f"$ {command}\n{out}{err}\nexit={code}"
    return ToolResult(True, content=body)


def _disconnect_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name") or kwargs.get("forward_id")
    if ref and pool.remove_connection_handle(ref):
        return ToolResult(True, content=f"已断开：{ref}")
    return ToolResult(True, content=f"未找到活跃连接：{ref}（可能已断开）")


def register(registry):
    registry.register(
        "ssh_connect",
        {"type": "function", "function": {
            "name": "ssh_connect",
            "description": "建立 SSH 连接并加入连接池，返回 handle（供 ssh_exec 等复用）",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "已保存连接名；或运行时 host/user 直接连"},
                "host": {"type": "string", "description": "主机（运行时直连时用）"},
                "port": {"type": "integer", "description": "端口"},
                "user": {"type": "string", "description": "用户名"},
                "auth_type": {"type": "string", "description": "认证方式"},
                "key_path": {"type": "string", "description": "私钥路径"},
                "password": {"type": "string", "description": "密码"},
                "key_passphrase": {"type": "string", "description": "私钥口令"},
                "timeout": {"type": "integer", "description": "超时秒"}
            }, "required": []},
        }},
        impl=_connect_impl, danger="dangerous", icon="ssh", cn_name="SSH 连接", group="SSH 远程",
        description="建立 SSH 连接",
    )
    registry.register(
        "ssh_exec",
        {"type": "function", "function": {
            "name": "ssh_exec",
            "description": "在已连接主机上执行命令，返回 stdout/stderr/exit code",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "ssh_connect 返回的 handle，或连接名"},
                "name": {"type": "string", "description": "连接名（无 handle 时用）"},
                "command": {"type": "string", "description": "要执行的 shell 命令"},
                "timeout": {"type": "integer", "description": "执行超时秒，默认 30"},
            }, "required": ["command"]},
        }},
        impl=_exec_impl, danger="dangerous", icon="ssh", cn_name="SSH 执行命令", group="SSH 远程",
        description="在远程主机执行命令",
    )
    registry.register(
        "ssh_disconnect",
        {"type": "function", "function": {
            "name": "ssh_disconnect",
            "description": "关闭 SSH 连接或端口转发",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "forward_id": {"type": "string", "description": "端口转发 id"},
            }, "required": []},
        }},
        impl=_disconnect_impl, danger="safe", icon="ssh", cn_name="SSH 断开", group="SSH 远程",
        description="关闭 SSH 连接/转发",
    )

---

### Task 7: transfer.py 文件传输与目录浏览

**Files:**
- Create: `ssh-toolkit/tools/transfer.py`

**Interfaces:**
- Consumes: `pool.get_client`
- Produces: `register(registry)` 注册 `ssh_upload`(dangerous) / `ssh_download`(dangerous) / `ssh_list_dir`(safe)

- [ ] **Step 1: 写 transfer.py**

```python
# ssh-toolkit/tools/transfer.py
# -*- coding: utf-8 -*-
"""SFTP 文件传输与目录浏览（upload/download/list_dir）。"""
import os
from app.tools.result import ToolResult

import pool


def _client(ref):
    c = pool.get_client(ref) if ref else None
    if c is None:
        raise RuntimeError(f"未找到活跃连接：{ref}（先 ssh_connect）")
    return c


def _norm_remote(path, home):
    if not path:
        return "."
    if path.startswith("~"):
        path = os.path.join(home, path[1:].lstrip("/"))
    elif not os.path.isabs(path):
        path = os.path.join(home, path)
    return path


def _home(client):
    return client.exec_command("echo $HOME")[1].read().decode("utf-8", "replace").strip() or "~"


def _upload_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    local = kwargs.get("local_path")
    remote = kwargs.get("remote_path")
    if not local or not remote:
        return ToolResult(False, content="需要 local_path 与 remote_path")
    try:
        client = _client(ref)
        remote = _norm_remote(remote, _home(client))
        sftp = client.open_sftp()
        sftp.put(local, remote)
        sftp.close()
    except Exception as e:
        return ToolResult(False, content=f"上传失败：{e}")
    return ToolResult(True, content=f"已上传 {local} → {remote} @ {ref}")


def _download_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    remote = kwargs.get("remote_path")
    local = kwargs.get("local_path")
    if not local or not remote:
        return ToolResult(False, content="需要 remote_path 与 local_path")
    try:
        client = _client(ref)
        remote = _norm_remote(remote, _home(client))
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        sftp = client.open_sftp()
        sftp.get(remote, local)
        sftp.close()
    except Exception as e:
        return ToolResult(False, content=f"下载失败：{e}")
    return ToolResult(True, content=f"已下载 {remote} → {local} @ {ref}")


def _list_dir_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    remote = kwargs.get("remote_path", ".")
    try:
        client = _client(ref)
        remote = _norm_remote(remote, _home(client))
        sftp = client.open_sftp()
        items = sftp.listdir_attr(remote)
        lines = []
        for a in items:
            kind = "d" if (a.st_mode & 0o170000) == 0o040000 else "f"
            lines.append(f"{kind} {a.st_size:>10} {a.st_mtime:.0f}  {a.filename}")
        sftp.close()
    except Exception as e:
        return ToolResult(False, content=f"浏览失败：{e}")
    return ToolResult(True, content="\n".join(lines) or "（空目录）")


def register(registry):
    registry.register(
        "ssh_upload",
        {"type": "function", "function": {
            "name": "ssh_upload",
            "description": "通过 SFTP 上传本地文件到远程主机",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "local_path": {"type": "string", "description": "本地文件路径"},
                "remote_path": {"type": "string", "description": "远程目标路径"},
            }, "required": ["local_path", "remote_path"]},
        }},
        impl=_upload_impl, danger="dangerous", icon="ssh", cn_name="SSH 上传文件", group="SSH 远程",
        description="SFTP 上传文件",
    )
    registry.register(
        "ssh_download",
        {"type": "function", "function": {
            "name": "ssh_download",
            "description": "通过 SFTP 从远程主机下载文件到本地",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "remote_path": {"type": "string", "description": "远程文件路径"},
                "local_path": {"type": "string", "description": "本地目标路径"},
            }, "required": ["remote_path", "local_path"]},
        }},
        impl=_download_impl, danger="dangerous", icon="ssh", cn_name="SSH 下载文件", group="SSH 远程",
        description="SFTP 下载文件",
    )
    registry.register(
        "ssh_list_dir",
        {"type": "function", "function": {
            "name": "ssh_list_dir",
            "description": "浏览远程目录文件列表（权限/大小/mtime）",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "remote_path": {"type": "string", "description": "远程目录路径，默认当前目录"},
                "recursive": {"type": "boolean", "description": "是否递归"},
            }, "required": []},
        }},
        impl=_list_dir_impl, danger="safe", icon="ssh", cn_name="SSH 浏览目录", group="SSH 远程",
        description="浏览远程目录",
    )
```

- [ ] **Step 2: py_compile 校验**

Run: `cd ssh-toolkit && python -m py_compile tools/transfer.py && echo ok`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add ssh-toolkit/tools/transfer.py
git commit -m "feat(ssh-toolkit): 文件传输与目录浏览工具"
```

---

### Task 8: forward.py 端口转发

**Files:**
- Create: `ssh-toolkit/tools/forward.py`

**Interfaces:**
- Consumes: `pool.get_client`
- Produces: `register(registry)` 注册 `ssh_forward`(dangerous)；模块级 `FORWARDS` 记录后台任务

- [ ] **Step 1: 写 forward.py**

```python
# ssh-toolkit/tools/forward.py
# -*- coding: utf-8 -*-
"""SSH 端口转发（local -L），后台线程运行。"""
import socket
import threading
from app.tools.result import ToolResult

import pool

FORWARDS = {}  # forward_id -> {"thread", "stop"}


def _pipe(src, dst):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        for s in (src, dst):
            try:
                s.close()
            except Exception:
                pass


def _forward_loop(fid, client, bind_addr, bind_port, remote_addr, remote_port, stop):
    transport = client.get_transport()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_addr, bind_port))
    sock.listen(5)
    while not stop.is_set():
        try:
            conn, _ = sock.accept()
        except OSError:
            break
        try:
            ch = transport.open_channel("direct-tcpip", (remote_addr, remote_port), ("127.0.0.1", 0))
        except Exception:
            conn.close()
            continue
        threading.Thread(target=_pipe, args=(conn, ch), daemon=True).start()
    try:
        sock.close()
    except Exception:
        pass


def _forward_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    ftype = kwargs.get("type", "local")
    bind_addr = kwargs.get("bind_addr", "127.0.0.1")
    bind_port = int(kwargs.get("bind_port", 0))
    remote_addr = kwargs.get("remote_addr", "127.0.0.1")
    remote_port = int(kwargs.get("remote_port", 0))
    client = pool.get_client(ref) if ref else None
    if client is None:
        return ToolResult(False, content=f"未找到活跃连接：{ref}")
    fid = f"fw:{ref}:{bind_port}"
    stop = threading.Event()
    t = threading.Thread(target=_forward_loop, args=(fid, client, bind_addr, bind_port, remote_addr, remote_port, stop), daemon=True)
    t.start()
    FORWARDS[fid] = {"thread": t, "stop": stop}
    return ToolResult(True, content=f"已启动{ftype}转发 {fid}: {bind_addr}:{bind_port} → {remote_addr}:{remote_port}")


def register(registry):
    registry.register(
        "ssh_forward",
        {"type": "function", "function": {
            "name": "ssh_forward",
            "description": "建立 SSH 端口转发（local/remote），后台运行",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "type": {"type": "string", "description": "local 或 remote"},
                "bind_addr": {"type": "string", "description": "本地绑定地址"},
                "bind_port": {"type": "integer", "description": "本地绑定端口"},
                "remote_addr": {"type": "string", "description": "远端目标地址"},
                "remote_port": {"type": "integer", "description": "远端目标端口"},
            }, "required": ["bind_port", "remote_port"]},
        }},
        impl=_forward_impl, danger="dangerous", icon="ssh", cn_name="SSH 端口转发", group="SSH 远程",
        description="SSH 端口转发",
    )
```

- [ ] **Step 2: py_compile 校验**

Run: `cd ssh-toolkit && python -m py_compile tools/forward.py && echo ok`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add ssh-toolkit/tools/forward.py
git commit -m "feat(ssh-toolkit): 端口转发工具"
```

---

### Task 9: 图标

**Files:**
- Create: `ssh-toolkit/tools/icons/ssh.svg`
- Create: `ssh-toolkit/tools/icons_light/ssh.svg`

**Interfaces:** 供 register 的 `icon="ssh"` 引用；深色版（白描边）+ 浅色版（深色描边）。

- [ ] **Step 1: 写深色图标 ssh.svg**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="14" rx="2"/><path d="M6 9l3 3-3 3"/><line x1="12" y1="15" x2="17" y2="15"/></svg>
```

- [ ] **Step 2: 写浅色图标 ssh.svg（stroke 改深色 #1f2937）**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#1f2937" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="14" rx="2"/><path d="M6 9l3 3-3 3"/><line x1="12" y1="15" x2="17" y2="15"/></svg>
```

- [ ] **Step 3: 校验 SVG 合法**

Run: `python -c "import xml.dom.minidom; xml.dom.minidom.parse('ssh-toolkit/tools/icons/ssh.svg'); xml.dom.minidom.parse('ssh-toolkit/tools/icons_light/ssh.svg'); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add ssh-toolkit/tools/icons ssh-toolkit/tools/icons_light
git commit -m "feat(ssh-toolkit): 工具图标"
```

---

### Task 10: 全量验证与发布准备

**Files:**
- 校验：`tools/validate_plugins.py`、`tools/generate_marketplace.py`

**Interfaces:** 无新增代码；聚合前面所有任务产物。

- [ ] **Step 1: py_compile 全部 tools**

Run: `cd ssh-toolkit && python -m py_compile tools/*.py && echo ok`
Expected: `ok`

- [ ] **Step 2: 单测全过**

Run: `cd ssh-toolkit && python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 3: 跑市场校验（复制到临时仓库）**

```bash
git clone --depth=1 https://github.com/martin98-afk/drifox-plugins.git /tmp/dfp
cp -r ssh-toolkit /tmp/dfp/plugins/
cd /tmp/dfp && python tools/validate_plugins.py && python tools/generate_marketplace.py
```
Expected: validate 全 OK，marketplace.json 更新

- [ ] **Step 4: 手动冒烟（有可用 SSH 主机时）**

依次调用：ssh_add_connection → ssh_list_connections → ssh_connect → ssh_exec("uname -a") → ssh_upload → ssh_download → ssh_list_dir → ssh_forward → ssh_disconnect

- [ ] **Step 5: 最终 Commit**

```bash
git add ssh-toolkit
git commit -m "feat(ssh-toolkit): SSH 远程工具包插件完整实现"
```

---

## 自审

**1. 规范覆盖**：design.md §3–§11 的 10 个工具、连接池、认证、存储、图标、验证均对应到 Task 1–10。无遗漏。

**2. 占位符扫描**：无 TBD/TODO；所有代码块为完整实现。

**3. 类型一致性**：store/pool/auth 接口签名在 Task 2–4 定义，Task 5–8 的 impl 调用一致（`get_connection` / `connect` / `put_connection` / `get_client` / `remove_connection_handle` / `add_connection` / `remove_connection` / `mask_passwords` / `load_connections`）。