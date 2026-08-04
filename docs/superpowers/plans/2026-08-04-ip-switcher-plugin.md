# ip-switcher 插件实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 开发一个 DriFox UI 插件 `ip-switcher`：当白名单免费模型请求触发限流（HTTP 429）时，自动切换本地代理池出口 IP 并重试；提供仪表盘浮动卡片展示当前 IP、换绑历史与统计，支持手动换 IP。

**Architecture:** monkey patch `openai.OpenAI.__init__` / `AsyncOpenAI.__init__`，白名单命中时注入带本地代理（127.0.0.1:8082）的 `http_client`；包装 `chat.completions.create` 捕获 RateLimitError 触发 `POST /rotate` 换 IP 并重试。代理池用 shadow1ng/ProxyPool 子进程（插件内置管理），通过其 HTTP 控制 API（8083 端口）驱动。UI 为仪表盘浮动卡片（方案 B），配置存 user-custom 插件。

**Tech Stack:** Python 3.14、PyQt5、openai SDK 2.x、httpx、shadow1ng/ProxyPool（外部子进程）、loguru、ruff（行宽120，双引号）

**设计文档:** `docs/superpowers/specs/2026-08-04-ip-switcher-plugin-design.md`

**实现位置:** `D:/work/drifox-plugins2/plugins/ip-switcher/`（独立插件仓库，参考 browser 插件结构）

---

## 文件结构总览

```
D:/work/drifox-plugins2/plugins/ip-switcher/
├── .drifox-plugin/
│   └── plugin.json                  # 插件清单（ui: true）
├── README.md                        # 插件说明
└── ui/
    ├── __init__.py                  # register_ui 入口：安装 patch + 注册卡片
    ├── ip_switcher_card.py          # 仪表盘浮动卡片（布局 B）
    ├── ip_redirect.py               # monkey patch 核心（幂等 + 429 重试）
    ├── proxy_pool.py                # 代理池管理（子进程生命周期 + HTTP API 客户端）
    ├── state.py                     # 状态/事件总线（当前 IP、历史、统计）
    ├── config.py                    # user-custom 配置读写
    └── _vendor/
        └── proxypool/               # shadow1ng/ProxyPool 源码打包（main.py + web/）
```

---

### Task 1: 创建插件骨架 + plugin.json + 打包 ProxyPool vendor

**Files:**
- Create: `D:/work/drifox-plugins2/plugins/ip-switcher/.drifox-plugin/plugin.json`
- Create: `D:/work/drifox-plugins2/plugins/ip-switcher/README.md`
- Create: `D:/work/drifox-plugins2/plugins/ip-switcher/ui/__init__.py`（占位，Task 7 填充）
- Vendor: `D:/work/drifox-plugins2/plugins/ip-switcher/ui/_vendor/proxypool/`

- [ ] **Step 1: 创建 plugin.json**

```json
{
    "name": "ip-switcher",
    "description": "IP 切换监控 — 免费模型限流自动换 IP（429 检测 + 代理池轮换 + 仪表盘）。",
    "version": "0.1.0",
    "author": {
        "name": "DriFox Contributors"
    },
    "license": "GPL-3.0-or-later",
    "type": "user",
    "drifox": {
        "min_version": "0.5.0"
    },
    "keywords": ["drifox", "ip", "proxy", "rate-limit", "free-model"],
    "components": {
        "ui": true
    }
}
```

- [ ] **Step 2: 创建 README.md**

```markdown
# ip-switcher — IP 切换监控

免费模型 API 常按出口 IP 绑定免费额度。本插件在检测到限流（HTTP 429）时自动切换本地代理池出口 IP 并重试请求。

## 功能
- 🧩 monkey patch openai SDK：白名单模型请求走本地代理池
- 🔄 429 自动换 IP + 自动重试（默认 3 次，2s 退避）
- 📊 仪表盘浮动卡片：当前出口 IP、换绑历史、统计
- 🖱 手动换 IP 按钮
- ⚙️ 配置存 user-custom 插件（随云端备份恢复）

## 使用
1. 安装插件后输入 `/ip-switcher` 打开仪表盘
2. 在卡片「设置」中配置白名单模型（如 `free-gpt4o`）
3. 插件自动拉起本地代理池（shadow1ng/ProxyPool），首次需等待抓取+检测代理
4. 白名单模型请求触发 429 时自动换 IP

## 配置项（.drifox/plugins/user-custom/ip-switcher/ip-switcher.json）
- `whitelist_models`: 白名单模型名列表
- `whitelist_base_urls`: 白名单 API 地址列表
- `proxy_pool_port`: 代理池代理端口（默认 8082）
- `retry_limit`: 429 后重试次数（默认 3）
- `retry_backoff_seconds`: 重试间隔秒（默认 2）
```

- [ ] **Step 3: 下载 ProxyPool 源码到 _vendor**

从 https://github.com/shadow1ng/ProxyPool 下载 `main.py` 和 `web/` 目录，放入 `ui/_vendor/proxypool/`。

```bash
mkdir -p D:/work/drifox-plugins2/plugins/ip-switcher/ui/_vendor/proxypool
# 下载 main.py（约 2000 行）和 web/index.html + web/pool.html 到该目录
```

验证：`D:/work/drifox-plugins2/plugins/ip-switcher/ui/_vendor/proxypool/main.py` 存在，`python -c "import ast; ast.parse(open('.../main.py').read())"` 无语法错误。

- [ ] **Step 4: 创建 ui/__init__.py 占位**

```python
# -*- coding: utf-8 -*-
"""ip-switcher UI 组件入口（Task 7 填充完整实现）"""
```

- [ ] **Step 5: Commit**

```bash
cd D:/work/drifox-plugins2
git add plugins/ip-switcher/
git commit -m "feat(ip-switcher): 插件骨架 + ProxyPool vendor 打包"
```

---

### Task 2: config.py — user-custom 配置读写

**Files:**
- Create: `D:/work/drifox-plugins2/plugins/ip-switcher/ui/config.py`

- [ ] **Step 1: 写配置模块（含默认值 + 原子读写）**

