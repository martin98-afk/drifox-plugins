# Storage Engine 组件开发实战

> **何时读这份**：用户要做"存储替换插件"、"持久化换格式"、"xlsx/jsonl/csv 存会话"等。
> 父文档：[runtime_components.md](runtime_components.md)
> **实战原型**：`jsonl-storage` v0.1.0（~/.drifox/plugins/jsonl-storage/）

## 一、必读约束

1. **接口签名 100% 对齐 `system/storages/sqlite.py`**——主程序按 sqlite 的契约消费，签名不一致会运行时崩
2. **注册即传实例，无回调**——`registry.register(MyEngine())`，别套 def 包装
3. **必须有 `id` 类属性**——主程序靠 id 识别引擎
4. **可选属性兼容**：消费方会用 `hasattr` 探测 `store / is_initialized / _db_path`，建议都给
5. **`config_schema` 字段类型只用 `bool/text/password/select`**，不要用 `switch`

## 二、接口方法清单（与 sqlite.py 对齐）

### SessionRepository 主接口
```python
def save(self, session: dict) -> bool: ...
def get(self, session_id: str) -> Optional[dict]: ...
def get_all(self, limit: int = 100, offset: int = 0) -> List[dict]: ...
def get_by_project(self, project: str, limit: int = 100) -> List[dict]: ...
def get_projects(self) -> List[dict]: ...
def delete(self, session_id: str) -> bool: ...
```

### SessionStore 消费方
```python
def save_session(self, session: dict) -> bool
def get_session(self, session_id: str) -> Optional[dict]
def get_sessions(self, limit: int = 100, offset: int = 0) -> List[dict]
def get_sessions_lightweight(self, limit: int = 100, offset: int = 0) -> List[dict]
def get_sessions_by_team_run_id(self, run_id: str) -> List[dict]
def delete_session(self, session_id: str) -> bool
def get_session_count(self) -> int
def update_session_project(self, session_id: str, project: str) -> bool
def archive_sessions_by_project(self, project: str) -> int
def clear_old_subagent_tasks(self, days: int = 7) -> int
def force_cleanup_project(self, project_name: str) -> bool
```

### 文件操作子表
```python
def record_file_operation(self, session_id, call_id, tool_name, file_path, backup_path) -> bool
def get_file_operations_by_call_id(self, session_id, call_id) -> List[dict]
def get_all_file_operations(self, session_id) -> List[dict]
def clear_session_file_operations(self, session_id) -> None
def remove_file_operation(self, session_id, call_id) -> int
```

### 可选能力（isinstance 探测）
```python
def update_session_title(self, session_id: str, title: str) -> bool
def get_session_counts(self) -> Dict[str, int]   # total/today/week
def get_input_history(self, limit: int = 50) -> List[Dict[str, Any]]
def add_input_history(self, content: str, attachments: Optional[list] = None) -> bool
```

## 三、典型数据布局选择

| 格式 | 优势 | 劣势 |
|------|------|------|
| **per-session 文件（推荐）** | 单 session 损坏不影响其它；易于 git diff | `get_all` 需要扫描全目录 |
| 单文件 sqlite 移植 | 与 sqlite 行为最接近 | 没意义，不如直接用 sqlite |
| 事件流（append-only） | 适合审计/分析 | `get(session_id)` 需要回放重放，慢 |

jsonl-storage 选择 per-session + 辅助流（file_ops/input_history/subagent_tasks 各自追加写）。

## 四、原子写模式（必用）

```python
@staticmethod
def _atomic_write_jsonl(path: Path, lines: List[str]) -> None:
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except Exception: pass
        raise
```

## 五、读坏行的容错

提供两种行为让用户在 config_schema 选：
- `skip`（默认）：跳过坏行继续读
- `empty`：碰到坏行立刻返回 `[]`（视整文件空，激进恢复）

实现：
```python
def _read_jsonl(self, path: Path) -> List[dict]:
    if not path.exists(): return []
    out = []
    with open(path, "r", encoding="utf-8", newline="\n") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: out.append(json.loads(line))
            except json.JSONDecodeError:
                if getattr(self, "_on_corrupt", "skip") == "empty":
                    return []
                continue
    return out
```

## 六、踩过的坑（不要重复）

1. **去掉 `@staticmethod` 时漏掉装饰器**：`_read_jsonl` 改实例方法后必须删 `@staticmethod`，否则调用报 `missing positional argument: path`
2. **`config_schema` 字段类型用 `switch`**：settings 面板渲染不出来，用 `bool`
3. **想用 hook "拦截 sqlite 写入"**：不可行，sqlite 写入路径是主程序内部，插件 hook 不到；只能注册并存引擎等主程序切换
4. **`record_file_operation` 忘了 session_id 校验**：空 sid 会写入垃圾文件
5. **`_session_mtime` 取不到 created_at**：兜底返回 `datetime.utcnow()`，否则 list 排序会 TypeError

## 七、模板（可复制）

```python
class MyStorageEngine:
    id = "my-storage"
    def __init__(self, db_dir=None):
        cfg_dir, cfg_mode = self._load_cfg()
        self._base = Path(db_dir or cfg_dir or Path.home() / ".drifox" / "data" / "my")
        # ...
    def _load_cfg(self):  # 见 runtime_components.md 的 PluginConfigStore 模式
        try:
            from app.plugins.managers.plugin_config_store import PluginConfigStore
            s = PluginConfigStore()
            return str(s.get("my-storage", "db_dir") or "").strip(), "skip"
        except Exception:
            return "", "skip"
    # ... 抄 sqlite.py 同名方法

def register(registry):
    engine = MyStorageEngine()
    registry.register(engine)
    _try_self_activate(registry)   # 见第八节：主程序不主动切，插件自激活

def _try_self_activate(registry):
    """主程序不会基于 plugin config_schema 自动 set_active；插件自己接管"""
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore
        if not PluginConfigStore().get("my-storage", "enabled"):
            return
    except Exception:
        return
    try:
        ok = registry.set_active("my-storage")  # _RegistryProxy.__getattr__ 转发到底层 registry
        if not ok:
            try:
                from loguru import logger
                logger.debug("[my-storage] set_active returned False — pool not ready")
            except Exception: pass
    except Exception:
        pass
```

## 八、自激活（核心模式 — 不踩就只"并存"）

主程序默认 `StorageRegistry._active = "sqlite"`，全仓库未发现任何代码会基于 plugin config_schema 自动调用 `set_active`。**不实现自激活 = 插件永远只是并存可选**。

实现要点：
1. register 末尾调用 `_try_self_activate(registry)`
2. 读 `PluginConfigStore().get(<plugin_name>, "enabled")`，true 才 set_active
3. `registry.set_active(...)` 可直接用——`_RegistryProxy.__getattr__` 转发到真 `StorageRegistry`
4. 全部异常静默降级（PluginConfigStore 未初始化 / pool not ready 等）——不阻塞 register

验证用 mock：fake_store.get.return_value = True/False + fake_registry.set_active.return_value = True/False，覆盖 4 个场景。

配套 `plugin.json` 见 [runtime_components.md](runtime_components.md) 第五节。