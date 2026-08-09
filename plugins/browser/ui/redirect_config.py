# -*- coding: utf-8 -*-
"""浏览器拦截配置 — 控制系统软件打开浏览器/URL/HTML 的拦截行为

配置存储：~/.drifox/plugins/browser/data/browser-redirect.json
（与收藏/历史/下载 browser.db 同数据目录，随 profile 一并保留）

配置项（DEFAULT_CONFIG 说明）：
- enabled              全局总开关：False 时所有拦截全部失效（走原系统逻辑）
- intercept_system     拦截「打开系统默认浏览器」入口（webbrowser.open /
                       QDesktopServices.openUrl 的 http/https 外链）→ 内置浏览器
- intercept_shell      拦截「shell 工具打开 URL」（bash start/explorer <url>）→ 内置浏览器
- intercept_html       拦截「打开本地 html 文件」（file:// 或本地 .html 路径）→ 内置浏览器

（原实现只拦 http/https；本模块新增 intercept_html 修复「打开 html 不拦截」问题。
 拦截行为一律为重定向到内置浏览器新标签打开，不做询问弹窗。）

线程安全 + 原子写，模式与 ip-switcher/ui/config.py 一致，但存储目录改为
插件自身数据目录（用户明确选择，不走 user-custom）。
"""

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

# ── 默认配置 ──────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "intercept_system": True,
    "intercept_shell": True,
    "intercept_html": True,
}

# 配置文件的固定相对路径（运行时按用户目录解析）
_CONFIG_REL = Path(".drifox") / "plugins" / "browser" / "data" / "browser-redirect.json"


def _get_config_path() -> Path:
    """定位配置文件：~/.drifox/plugins/browser/data/browser-redirect.json"""
    return Path.home() / _CONFIG_REL


class ConfigStore:
    """浏览器拦截配置存储（线程安全 + 原子写）"""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or _get_config_path()
        self._lock = threading.RLock()
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
                    merged.update(
                        {k: v for k, v in saved.items() if k in DEFAULT_CONFIG}
                    )
                    with self._lock:
                        self._data = merged
                    return
        except (OSError, ValueError) as e:
            logger.warning(f"[browser-redirect] 配置加载失败，使用默认值: {e}")
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
            logger.error(f"[browser-redirect] 配置保存失败: {e}")

    # ── 读取 / 写入 ──

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

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


# 模块级单例（热重载时重建）
_store: Optional[ConfigStore] = None


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


# ── 拦截决策（供 external_open 调用）─────────────────────

_HTML_SUFFIX_RE = re.compile(r"\.(?:html?|xhtml)$", re.IGNORECASE)


def _is_http(url: str) -> bool:
    """仅 http/https（scheme 大小写不敏感）"""
    u = url.strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _is_local_html(url: str) -> bool:
    """是否为本地 html 文件（file:// 协议或磁盘 .html 路径）

    判定：
    - file:// 开头（含 file:/// 与 file://server/）→ 看后缀
    - 其余（本地路径 D:/x.html、/home/x.html、UNC 路径）→ 看后缀
    - http/https 链接即使带 .html 后缀也不算本地文件（避免把网页 URL 当本地）
    """
    u = url.strip()
    if not u:
        return False
    if _is_http(u):
        return False
    if u.lower().startswith("file://"):
        return bool(_HTML_SUFFIX_RE.search(u))
    # 无协议字符串（本地路径/相对文件名）：带 html 后缀即视为本地文件。
    # 排除带 scheme:// 的（ftp://x/a.html 等仍走原逻辑；http/https 已在前面剔除）
    if not _HTML_SUFFIX_RE.search(u):
        return False
    return not bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u))


def to_browser_url(url: str) -> str:
    """把任意目标转成内置浏览器可加载的 URL

    - file:// 协议 → 原样
    - 本地 html 路径（D:/x.html 等）→ 转成 file:/// 形式
    - http/https → 原样
    """
    u = url.strip()
    if u.lower().startswith("file://"):
        return u
    if _is_http(u):
        return u
    # 本地路径 → file:// 绝对路径
    try:
        p = Path(u)
        if p.is_absolute() or u.startswith(("/", "\\")):
            return p.resolve().as_uri()
        # 相对路径：基于当前工作目录补全
        return (Path.cwd() / p).resolve().as_uri()
    except (OSError, ValueError) as e:
        logger.debug(f"[browser-redirect] 路径转 file:// 失败({u}): {e}")
        return u


def should_intercept(url: str, entry: str) -> bool:
    """按配置判断某入口是否应拦截该 URL

    entry: "system"（webbrowser/QDesktopServices）| "shell"（bash）
    规则（全局 enabled 关闭一律不拦）：
    - http/https：system -> intercept_system，shell -> intercept_shell
    - 本地 html：统一受 intercept_html 控制（三入口均适用）
    - 其余（file 非 html / mailto / 本地可执行文件等）→ 不拦
    """
    cfg = get_config()
    if not cfg.get("enabled", True):
        return False
    u = url.strip()
    if not u:
        return False
    if _is_local_html(u):
        return bool(cfg.get("intercept_html", True))
    if _is_http(u):
        key = "intercept_system" if entry == "system" else "intercept_shell"
        return bool(cfg.get(key, True))
    return False