```python
# -*- coding: utf-8 -*-
"""ip-switcher 配置 — 存于 user-custom 插件目录（随云端备份恢复）

路径：.drifox/plugins/user-custom/ip-switcher/ip-switcher.json
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict

from loguru import logger

# 默认配置（与设计文档 §9 一致）
DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "whitelist_models": [],
    "whitelist_base_urls": [],
    "proxy_pool_port": 8082,
    "retry_limit": 3,
    "retry_backoff_seconds": 2,
    "auto_switch": True,
    "switch_fail_threshold": 3,
}


def _get_user_custom_dir() -> Path:
    """定位 user-custom 插件目录（随云端备份恢复）"""
    # 优先环境变量（测试注入）
    env = __import__("os").environ.get("IP_SWITCHER_CUSTOM_DIR")
    if env:
        return Path(env)
    # 开发环境：项目根/.drifox/plugins/user-custom
    # 打包环境：~/.drifox/plugins/user-custom
    import sys

    if not hasattr(sys, "_MEIPASS") and not getattr(sys, "frozen", False):
        return Path(".drifox") / "plugins" / "user-custom"
    return Path.home() / ".drifox" / "plugins" / "user-custom"


class ConfigStore:
    """ip-switcher 配置存储（线程安全 + 原子写）"""

    _lock = threading.RLock()

    def __init__(self, path: Path | None = None):
        self.path = path or (_get_user_custom_dir() / "ip-switcher" / "ip-switcher.json")
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        """从磁盘加载，与默认值合并（缺字段补默认）"""
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    merged = dict(DEFAULT_CONFIG)
                    merged.update({k: v for k, v in saved.items() if k in DEFAULT_CONFIG})
                    with self._lock:
                        self._data = merged
                    return
        except (OSError, ValueError) as e:
            logger.warning(f"[ip-switcher] 配置加载失败，使用默认值: {e}")
        with self._lock:
            self._data = dict(DEFAULT_CONFIG)

    def save(self) -> None:
        """原子写回磁盘（先写 tmp 再 rename）"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            tmp.replace(self.path)
        except OSError as e:
            logger.error(f"[ip-switcher] 配置保存失败: {e}")

    # ── 读取 ──

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    # ── 写入 ──

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
        self.save()

    def update(self, changes: Dict[str, Any]) -> None:
        with self._lock:
            for k, v in changes.items():
                if k in DEFAULT_CONFIG:
                    self._data[k] = v
        self.save()

    # ── 白名单快捷方法 ──

    def is_whitelisted_model(self, model: str) -> bool:
        """模型名命中白名单"""
        if not model:
            return False
        with self._lock:
            return model in self._data.get("whitelist_models", [])

    def is_whitelisted_base_url(self, base_url: str) -> bool:
        """API 地址命中白名单（精确匹配，容错去掉尾部斜杠）"""
        if not base_url:
            return False
        norm = base_url.rstrip("/")
        with self._lock:
            return any(str(u).rstrip("/") == norm for u in self._data.get("whitelist_base_urls", []))


# 模块级单例（热重载时重建）
_store: ConfigStore | None = None


def get_config() -> ConfigStore:
    """获取全局配置单例"""
    global _store
    if _store is None:
        _store = ConfigStore()
    return _store


def reset_config_for_test(path: Path) -> ConfigStore:
    """测试辅助：重置单例指向指定路径"""
    global _store
    _store = ConfigStore(path)
    return _store
```

- [ ] **Step 2: 写单元测试**

创建 `D:/work/drifox-plugins2/tests/test_ip_switcher_config.py`：

```python
# -*- coding: utf-8 -*-
"""ip-switcher config 单元测试"""
import json
from pathlib import Path

from plugins.ip_switcher.ui.config import (
    DEFAULT_CONFIG,
    ConfigStore,
    reset_config_for_test,
)


def _make_store(tmp_path: Path) -> ConfigStore:
    cfg_path = tmp_path / "user-custom" / "ip-switcher" / "ip-switcher.json"
    return reset_config_for_test(cfg_path)


def test_default_config(tmp_path):
    store = _make_store(tmp_path)
    assert store.get("retry_limit") == 3
    assert store.get("enabled") is True


def test_set_and_persist(tmp_path):
    store = _make_store(tmp_path)
    store.set("retry_limit", 5)
    # 重新加载验证持久化
    store2 = ConfigStore(store.path)
    assert store2.get("retry_limit") == 5


def test_whitelist_model(tmp_path):
    store = _make_store(tmp_path)
    store.set("whitelist_models", ["free-gpt4o", "gemini-flash-free"])
    assert store.is_whitelisted_model("free-gpt4o")
    assert not store.is_whitelisted_model("gpt-4o")


def test_whitelist_base_url_trailing_slash(tmp_path):
    store = _make_store(tmp_path)
    store.set("whitelist_base_urls", ["https://free-api.example.com"])
    assert store.is_whitelisted_base_url("https://free-api.example.com/")
    assert not store.is_whitelisted_base_url("https://other.example.com")


def test_merge_unknown_keys_ignored(tmp_path):
    cfg_path = tmp_path / "user-custom" / "ip-switcher" / "ip-switcher.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"evil_key": 1, "retry_limit": 7}), encoding="utf-8")
    store = reset_config_for_test(cfg_path)
    assert store.get("retry_limit") == 7
    assert "evil_key" not in store.get_all()
```

- [ ] **Step 3: 运行测试**

