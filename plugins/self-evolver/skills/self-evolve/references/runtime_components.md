# Runtime 组件注册契约速查

> **何时读这份**：scaffold 时选了 `storages / serializers / gateways / model_adapters / loop_policies / engines` 等"runtime 类"组件，或用户提到"系统配置卡片"、"注册一个 X 引擎"。
>
> **来源**：jsonl-storage v0.1.0 开发实战 + gateway-feishu 对照分析。

## 一、17 类组件分类

| 类型 | 是否 runtime | 注册契约 | 是否有 config_schema 卡片 |
|------|-------------|----------|--------------------------|
| `tools` | 否 | `register(registry)` 暴露工具 | 可选 |
| `commands` | 否 | markdown 文件 | 否 |
| `agents` | 否 | markdown 文件 | 否 |
| `skills` | 否 | SKILL.md 目录 | 否 |
| `hooks` | 否（启动期） | hooks.json + .py | 否 |
| `mcp` | 否 | .mcp.json | 否 |
| `lsp` | 否 | lsp.json | 否 |
| `themes` | 否 | theme.json | 否 |
| `ui` | 否 | ui/*.py + register | 否 |
| `providers` | 否 | providers/*.py + register | 否 |
| `team_templates` | 否 | markdown | 否 |
| **`storages`** | **✅** | **实例直接注册**（**无回调**） | ✅ 仅渲染 |
| **`serializers`** | **✅** | 实例直接注册 | ✅ |
| **`gateways`** | **✅** | **def 对象 + 3 个回调** | ✅ 渲染+保存 |
| **`model_adapters`** | **✅** | 实例直接注册 | ✅ |
| **`loop_policies`** | **✅** | 实例直接注册 | ✅ |
| **`engines`** | **✅** | 实例直接注册 | ✅ |

**runtime 类 = 注册到主程序运行时注册池，主程序从池里选一个 active 实例消费。**

## 二、storages 组件契约（以 jsonl-storage 为范本）

### 注册形式

```python
class MyStorageEngine:
    id = "my-storage"          # 必需：主程序用 id 识别引擎
    # 可选属性（消费方 hasattr 探测）：store / is_initialized / _db_path
    def __init__(self, db_dir=None): ...
    # 30+ 方法对齐 system/storages/sqlite.py（save/get/list/delete/...）

def register(registry):
    registry.register(MyStorageEngine())   # 直接传实例，无回调
```

### ⚠ 关键限制

- **storages 注册没有 `config_builder / config_writer` 回调**（gateways 才有）
- 主程序 `StorageRegistry._active` 默认 `"sqlite"`，**全仓库未发现任何代码基于 plugin config_schema 自动 set_active**
- 不实现自激活 = 插件永远只是"并存可选"，开关不生效
- **必须自激活**：register 末尾读 enabled → true 则 `registry.set_active("my-id")`（详见 storage_engine.md 第八节）
- `registry.set_active(...)` 可直接用，`_RegistryProxy.__getattr__` 转发到底层真 registry

### config_schema 字段类型枚举（**官方可用值**）

| 值 | 控件 |
|----|------|
| `bool` | 开关 |
| `text` | 单行输入 |
| `password` | 密码框 |
| `select` | 下拉（需 `options: [{label, value}]`） |

> ❌ `"switch"` 不是合法值（jsonl-storage v0.1.0 初版踩坑）→ 用 `bool`

### PluginConfigStore 用法（E1 契约）

```python
# 读
from app.plugins.managers.plugin_config_store import PluginConfigStore
val = PluginConfigStore().get("plugin-name", "key")
# 写
PluginConfigStore().set_values("plugin-name", {"key1": v1, "key2": v2})
```

- 任意异常静默降级（导入期 PluginConfigStore 可能未初始化）
- 插件名 = `plugin.json` 的 `name` 字段

## 三、gateways 组件契约（对照参考）

```python
def register(registry):
    from app.plugins.contracts.gateway_platform import GatewayPlatformDef
    registry.register(GatewayPlatformDef(
        platform_id="xxx",
        display_name="xxx",
        adapter_factory=lambda cfg: MyAdapter(cfg),
        config_builder=_build_config,            # 启动读配置
        config_writer=_write_config,             # 写配置
        build_config_values=_build_config_values, # 设置卡片保存回调
        validate_config=lambda cfg: (ok, msg),
        ui_order=50,
    ))
```

**核心区别**：gateways 把配置读写逻辑挂在回调里，主程序在 settings 保存时会调 `build_config_values` 拿到新 `PlatformConfig` 写回；storages 没这套机制。

## 四、jsonl-storage 实战踩坑清单

1. **`@staticmethod` 残留**：把 `_read_jsonl` 改实例方法时忘了去掉装饰器，导致 `self._read_jsonl(path)` 调用报"missing positional argument: path"
2. **`config_schema` 字段类型**：用 `"switch"` 渲染不出来，要用 `"bool"`
3. **storages 注册无回调**：不能像 gateway 那样挂 `config_builder`，只能在 `__init__` 里 try/except 读 PluginConfigStore
4. **主程序侧引擎选取**：插件无法"主动覆盖 sqlite"，只能注册到池里等主程序挑

## 五、模板：把经验复制到下一个 storages 插件

```python
# storages/<name>.py
class <Name>StorageEngine:
    id = "<name>"
    def __init__(self, db_dir=None):
        cfg_db_dir, cfg_on_corrupt = self._load_plugin_config()  # 见 PluginConfigStore 模式
        self._base = Path(db_dir or cfg_db_dir or "~/.drifox/data/<name>/")
    def _load_plugin_config(self):  # 静默降级
        try:
            from app.plugins.managers.plugin_config_store import PluginConfigStore
            s = PluginConfigStore()
            return str(s.get("<plugin-name>", "db_dir") or "").strip(), \
                   str(s.get("<plugin-name>", "on_corrupt") or "skip").strip()
        except Exception:
            return "", "skip"
    # ... 全部对齐 sqlite.py 方法签名
def register(registry):
    registry.register(<Name>StorageEngine())
```

并配 `plugin.json`：
```json
{
    "components": { "storages": true, ... },
    "config_schema": {
        "title": "...",
        "fields": [
            {"key": "enabled", "label": "...", "type": "bool", "default": false},
            {"key": "db_dir",  "label": "...", "type": "text", "default": ""}
        ]
    }
}
```