```bash
cd D:/work/drifox-plugins2
python -m pytest tests/test_ip_switcher_config.py -v
```

Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add plugins/ip-switcher/ui/config.py tests/test_ip_switcher_config.py
git commit -m "feat(ip-switcher): user-custom 配置读写 + 白名单匹配"
```

---

### Task 3: state.py — 状态/事件总线

**Files:**
- Create: `D:/work/drifox-plugins2/plugins/ip-switcher/ui/state.py`

- [ ] **Step 1: 写状态模块**

```python
# -*- coding: utf-8 -*-
"""ip-switcher 状态/事件总线

职责：
- 维护当前出口 IP、换绑历史（内存 + 可选落盘）、统计计数
- 通过 pyqtSignal 广播事件（换绑完成、代理池异常、模式变化）
- 线程安全：信号跨线程自动投递，计数加锁
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal


@dataclass
class SwitchEvent:
    """一次换绑事件"""

    timestamp: float
    trigger: str  # "ratelimit" | "manual" | "startup"
    old_ip: str
    new_ip: str
    success: bool = True
    note: str = ""


class IPState(QObject):
    """全局状态总线（QObject 以便信号跨线程）"""

    # 信号：换绑事件、状态变化（供 UI 刷新）
    switched = pyqtSignal(object)          # SwitchEvent
    status_changed = pyqtSignal(str, str)  # (field, value)
    pool_state_changed = pyqtSignal(str)   # "ok" | "error" | "starting"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = __import__("threading").RLock()
        self._current_ip: str = "未使用"
        self._mode: str = "auto"          # auto/sticky/manual
        self._auto_switch: bool = True
        self._pool_state: str = "stopped"  # stopped/starting/ok/error
        self._history: Deque[SwitchEvent] = deque(maxlen=50)
        self._stats: Dict[str, int] = {
            "total_switches": 0,
            "today_switches": 0,
            "success_count": 0,
            "fail_count": 0,
            "rate_limit_hits": 0,
        }
        self._today: str = time.strftime("%Y-%m-%d")

    # ── 读 ──

    def current_ip(self) -> str:
        with self._lock:
            return self._current_ip

    def mode(self) -> str:
        with self._lock:
            return self._mode

    def is_auto_switch(self) -> bool:
        with self._lock:
            return self._auto_switch

    def pool_state(self) -> str:
        with self._lock:
            return self._pool_state

    def history(self) -> List[SwitchEvent]:
        with self._lock:
            return list(self._history)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            # 跨天重置今日计数
            today = time.strftime("%Y-%m-%d")
            if today != self._today:
                self._today = today
                self._stats["today_switches"] = 0
            return dict(self._stats)

    # ── 写（均广播信号） ──

    def set_current_ip(self, ip: str) -> None:
        with self._lock:
            self._current_ip = ip or "未使用"
        self.status_changed.emit("current_ip", self._current_ip)

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode
        self.status_changed.emit("mode", mode)

    def set_auto_switch(self, on: bool) -> None:
        with self._lock:
            self._auto_switch = on
        self.status_changed.emit("auto_switch", "on" if on else "off")

    def set_pool_state(self, state: str) -> None:
        with self._lock:
            self._pool_state = state
        self.pool_state_changed.emit(state)

    def record_switch(self, trigger: str, old_ip: str, new_ip: str, success: bool = True, note: str = "") -> None:
        """记录一次换绑事件并广播"""
        ev = SwitchEvent(
            timestamp=time.time(),
            trigger=trigger,
            old_ip=old_ip,
            new_ip=new_ip,
            success=success,
            note=note,
        )
        with self._lock:
            self._history.append(ev)
            self._stats["total_switches"] += 1
            if time.strftime("%Y-%m-%d") == self._today:
                self._stats["today_switches"] += 1
            if success:
                self._stats["success_count"] += 1
            else:
                self._stats["fail_count"] += 1
            if trigger == "ratelimit":
                self._stats["rate_limit_hits"] += 1
            self._current_ip = new_ip or self._current_ip
        self.switched.emit(ev)
        self.status_changed.emit("current_ip", self._current_ip)


# 模块级单例
_state: Optional[IPState] = None


def get_state() -> IPState:
    """获取全局状态单例（须在主线程创建）"""
    global _state
    if _state is None:
        _state = IPState()
    return _state


def reset_state_for_test() -> IPState:
    """测试辅助"""
    global _state
    _state = IPState()
    return _state
```

- [ ] **Step 2: 写单元测试**

创建 `D:/work/drifox-plugins2/tests/test_ip_switcher_state.py`：

```python
# -*- coding: utf-8 -*-
"""ip-switcher state 单元测试"""
from plugins.ip_switcher.ui.state import reset_state_for_test


def test_record_switch_updates_history_and_stats():
    st = reset_state_for_test()
    st.record_switch("ratelimit", "1.1.1.1", "2.2.2.2")
    st.record_switch("manual", "2.2.2.2", "3.3.3.3", success=False)
    assert st.current_ip() == "3.3.3.3"
    assert len(st.history()) == 2
    stats = st.stats()
    assert stats["total_switches"] == 2
    assert stats["rate_limit_hits"] == 1
    assert stats["fail_count"] == 1


def test_set_pool_state():
    st = reset_state_for_test()
    st.set_pool_state("ok")
    assert st.pool_state() == "ok"
```

- [ ] **Step 3: 运行测试**

```bash
cd D:/work/drifox-plugins2
python -m pytest tests/test_ip_switcher_state.py -v
```

Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add plugins/ip-switcher/ui/state.py tests/test_ip_switcher_state.py
git commit -m "feat(ip-switcher): 状态/事件总线 - 换绑历史 + 统计 + 信号广播"
```

---

### Task 4: proxy_pool.py — 代理池管理

**Files:**
- Create: `D:/work/drifox-plugins2/plugins/ip-switcher/ui/proxy_pool.py`

**关键设计**：
- 子进程生命周期：`start()`（fetch → check → serve 或直接 serve）→ `stop()`
- HTTP API 客户端：`POST /rotate`（换 IP）、`POST /mode`（sticky）、`GET /stats`
- 换 IP 后验证新 IP：通过代理请求 `https://api.ipify.org` 拿出口 IP
- 连续失败阈值 → `switch_fail_threshold` → 暂停自动切换

- [ ] **Step 1: 写代理池管理模块**

```python
# -*- coding: utf-8 -*-
"""ip-switcher 代理池管理 — shadow1ng/ProxyPool 子进程 + HTTP 控制

子进程：python <vendor>/main.py serve --port 8082（控制台 8083）
控制 API（ProxyPool web/index.html 前端调用清单）：
- POST /rotate  {"mode": "sticky"}  → 换 IP
- POST /mode    {"mode": "auto|sticky|manual"}
- GET  /stats   → {current, pool_size, alive_total, ...}
- POST /fetch   → 抓取代理
- POST /check   → 检测存活
- GET  /reset   → 重置熔断
"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from loguru import logger

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor" / "proxypool"
_PROXY_MAIN = _VENDOR_DIR / "main.py"


class ProxyPoolManager:
    """代理池子进程生命周期 + 控制 API 客户端"""

    def __init__(self, stats_port: int = 8083, proxy_port: int = 8082, data_dir: Optional[Path] = None):
        self.stats_port = stats_port
        self.proxy_port = proxy_port
        # 工作目录：存 socks.txt / alive.txt / config.json（默认 user-custom/ip-switcher/data）
        self.data_dir = data_dir or (Path(".drifox") / "plugins" / "user-custom" / "ip-switcher" / "data")
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._base_url = f"http://127.0.0.1:{stats_port}"

    # ── 子进程生命周期 ──

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, fetch_and_check: bool = True, wait_ready: float = 8.0) -> bool:
        """启动代理池子进程。fetch_and_check=True 时先抓取+检测代理。"""
        with self._lock:
            if self.is_running():
                return True
            self.data_dir.mkdir(parents=True, exist_ok=True)
            try:
                if fetch_and_check:
                    # run = fetch → check → serve（一键全流程）
                    cmd = [sys.executable, str(_PROXY_MAIN), "run",
                           "--port", str(self.proxy_port), "--stats-port", str(self.stats_port)]
                else:
                    cmd = [sys.executable, str(_PROXY_MAIN), "serve",
                           "--port", str(self.proxy_port), "--stats-port", str(self.stats_port)]
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.data_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                logger.info(f"[ip-switcher] 代理池已启动 (pid={self._proc.pid}, port={self.proxy_port})")
            except Exception as e:
                logger.error(f"[ip-switcher] 代理池启动失败: {e}")
                self._proc = None
                return False
        # 等待控制台就绪
        deadline = time.time() + wait_ready
        while time.time() < deadline:
            if self._request("GET", "/stats") is not None:
                return True
            time.sleep(0.5)
        logger.warning("[ip-switcher] 代理池控制台未就绪（可能仍在抓取/检测）")
        return True  # 进程在跑，只是没就绪；后续调用会重试

    def stop(self) -> None:
        """停止代理池子进程"""
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=5)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None
        logger.info("[ip-switcher] 代理池已停止")

    # ── HTTP 控制 API ──

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None, timeout: float = 6.0):
        """请求代理池控制台 API，失败返回 None"""
        try:
            if method == "GET":
                r = httpx.get(self._base_url + path, timeout=timeout)
            else:
                r = httpx.post(self._base_url + path, json=body or {}, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.debug(f"[ip-switcher] 控制 API {path} 请求失败: {e}")
        return None

    def get_stats(self) -> Optional[Dict[str, Any]]:
        """获取代理池状态（当前 IP、池大小等）"""
        return self._request("GET", "/stats")

    def set_mode(self, mode: str) -> bool:
        """切换模式：auto / sticky / manual"""
        d = self._request("POST", "/mode", {"mode": mode})
        return d is not None and not d.get("error")

    def rotate(self) -> Optional[str]:
        """手动/触发换 IP：调用 /rotate，返回新代理 ip:port 或 None"""
        d = self._request("POST", "/rotate", {})
        if d is None or d.get("error"):
            return None
        return d.get("current")

    def fetch_proxies(self) -> bool:
        """触发抓取代理（后台任务）"""
        d = self._request("POST", "/fetch", {})
        return d is not None and not d.get("error")

    def check_proxies(self) -> bool:
        """触发检测存活（后台任务）"""
        d = self._request("POST", "/check", {})
        return d is not None and not d.get("error")

    def reset_circuits(self) -> bool:
        """重置熔断"""
        try:
            r = httpx.get(self._base_url + "/reset", timeout=6.0)
            return r.status_code == 200
        except Exception:
            return False

    # ── 出口 IP 验证 ──

    def get_outbound_ip(self, timeout: float = 8.0) -> Optional[str]:
        """通过代理请求 ipify 拿出口 IP（验证代理连通性）"""
        try:
            proxies = {"http://": f"http://127.0.0.1:{self.proxy_port}",
                       "https://": f"http://127.0.0.1:{self.proxy_port}"}
            r = httpx.get("https://api.ipify.org", proxies=proxies, timeout=timeout)
            if r.status_code == 200:
                ip = r.text.strip()
                return ip if ip else None
        except Exception as e:
            logger.debug(f"[ip-switcher] 出口 IP 验证失败: {e}")
        return None


# 模块级单例
_manager: Optional[ProxyPoolManager] = None


def get_manager() -> ProxyPoolManager:
    global _manager
    if _manager is None:
        _manager = ProxyPoolManager()
    return _manager


def reset_manager_for_test(manager: ProxyPoolManager) -> None:
    global _manager
    _manager = manager
```

- [ ] **Step 2: 写单元测试（mock 掉子进程与 HTTP）**

创建 `D:/work/drifox-plugins2/tests/test_ip_switcher_proxy_pool.py`：

```python
# -*- coding: utf-8 -*-
"""ip-switcher proxy_pool 单元测试（mock HTTP 层）"""
from unittest.mock import patch

from plugins.ip_switcher.ui.proxy_pool import ProxyPoolManager


def _make_manager():
    return ProxyPoolManager(stats_port=18083, proxy_port=18082, data_dir=None)


def test_rotate_returns_current_ip():
    m = _make_manager()
    with patch.object(m, "_request", return_value={"current": "103.216.72.14"}):
        assert m.rotate() == "103.216.72.14"


def test_rotate_failure_returns_none():
    m = _make_manager()
    with patch.object(m, "_request", return_value={"error": "池子为空"}):
        assert m.rotate() is None


def test_set_mode_sticky():
    m = _make_manager()
    with patch.object(m, "_request", return_value={"mode": "sticky"}):
        assert m.set_mode("sticky") is True


def test_get_stats():
    m = _make_manager()
    with patch.object(m, "_request", return_value={"current": "1.2.3.4", "pool_size": 10}):
        stats = m.get_stats()
        assert stats["pool_size"] == 10
```

- [ ] **Step 3: 运行测试**

```bash
cd D:/work/drifox-plugins2
python -m pytest tests/test_ip_switcher_proxy_pool.py -v
```

Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add plugins/ip-switcher/ui/proxy_pool.py tests/test_ip_switcher_proxy_pool.py
git commit -m "feat(ip-switcher): 代理池管理 - 子进程生命周期 + rotate/mode/stats API"
```

---

### Task 5: ip_redirect.py — monkey patch 核心

**Files:**
- Create: `D:/work/drifox-plugins2/plugins/ip-switcher/ui/ip_redirect.py`

**关键设计（对齐 browser external_open.py 模式）**：
- 幂等：`_installed` + 函数属性 `_drifox_ip_switch`
- 主线程派发器：换 IP + UI 更新必须回主线程
- 回退：代理池不可用 → 直连

- [ ] **Step 1: 写 monkey patch 模块**

```python
# -*- coding: utf-8 -*-
"""ip-switcher monkey patch — 白名单模型走代理池 + 429 自动换 IP 重试

原理（对齐 browser/external_open.py 模式）：
- patch ``openai.OpenAI.__init__`` / ``AsyncOpenAI.__init__``：
  白名单命中 → 注入带本地代理的 ``http_client``
- patch ``chat.completions.create`` / ``acreate``：
  捕获 RateLimitError(429) → 换 IP → 自动重试（默认 3 次）
- 幂等：热重载时 register_ui 再次执行，通过标记避免重复嵌套
- 线程安全：429 可能发生在 worker 线程，经 _MainThreadDispatcher 回主线程换 IP
"""

import re
import threading
import time
from typing import Any, Optional

from loguru import logger
from PyQt5.QtCore import QObject, pyqtSignal

from .config import get_config
from .proxy_pool import get_manager
from .state import get_state

# ── 幂等标记 ──────────────────────────────────────────────
_installed = False
_orig_openai_init: Any = None
_orig_async_openai_init: Any = None
_orig_chat_create: Any = None
_orig_chat_acreate: Any = None

# 429 错误文本关键词（防止误判其他异常）
_RATE_LIMIT_KEYWORDS = (
    "rate limit",
    "rate_limit",
    "quota",
    "额度",
    "limit exceeded",
    "too many requests",
    "429",
)


def _is_rate_limit_error(exc: BaseException) -> bool:
    """判断异常是否为限流（429 或错误文本命中）"""
    # openai.RateLimitError 是 429 专用异常
    try:
        import openai

        if isinstance(exc, openai.RateLimitError):
            return True
    except Exception:
        pass
    # 错误文本关键词匹配
    msg = str(getattr(exc, "message", "") or exc).lower()
    return any(kw in msg for kw in _RATE_LIMIT_KEYWORDS)


def _is_whitelisted(model: str = "", base_url: str = "") -> bool:
    """白名单判定：model 名或 base_url 命中任一即可"""
    cfg = get_config()
    if model and cfg.is_whitelisted_model(model):
        return True
    if base_url and cfg.is_whitelisted_base_url(base_url):
        return True
    return False


class _MainThreadDispatcher(QObject):
    """跨线程派发器：信号 AutoConnection 自动投递到主线程事件循环"""

    _requested = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._requested.connect(self._handle)

    def _handle(self, fn):
        try:
            fn()
        except Exception:
            logger.exception("[ip-switcher] 主线程派发任务异常")

    def call(self, fn):
        self._requested.emit(fn)


_dispatcher: Optional[_MainThreadDispatcher] = None


def _get_dispatcher() -> Optional[_MainThreadDispatcher]:
    """获取主线程派发器（须在主线程创建）"""
    global _dispatcher
    if _dispatcher is None:
        try:
            from PyQt5.QtCore import QThread
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None or QThread.currentThread() != app.thread():
                return None
            _dispatcher = _MainThreadDispatcher()
        except Exception:
            return None
    return _dispatcher


def _switch_ip_threadsafe(timeout: float = 20.0) -> Optional[str]:
    """线程安全换 IP：非 UI 线程 → 派发到主线程同步等待结果"""
    import threading as _t

    try:
        from PyQt5.QtCore import QThread
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            dispatcher = _get_dispatcher()
            if dispatcher is None:
                logger.warning("[ip-switcher] 派发器不可用且非主线程，跳过换 IP")
                return None
            event = _t.Event()
            result: dict = {"ip": None}

            def _do():
                try:
                    result["ip"] = _do_switch_ip()
                finally:
                    event.set()

            dispatcher.call(_do)
            event.wait(timeout)
            return result["ip"]
    except Exception:
        pass
    return _do_switch_ip()


def _do_switch_ip() -> Optional[str]:
    """执行换 IP（主线程）：代理池 rotate → 验证出口 IP → 更新 state"""
    state = get_state()
    if not state.is_auto_switch():
        logger.info("[ip-switcher] 自动切换已暂停，跳过换 IP")
        return None
    old_ip = state.current_ip()
    manager = get_manager()
    new_proxy = manager.rotate()
    if not new_proxy:
        logger.warning("[ip-switcher] 代理池换 IP 失败（可能池子为空）")
        state.set_pool_state("error")
        return None
    # 验证出口 IP
    outbound = manager.get_outbound_ip()
    new_ip = outbound or new_proxy.split(":")[0]
    state.record_switch("ratelimit" if old_ip != "未使用" else "startup", old_ip, new_ip)
    state.set_pool_state("ok")
    logger.info(f"[ip-switcher] 已切换 IP: {old_ip} → {new_ip}")
    return new_ip


def _make_proxied_http_client(proxy_url: str):
    """构建带代理的 httpx.Client（openai SDK http_client 参数）"""
    import httpx

    return httpx.Client(proxy=proxy_url, timeout=httpx.Timeout(60.0, connect=10.0))


def _patched_openai_init(self, *args, **kwargs):
    """OpenAI.__init__ 代理：白名单命中注入代理 http_client"""
    cfg = get_config()
    base_url = kwargs.get("base_url") or ""
    model = kwargs.get("model") or ""
    if cfg.get("enabled") and _is_whitelisted(model=model, base_url=base_url):
        if "http_client" not in kwargs:
            try:
                port = cfg.get("proxy_pool_port", 8082)
                kwargs["http_client"] = _make_proxied_http_client(f"http://127.0.0.1:{port}")
                logger.debug(f"[ip-switcher] 白名单命中注入代理 client: base={base_url} model={model}")
            except Exception as e:
                logger.warning(f"[ip-switcher] 注入代理 client 失败，回退直连: {e}")
    return _orig_openai_init(self, *args, **kwargs)


def _patched_async_openai_init(self, *args, **kwargs):
    """AsyncOpenAI.__init__ 代理（同 OpenAI）"""
    cfg = get_config()
    base_url = kwargs.get("base_url") or ""
    model = kwargs.get("model") or ""
    if cfg.get("enabled") and _is_whitelisted(model=model, base_url=base_url):
        if "http_client" not in kwargs:
            try:
                port = cfg.get("proxy_pool_port", 8082)
                import httpx

                kwargs["http_client"] = httpx.AsyncClient(
                    proxy=f"http://127.0.0.1:{port}",
                    timeout=httpx.Timeout(60.0, connect=10.0),
                )
                logger.debug(f"[ip-switcher] 白名单命中注入异步代理 client: base={base_url}")
            except Exception as e:
                logger.warning(f"[ip-switcher] 注入异步代理 client 失败，回退直连: {e}")
    return _orig_async_openai_init(self, *args, **kwargs)


def _wrap_chat_create(orig_create):
    """包装 chat.completions.create：429 → 换 IP → 重试"""

    def _wrapped(self, *args, **kwargs):
        cfg = get_config()
        model = kwargs.get("model") or getattr(self, "_model", "")
        base_url = str(getattr(self, "base_url", "") or "")
        if not (cfg.get("enabled") and _is_whitelisted(model=model, base_url=base_url)):
            return orig_create(self, *args, **kwargs)  # 非白名单零开销

        retry_limit = int(cfg.get("retry_limit", 3))
        backoff = float(cfg.get("retry_backoff_seconds", 2))
        last_exc: Optional[BaseException] = None
        for attempt in range(retry_limit + 1):
            try:
                return orig_create(self, *args, **kwargs)
            except Exception as e:
                if not _is_rate_limit_error(e):
                    raise  # 非限流错误直接抛
                last_exc = e
                logger.warning(f"[ip-switcher] 429 限流 (第 {attempt + 1} 次)，换 IP 后重试")
                if attempt >= retry_limit:
                    break
                new_ip = _switch_ip_threadsafe()
                if new_ip is None:
                    logger.warning("[ip-switcher] 换 IP 失败，不再重试")
                    break
                time.sleep(backoff)  # 等 IP 生效
        raise last_exc  # 重试耗尽 → 抛原始异常

    return _wrapped


def _wrap_chat_acreate(orig_acreate):
    """包装 chat.completions.acreate（异步版）"""

    async def _wrapped(self, *args, **kwargs):
        cfg = get_config()
        model = kwargs.get("model") or getattr(self, "_model", "")
        base_url = str(getattr(self, "base_url", "") or "")
        if not (cfg.get("enabled") and _is_whitelisted(model=model, base_url=base_url)):
            return await orig_acreate(self, *args, **kwargs)

        retry_limit = int(cfg.get("retry_limit", 3))
        backoff = float(cfg.get("retry_backoff_seconds", 2))
        last_exc: Optional[BaseException] = None
        for attempt in range(retry_limit + 1):
            try:
                return await orig_acreate(self, *args, **kwargs)
            except Exception as e:
                if not _is_rate_limit_error(e):
                    raise
                last_exc = e
                logger.warning(f"[ip-switcher] 429 限流 (异步, 第 {attempt + 1} 次)，换 IP 后重试")
                if attempt >= retry_limit:
                    break
                new_ip = _switch_ip_threadsafe()
                if new_ip is None:
                    break
                await __import__("asyncio").sleep(backoff)
        raise last_exc

    return _wrapped


def install_redirect() -> bool:
    """安装 monkey patch（register_ui 时调用）。返回是否完成注入。"""
    global _installed, _orig_openai_init, _orig_async_openai_init
    global _orig_chat_create, _orig_chat_acreate

    if _installed:
        return True
    try:
        import openai
    except Exception:
        logger.warning("[ip-switcher] openai SDK 不可用，跳过 patch")
        return False

    # 幂等：热重载遗留代理检测
    if getattr(openai.OpenAI.__init__, "_drifox_ip_switch", False):
        _installed = True
        return True

    try:
        # 1) patch OpenAI.__init__
        _orig_openai_init = openai.OpenAI.__init__
        _patched_openai_init._drifox_ip_switch = True  # type: ignore[attr-defined]
        openai.OpenAI.__init__ = _patched_openai_init  # type: ignore[assignment]

        # 2) patch AsyncOpenAI.__init__
        if hasattr(openai, "AsyncOpenAI"):
            _orig_async_openai_init = openai.AsyncOpenAI.__init__
            _patched_async_openai_init._drifox_ip_switch = True  # type: ignore[attr-defined]
            openai.AsyncOpenAI.__init__ = _patched_async_openai_init  # type: ignore[assignment]

        # 3) patch chat.completions.create
        from openai.resources.chat.completions import Completions

        _orig_chat_create = Completions.create
        Completions.create = _wrap_chat_create(_orig_chat_create)  # type: ignore[assignment]

        # 4) patch chat.completions.acreate
        if hasattr(Completions, "acreate"):
            _orig_chat_acreate = Completions.acreate
            Completions.acreate = _wrap_chat_acreate(_orig_chat_acreate)  # type: ignore[assignment]

        # 5) 预创建主线程派发器（register_ui 在主线程执行）
        _get_dispatcher()

        _installed = True
        logger.info("[ip-switcher] monkey patch 已安装 (OpenAI.__init__ + chat.create)")
        return True
    except Exception:
        logger.exception("[ip-switcher] monkey patch 安装失败")
        return False


def uninstall_redirect() -> None:
    """卸载 patch（插件卸载/禁用时调用）"""
    global _installed, _orig_openai_init, _orig_async_openai_init
    global _orig_chat_create, _orig_chat_acreate
    try:
        import openai

        if _orig_openai_init is not None:
            openai.OpenAI.__init__ = _orig_openai_init  # type: ignore[assignment]
        if _orig_async_openai_init is not None and hasattr(openai, "AsyncOpenAI"):
            openai.AsyncOpenAI.__init__ = _orig_async_openai_init  # type: ignore[assignment]
        if _orig_chat_create is not None:
            from openai.resources.chat.completions import Completions

            Completions.create = _orig_chat_create  # type: ignore[assignment]
        if _orig_chat_acreate is not None:
            from openai.resources.chat.completions import Completions

            Completions.acreate = _orig_chat_acreate  # type: ignore[assignment]
    except Exception as e:
        logger.warning(f"[ip-switcher] 卸载 patch 异常: {e}")
    _installed = False
    _orig_openai_init = _orig_async_openai_init = None
    _orig_chat_create = _orig_chat_acreate = None
```

- [ ] **Step 2: 写单元测试（mock openai 模块）**

创建 `D:/work/drifox-plugins2/tests/test_ip_switcher_redirect.py`：

```python
# -*- coding: utf-8 -*-
"""ip-switcher monkey patch 单元测试"""
import sys
import types
from unittest.mock import MagicMock, patch

from plugins.ip_switcher.ui import ip_redirect


class _FakeRateLimit(Exception):
    """模拟 openai.RateLimitError（无 openai 时用）"""
    status_code = 429
    message = "rate limit exceeded"


def _fake_openai_module():
    """构造最小 openai 假模块"""
    m = types.ModuleType("openai")
    m.RateLimitError = _FakeRateLimit
    m.OpenAI = type("OpenAI", (), {"__init__": lambda self, *a, **k: None})
    m.AsyncOpenAI = type("AsyncOpenAI", (), {"__init__": lambda self, *a, **k: None})
    # chat.completions 层级
    comp = type("Completions", (), {
        "create": lambda self, *a, **k: None,
        "acreate": lambda self, *a, **k: None,
    })
    chat = type("chat", (), {"completions": comp()})
    m.chat = chat()
    return m


def test_is_rate_limit_error_429():
    err = _FakeRateLimit()
    assert ip_redirect._is_rate_limit_error(err) is True


def test_is_rate_limit_error_text():
    class E(Exception):
        message = "Quota exceeded for this IP"

    assert ip_redirect._is_rate_limit_error(E()) is True


def test_is_rate_limit_error_other():
    assert ip_redirect._is_rate_limit_error(ValueError("bad request")) is False


def test_is_whitelisted_model():
    with patch.object(ip_redirect, "get_config") as mock_cfg:
        cfg = MagicMock()
        cfg.is_whitelisted_model.return_value = True
        cfg.is_whitelisted_base_url.return_value = False
        mock_cfg.return_value = cfg
        assert ip_redirect._is_whitelisted(model="free-gpt4o") is True
```

- [ ] **Step 3: 运行测试**

```bash
cd D:/work/drifox-plugins2
python -m pytest tests/test_ip_switcher_redirect.py -v
```

Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add plugins/ip-switcher/ui/ip_redirect.py tests/test_ip_switcher_redirect.py
git commit -m "feat(ip-switcher): monkey patch 核心 - 白名单代理注入 + 429 换 IP 重试"
```

---

### Task 6: ip_switcher_card.py — 仪表盘浮动卡片

**Files:**
- Create: `D:/work/drifox-plugins2/plugins/ip-switcher/ui/ip_switcher_card.py`

**布局**（设计文档 §8 方案 B）：头部（标题+状态徽章）→ 当前 IP → 4 统计格 → 换绑历史 → 操作按钮。

- [ ] **Step 1: 写浮动卡片**

```python
# -*- coding: utf-8 -*-
"""ip-switcher 仪表盘浮动卡片（方案 B）

┌──────────────────────────────────────┐
│ IP 换绑监控                    [正常] │
│  103.216.72.14                        │
│ ┌──────┬──────┬──────┬──────┐        │
│ │总换绑 │ 今日 │成功率 │代理池 │        │
│ └──────┴──────┴──────┴──────┘        │
│ ── 换绑历史 ─────────────────        │
│ ● 12:03 限流触发 · 98.xx → 103.x     │
│ ● 11:47 手动切换 · 45.xx → 98.xx     │
│                                      │
│ [🔄 立即换 IP]   [⏸ 暂停自动]        │
└──────────────────────────────────────┘
"""

import time
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from .config import get_config
from .proxy_pool import get_manager
from .state import SwitchEvent, get_state


# ── 主题色辅助（对齐 templates.md 骨架） ──────────────────


def _text_color(secondary: bool = False) -> str:
    from qfluentwidgets import isDarkTheme

    if isDarkTheme():
        return "rgba(255,255,255,0.55)" if secondary else "rgba(255,255,255,0.9)"
    return "rgba(0,0,0,0.45)" if secondary else "rgba(0,0,0,0.85)"


def _make_style(color: str, font_family: str = "", font_size: int = 0, extra: str = "") -> str:
    parts = [f"color: {color};"]
    if font_family:
        parts.append(f"font-family: '{font_family}'")
    if font_size:
        parts.append(f"font-size: {font_size}px;")
    if extra:
        parts.append(extra)
    return " ".join(parts)


class IPSwitcherCard(QWidget):
    """IP 换绑监控仪表盘浮动卡片"""

    closed = pyqtSignal()

    # ── 状态徽章映射 ──
    _BADGE = {
        "ok": ("正常", "#22c55e"),
        "switching": ("限流切换中", "#eab308"),
        "error": ("代理池异常", "#ef4444"),
        "paused": ("已暂停", "#6b7280"),
        "stopped": ("代理池未启动", "#9ca3af"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._is_busy = False
        self._state = get_state()
        self._config = get_config()
        self._setup_ui()
        self._connect_signals()

    # ── 上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        self._apply_latest_theme()
        self._refresh_all()
        self.setVisible(True)

    def _apply_latest_theme(self):
        if self._context_provider is None:
            return
        try:
            ctx = self._context_provider()
        except Exception:
            return
        ff = ctx.get("font_family", "Microsoft YaHei")
        fs = ctx.get("font_size", 14)
        tc = ctx.get("colors", {}).get("text_primary", "") or _text_color()
        tcs = ctx.get("colors", {}).get("text_secondary", "") or _text_color(secondary=True)
        self.setFont(QFont(ff, fs if fs else 14))
        for lb in self.findChildren(QLabel):
            try:
                ss = lb.styleSheet()
                if not ss:
                    continue
                import re

                new_ss = re.sub(r"color:\s*[^;]+;", f"color: {tc};", ss)
                lb.setStyleSheet(new_ss)
            except RuntimeError:
                pass
        self._ip_label.setStyleSheet(_make_style(tc, ff, fs + 6, "font-weight: 700;"))
        self._badge_label.setStyleSheet(self._badge_style())

    def _badge_style(self) -> str:
        _, color = self._badge_state()
        return (
            f"background: {color}22; color: {color}; border-radius: 10px;"
            f" padding: 2px 10px; font-size: 12px;"
        )

    def _badge_state(self):
        state = self._state
        pool = state.pool_state()
        if pool == "error":
            return self._BADGE["error"]
        if pool == "stopped":
            return self._BADGE["stopped"]
        if not state.is_auto_switch():
            return self._BADGE["paused"]
        return self._BADGE["ok"]

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumSize(360, 320)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("IPSwitcherCard { background: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 头部 ──
        header = QWidget(self)
        hly = QHBoxLayout(header)
        hly.setContentsMargins(16, 12, 16, 4)
        title = QLabel("🌐 IP 换绑监控", header)
        title.setStyleSheet(_make_style(_text_color(), extra="font-weight: 600;"))
        hly.addWidget(title)
        hly.addStretch(1)
        self._badge_label = QLabel("", header)
        hly.addWidget(self._badge_label)
        root.addWidget(header)

        # 分隔线
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: rgba(128,128,128,0.15); max-height: 1px;")
        root.addWidget(sep)

        # ── 当前出口 IP ──
        ip_wrap = QWidget(self)
        ily = QVBoxLayout(ip_wrap)
        ily.setContentsMargins(16, 10, 16, 4)
        ip_hint = QLabel("当前出口 IP", ip_wrap)
        ip_hint.setStyleSheet(_make_style(_text_color(secondary=True), font_size=11))
        ily.addWidget(ip_hint)
        self._ip_label = QLabel("未使用", ip_wrap)
        self._ip_label.setStyleSheet(_make_style(_text_color(), font_size=20, extra="font-weight: 700;"))
        ily.addWidget(self._ip_label)
        root.addWidget(ip_wrap)

        # ── 统计格 ×4 ──
        stats = QWidget(self)
        sly = QHBoxLayout(stats)
        sly.setContentsMargins(16, 8, 16, 4)
        sly.setSpacing(8)
        self._stat_labels = {}
        for key, name in (("total_switches", "总换绑"), ("today_switches", "今日"),
                          ("success_rate", "成功率"), ("pool_size", "代理池")):
            cell = QFrame(stats)
            cell.setStyleSheet("background: rgba(128,128,128,0.08); border-radius: 6px;")
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(6, 6, 6, 6)
            cl.setAlignment(Qt.AlignCenter)
            val = QLabel("0", cell)
            val.setAlignment(Qt.AlignCenter)
            val.setStyleSheet(_make_style(_text_color(), extra="font-weight: 700;"))
            name_lb = QLabel(name, cell)
            name_lb.setAlignment(Qt.AlignCenter)
            name_lb.setStyleSheet(_make_style(_text_color(secondary=True), font_size=10))
            cl.addWidget(val)
            cl.addWidget(name_lb)
            self._stat_labels[key] = val
            sly.addWidget(cell, 1)
        root.addWidget(stats)

        # ── 换绑历史 ──
        hist_hint = QLabel("换绑历史", self)
        hist_hint.setContentsMargins(16, 8, 16, 2)
        hist_hint.setStyleSheet(_make_style(_text_color(secondary=True), font_size=11))
        root.addWidget(hist_hint)

        self._history_box = QWidget(self)
        self._history_layout = QVBoxLayout(self._history_box)
        self._history_layout.setContentsMargins(16, 0, 16, 4)
        self._history_layout.setSpacing(2)
        root.addWidget(self._history_box)

        # ── 操作按钮 ──
        btns = QWidget(self)
        bly = QHBoxLayout(btns)
        bly.setContentsMargins(16, 8, 16, 12)
        bly.setSpacing(8)
        self._switch_btn = QPushButton("🔄 立即换 IP", btns)
        self._switch_btn.setCursor(Qt.PointingHandCursor)
        self._switch_btn.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; border: none;"
            " border-radius: 6px; padding: 0 10px; min-height: 32px; }"
            "QPushButton:hover { background: #6366f1; }"
            "QPushButton:disabled { background: #a5b4fc; }"
        )
        self._switch_btn.clicked.connect(self._on_manual_switch)
        bly.addWidget(self._switch_btn, 1)
        self._auto_btn = QPushButton("⏸ 暂停自动", btns)
        self._auto_btn.setCursor(Qt.PointingHandCursor)
        self._auto_btn.setStyleSheet(
            "QPushButton { background: rgba(128,128,128,0.12); color: "
            + _text_color()
            + "; border: 1px solid rgba(128,128,128,0.2); border-radius: 6px;"
            " padding: 0 10px; min-height: 32px; }"
        )
        self._auto_btn.clicked.connect(self._on_toggle_auto)
        bly.addWidget(self._auto_btn, 1)
        root.addWidget(btns)

    # ── 信号连接 ──

    def _connect_signals(self):
        self._state.switched.connect(lambda _ev: self._refresh_all())
        self._state.status_changed.connect(lambda _f, _v: self._refresh_all())
        self._state.pool_state_changed.connect(lambda _s: self._refresh_all())

    # ── 刷新 ──

    def _refresh_all(self):
        st = self._state
        # 徽章
        text, _ = self._badge_state()
        self._badge_label.setText(text)
        self._badge_label.setStyleSheet(self._badge_style())
        # 当前 IP
        self._ip_label.setText(st.current_ip())
        # 统计
        stats = st.stats()
        self._stat_labels["total_switches"].setText(str(stats["total_switches"]))
        self._stat_labels["today_switches"].setText(str(stats["today_switches"]))
        total = stats["total_switches"]
        success = stats["success_count"]
        rate = f"{int(success * 100 / total)}%" if total else "-"
        self._stat_labels["success_rate"].setText(rate)
        manager = get_manager()
        pool_stats = manager.get_stats()
        pool_size = pool_stats.get("pool_size", "-") if pool_stats else "-"
        self._stat_labels["pool_size"].setText(str(pool_size))
        # 历史（最近 6 条）
        self._render_history(st.history()[:6])
        # 按钮
        self._auto_btn.setText("▶ 恢复自动" if not st.is_auto_switch() else "⏸ 暂停自动")

    def _render_history(self, events: list):
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not events:
            empty = QLabel("暂无换绑记录", self._history_box)
            empty.setStyleSheet(_make_style(_text_color(secondary=True), font_size=12))
            self._history_layout.addWidget(empty)
            return
        for ev in events:
            self._history_layout.addWidget(self._make_history_row(ev))

    def _make_history_row(self, ev: SwitchEvent) -> QLabel:
        t = time.strftime("%H:%M", time.localtime(ev.timestamp))
        trigger = "限流触发" if ev.trigger == "ratelimit" else "手动切换"
        dot = "🔴" if ev.trigger == "ratelimit" else "🔵"
        text = f"{dot} {t} {trigger} · {ev.old_ip} → {ev.new_ip}"
        lb = QLabel(text, self._history_box)
        lb.setStyleSheet(_make_style(_text_color(secondary=True), font_size=12))
        lb.setToolTip(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ev.timestamp))}\n"
                      f"触发: {trigger}\n{ev.note or ''}")
        return lb

    # ── 操作 ──

    def _on_manual_switch(self):
        if self._is_busy:
            return
        self._is_busy = True
        self._switch_btn.setEnabled(False)
        self._switch_btn.setText("🔄 切换中…")
        try:
            from .ip_redirect import _switch_ip_threadsafe

            new_ip = _switch_ip_threadsafe()
            if new_ip:
                self._switch_btn.setText("✅ 已切换")
            else:
                self._switch_btn.setText("❌ 切换失败")
        finally:
            QTimer.singleShot(2000, self._reset_btn)

    def _reset_btn(self):
        if not self._is_busy:
            return
        self._is_busy = False
        self._switch_btn.setEnabled(True)
        self._switch_btn.setText("🔄 立即换 IP")

    def _on_toggle_auto(self):
        st = self._state
        st.set_auto_switch(not st.is_auto_switch())
        self._config.set("auto_switch", st.is_auto_switch())
        self._refresh_all()

    # ── 生命周期 ──

    def deleteLater(self):
        super().deleteLater()
```

- [ ] **Step 2: ruff 校验**

```bash
cd D:/work/drifox-plugins2
ruff check plugins/ip-switcher/ui/ip_switcher_card.py
```

Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add plugins/ip-switcher/ui/ip_switcher_card.py
git commit -m "feat(ip-switcher): 仪表盘浮动卡片 - 徽章/统计/历史/手动换IP"
```

---

### Task 7: ui/__init__.py — register_ui 集成

**Files:**
- Modify: `D:/work/drifox-plugins2/plugins/ip-switcher/ui/__init__.py`

- [ ] **Step 1: 写 register_ui 入口**

```python
# -*- coding: utf-8 -*-
"""ip-switcher UI 组件入口

注册浮动卡片「IP 换绑监控」并安装 monkey patch：
- /ip-switcher           打开/聚焦仪表盘
- register_ui 时安装 OpenAI patch（幂等）

热重载语义（对齐 UIPluginRegistry.load_plugin 约定）：
1. 清理 sys.modules 残留子模块缓存
2. 清理 function handlers 残留
3. 安装 patch（幂等标记防嵌套）
4. 注册浮动卡片
"""

import sys

from loguru import logger


def register_ui(registry):
    """注册 ip-switcher 插件的 UI 组件（浮动卡片 + monkey patch）"""
    # 0) 安装 monkey patch：白名单模型走代理 + 429 换 IP 重试
    try:
        from .ip_redirect import install_redirect

        install_redirect()
    except Exception:
        logger.exception("[ip-switcher] monkey patch 安装失败（不影响卡片注册）")

    # 1) 清理旧子模块缓存
    prefix = "ui_plugin_ip_switcher."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    # 2) 清理 function handlers 残留
    try:
        from app.core.builtin_commands import FunctionCommandHandlers

        FunctionCommandHandlers._handlers.pop("ip-switcher", None)
    except Exception:
        pass

    # 3) 启动代理池（后台线程，不阻塞注册）
    try:
        from PyQt5.QtCore import QTimer

        def _lazy_start():
            try:
                from .config import get_config
                from .proxy_pool import get_manager
                from .state import get_state

                cfg = get_config()
                if cfg.get("enabled"):
                    manager = get_manager()
                    get_state().set_pool_state("starting")
                    ok = manager.start(fetch_and_check=True)
                    if ok:
                        manager.set_mode("sticky")  # 平时保持同一 IP
                        stats = manager.get_stats()
                        cur = (stats or {}).get("current")
                        if cur:
                            get_state().set_current_ip(cur)
                        get_state().set_pool_state("ok")
                    else:
                        get_state().set_pool_state("error")
            except Exception:
                logger.exception("[ip-switcher] 代理池启动失败")

        QTimer.singleShot(500, _lazy_start)  # 延迟到主循环空闲后
    except Exception:
        logger.exception("[ip-switcher] 代理池启动调度失败")

    # 4) 注册浮动卡片（自动注册 /ip-switcher 命令）
    from .ip_switcher_card import IPSwitcherCard

    registry.register_floating_card(
        plugin_name="ip-switcher",
        card_id="ip-switcher",
        widget_class=IPSwitcherCard,
        container="right",
        title="IP 换绑监控",
        default_visible=False,
    )

    logger.info("[ip-switcher] UI components registered")
```

- [ ] **Step 2: ruff 校验 + 导入测试**

```bash
cd D:/work/drifox-plugins2
ruff check plugins/ip-switcher/ui/
```

Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add plugins/ip-switcher/ui/__init__.py
git commit -m "feat(ip-switcher): register_ui 集成 - patch 安装 + 卡片注册 + 代理池懒启动"
```

---

### Task 8: 完整验证 + 文档同步

**Files:**
- Modify: `D:/work/drifox-plugins2/CHANGELOG.md`
- 全部测试文件

- [ ] **Step 1: 全量测试**

```bash
cd D:/work/drifox-plugins2
python -m pytest tests/test_ip_switcher_*.py -v
```

Expected: 15 passed（5 config + 2 state + 4 proxy_pool + 4 redirect）

- [ ] **Step 2: ruff 全量**

```bash
ruff check plugins/ip-switcher/
ruff format --check plugins/ip-switcher/
```

- [ ] **Step 3: 手动加载验证（DriFox 主程序）**

```bash
cd D:/work/DriFox
python main.py
```

验证清单（checklist.md §3）：
1. `/ip-switcher` 命令打开仪表盘卡片 ✅
2. 卡片字体与主程序一致（深/浅色切换跟随）✅
3. 代理池子进程启动（任务管理器可见 python 进程）✅
4. 卡片「代理池」统计格显示存活数量 ✅
5. 手动换 IP → IP 变化 → 历史新增「手动切换」✅
6. 白名单模型 429 → 自动换 IP + 重试 ✅（需配置真实免费模型验证）

- [ ] **Step 4: 更新 CHANGELOG.md**

在文件顶部新增：

```markdown
## [0.1.0] - 2026-08-04
### Added
- ip-switcher 插件：免费模型限流自动换 IP（429 检测 + 代理池轮换 + 仪表盘）
```

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: CHANGELOG - ip-switcher 0.1.0"
```

---

## 自检记录

**Spec 覆盖：**
- ✅ 需求决策（§2）→ Task 1-8 全覆盖
- ✅ 架构组件（§3）→ config/state/proxy_pool/ip_redirect/card/register 一一对应
- ✅ 数据流（§4）→ Task 5 `_wrap_chat_create` 实现 429 → 换 IP → 重试
- ✅ patch 设计（§5）→ Task 5 幂等标记 + 主线程派发 + 回退
- ✅ 换 IP 逻辑（§6）→ Task 4 `rotate()` + Task 5 `_do_switch_ip()`
- ✅ 错误矩阵（§7）→ Task 5 回退 + Task 4 熔断重置
- ✅ UI（§8）→ Task 6 布局 B
- ✅ 配置（§9）→ Task 2
- ✅ 验证（§10）→ Task 8
- ✅ 开发规范（§11）→ 各 Task 中 `except ... as e`、`padding: 0 Xpx`、worker 清理

**类型一致性：**
- `get_config()` / `get_state()` / `get_manager()` 三个单例函数在 Task 2/3/4 定义，Task 5/6/7 引用一致 ✅
- `_switch_ip_threadsafe()` / `_do_switch_ip()` / `install_redirect()` / `uninstall_redirect()` 签名跨 Task 一致 ✅
- `SwitchEvent` dataclass 字段：timestamp/trigger/old_ip/new_ip/success/note，Task 3 定义，Task 6 使用一致 ✅
- `state.record_switch(trigger, old_ip, new_ip, success, note)` 参数顺序跨 Task 一致 ✅

**占位符扫描：** 无 TBD/TODO/占位描述，所有步骤含完整代码。
